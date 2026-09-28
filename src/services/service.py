"""CMN-C2-669 — deterministic domain services (no framework imports).

``IncidentEvidenceStore`` holds the auditable, deterministic core of the postmortem workflow:

  * ``normalize_timeline``  — validate records, drop unauthorised access scopes, sort chronologically,
                              and build the evidence chain (stable ``evidence_id`` + provenance).
  * ``classify_fact_hypothesis`` — separate **evidenced facts** from **hypotheses** (objective signal
                              types are facts; hedged operator notes are hypotheses).
  * ``synthesize_contributing_factors`` — map facts onto a seeded AI-ops causal taxonomy, producing
                              multiple contributing factors (never a single-cause claim, never blame).
  * ``redact_credentials``  — defence-in-depth secret redaction (used at S-2 input and S-3 output).

Everything here is deterministic and side-effect-free; the production LLM is reserved for phrasing.
No person / team attribution is ever produced (no blame). No PII or raw secret is persisted.
"""

from __future__ import annotations

import re
from typing import Any

# ── authorised access scopes (S-2) ────────────────────────────────────────────
# Records outside these scopes are dropped before synthesis — the agent only reasons over
# evidence the caller is authorised to share.
AUTHORIZED_SCOPES = frozenset({"incident", "ops", "internal", "authorized", "sre"})

# ── objective signal types (evidenced) vs. narrative types (may be hypothesis) ─
_OBJECTIVE_TYPES = frozenset({"alert", "deployment_change", "eval_observation", "trace_reference"})
_NARRATIVE_TYPES = frozenset({"operator_note"})
_KNOWN_TYPES = _OBJECTIVE_TYPES | _NARRATIVE_TYPES

# Hedge markers → an operator note that speculates is a hypothesis, not a fact.
_HEDGE_MARKERS = (
    "推測",
    "疑い",
    "うたがい",
    "かもしれ",
    "と思われ",
    "おそらく",
    "可能性",
    "maybe",
    "probably",
    "possibly",
    "likely",
    "suspect",
    "seems",
    "might",
    "could be",
)

# ── AI-ops causal taxonomy (contributing factors) ─────────────────────────────
# Each factor is matched deterministically against fact statements. Multiple factors may fire;
# a single-cause conclusion is never forced. Categories are technical, never a person/team.
CAUSAL_TAXONOMY: list[dict[str, Any]] = [
    {
        "category": "deployment_change",
        "label": "デプロイ / リリース変更",
        "tags": [
            "deploy",
            "release",
            "rollout",
            "version",
            "canary",
            "ロールアウト",
            "デプロイ",
            "リリース",
            "バージョン",
        ],
    },
    {
        "category": "model_regression",
        "label": "モデル精度リグレッション",
        "tags": [
            "model",
            "regression",
            "accuracy",
            "hallucination",
            "quality",
            "精度",
            "モデル",
            "ハルシネーション",
            "品質劣化",
        ],
    },
    {
        "category": "data_drift",
        "label": "データドリフト / 分布変化",
        "tags": ["drift", "distribution", "dataset", "ドリフト", "分布", "データ"],
    },
    {
        "category": "prompt_change",
        "label": "プロンプト / 指示テンプレ変更",
        "tags": ["prompt", "template", "instruction", "system message", "プロンプト", "指示"],
    },
    {
        "category": "tool_failure",
        "label": "ツール / 外部API障害",
        "tags": ["tool", "api", "timeout", "connection", "500", "503", "ツール", "タイムアウト", "接続"],
    },
    {
        "category": "capacity_saturation",
        "label": "レート / キャパシティ飽和",
        "tags": [
            "rate limit",
            "throttle",
            "capacity",
            "latency",
            "quota",
            "レート",
            "スロットル",
            "飽和",
            "レイテンシ",
        ],
    },
    {
        "category": "config_drift",
        "label": "設定 / コンフィグドリフト",
        "tags": ["config", "setting", "parameter", "flag", "設定", "コンフィグ", "パラメータ"],
    },
    {
        "category": "dependency_change",
        "label": "依存 / プロバイダ変更",
        "tags": ["dependency", "upstream", "provider", "sdk", "依存", "プロバイダ", "アップストリーム"],
    },
]

# ── credential redaction (defence-in-depth, S-2 input / S-3 output) ────────────
# Patterns only — no literal credential value lives in source (S-5 / gate-credential-scan safe).
_CRED_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),  # OpenAI-style keys
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),  # JWT
    re.compile(r"(?i)(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+"),  # key=value
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{12,}"),  # bearer tokens
)
_CRED_MASK = "[REDACTED-SECRET]"

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def redact_credentials(text: str) -> str:
    """Redact secret-shaped substrings (best-effort, deterministic). Never raises."""
    out = text or ""
    for pat in _CRED_PATTERNS:
        out = pat.sub(_CRED_MASK, out)
    return out


def _clean(text: str) -> str:
    """Strip control chars and redact secrets before a value is persisted / emitted."""
    return redact_credentials(_CONTROL.sub("", text or ""))


def _summarize(content: str, limit: int = 200) -> str:
    one_line = re.sub(r"\s+", " ", _clean(content)).strip()
    return one_line[:limit]


class IncidentEvidenceStore:
    """Deterministic timeline / fact / factor synthesis over an authorised evidence set."""

    @staticmethod
    def normalize_timeline(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        """Validate + authorise + chronologically order the evidence chain.

        Returns ``(timeline, rejected_count)``. A record is dropped when it lacks a known type or a
        timestamp, or its ``access_scope`` is not authorised. Timeline entries are stable, secret-free.
        """
        timeline: list[dict[str, Any]] = []
        rejected = 0
        for rec in records or []:
            if not isinstance(rec, dict):
                rejected += 1
                continue
            rtype = str(rec.get("type") or "").strip().lower()
            ts = str(rec.get("timestamp") or rec.get("ts") or "").strip()
            scope = str(rec.get("access_scope") or rec.get("scope") or "").strip().lower()
            if rtype not in _KNOWN_TYPES or not ts:
                rejected += 1
                continue
            if scope and scope not in AUTHORIZED_SCOPES:
                rejected += 1  # S-2: unauthorised evidence is not reasoned over
                continue
            timeline.append(
                {
                    "ts": ts,
                    "type": rtype,
                    "source": _clean(str(rec.get("source") or "unknown"))[:120],
                    "access_scope": scope or "unspecified",
                    "summary": _summarize(str(rec.get("content") or rec.get("summary") or "")),
                }
            )
        timeline.sort(key=lambda e: (e["ts"], e["type"]))
        for i, entry in enumerate(timeline, start=1):
            entry["evidence_id"] = f"EV-{i:03d}"
        return timeline, rejected

    @staticmethod
    def classify_fact_hypothesis(timeline: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Separate evidenced facts from hypotheses (deterministic)."""
        facts: list[dict[str, Any]] = []
        hypotheses: list[dict[str, Any]] = []
        for e in timeline:
            statement = e["summary"]
            if e["type"] in _OBJECTIVE_TYPES:
                # An objective signal (alert / deploy change / eval obs / trace ref) is a recorded fact.
                facts.append(
                    {"evidence_id": e["evidence_id"], "statement": statement, "type": e["type"], "source": e["source"]}
                )
            elif any(m in statement.lower() for m in _HEDGE_MARKERS):
                # A hedged / speculative operator note is a hypothesis, not a directly evidenced fact.
                hypotheses.append(
                    {
                        "evidence_id": e["evidence_id"],
                        "statement": statement,
                        "basis": "hedged / speculative — not directly evidenced",
                    }
                )
            else:
                # A non-hedged operator note is an asserted fact but flagged corroboration-low.
                facts.append(
                    {
                        "evidence_id": e["evidence_id"],
                        "statement": statement,
                        "type": e["type"],
                        "source": e["source"],
                        "corroboration": "low",
                    }
                )
        return {"facts": facts, "hypotheses": hypotheses}

    @staticmethod
    def synthesize_contributing_factors(
        timeline: list[dict[str, Any]], facts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Map facts onto the causal taxonomy → multiple contributing factors (no blame)."""
        by_id = {e["evidence_id"]: e for e in timeline}
        out: list[dict[str, Any]] = []
        for fac in CAUSAL_TAXONOMY:
            evidence_ids: list[str] = []
            for f in facts:
                entry = by_id.get(f["evidence_id"], {})
                hay = f"{f.get('statement', '')} {entry.get('type', '')}".lower()
                if any(tag in hay for tag in fac["tags"]):
                    evidence_ids.append(f["evidence_id"])
            if evidence_ids:
                out.append(
                    {
                        "factor": fac["label"],
                        "category": fac["category"],
                        "evidence_ids": evidence_ids,
                        "confidence": "high" if len(evidence_ids) >= 2 else "medium",
                    }
                )
        out.sort(key=lambda x: (-len(x["evidence_ids"]), x["category"]))
        return out
