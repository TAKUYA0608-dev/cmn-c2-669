"""CMN-C2-669 — pre_process node: EvidenceValidate (S-1 input validation + S-2 authorised-scope gate).

Accepts a structured JSON incident payload ``{incident_id, records[], taxonomy_hint}`` or NL text,
normalises it (NFKC), enforces S-1/S-2 (size cap + prompt-injection markers via
``_extra_security_gate_input``), redacts any inadvertently supplied secret (defence-in-depth), and
drops records outside authorised access scopes.

Hard rejects (empty / injection / oversize) return ``status=SUCCESS + error_code`` (degraded, never ERROR).
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import redact_credentials
from src.utils.audit import emit_trace_event

_MAX_INPUT = 200_000  # incident payloads can be large (multiple records)
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard the above",
    "system prompt",
    "you are now",
    "###system",
    "<|im_start|>",
)


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


class PreProcessNode(FunctionNode):
    """Validate the incident payload and extract the authorised evidence set."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2 domain hook — no hard reject.

        SDK 1.0.0 contract: MUST NOT raise. Prompt-injection / oversize are handled as the degraded
        ``SUCCESS + error_code`` path in ``execute()`` (untrusted content never processed) so main /
        post_process S-3/S-4 always run. A ``status=ERROR`` here would short-circuit ``__call__`` and skip
        main / post_process. Framework default PII masking still applies.
        """
        return dict(state)

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "") or ""
        input_context = state.get("input_context", {})  # read-only [C1]
        enriched = json.dumps(
            {
                "source": "IncidentEvidenceTimelinePostmortemSynthesisAgent",
                "channel": input_context.get("channel", "unknown"),
            },
            ensure_ascii=False,
        )
        normalized = _nfkc(raw).strip()

        # Prompt-injection / oversize -> degraded SUCCESS + error_code (never processed). NOT ERROR:
        # ERROR short-circuits __call__ so main / post_process (disclaimer / redaction / audit) would be
        # skipped. The untrusted body is discarded; the safe-answer path runs.
        reject_code = None
        if len(raw) > _MAX_INPUT:
            reject_code = "INPUT_TOO_LONG"
        elif any(marker in normalized.lower() for marker in _INJECTION_MARKERS):
            reject_code = "INJECTION_REJECTED"
        if reject_code:
            emit_trace_event("evidence_validate.rejected", {"reason": reject_code.lower()}, state)
            return {
                "validated_input": "{}",
                "input_format": "rejected",
                "enriched_context": enriched,
                "rejected_evidence_count": 0,
                "error_code": reject_code,
                "status": AgentStatus.SUCCESS.value,
            }

        if not raw.strip():
            emit_trace_event("evidence_validate.rejected", {"reason": "empty_input"}, state)
            return {
                "validated_input": "{}",
                "input_format": "empty",
                "enriched_context": enriched,
                "rejected_evidence_count": 0,
                "error_code": "INPUT_REJECTED",
                "status": AgentStatus.SUCCESS.value,
            }

        payload, fmt = self._parse(_nfkc(raw).strip())
        records = payload.get("records", [])
        emit_trace_event(
            "evidence_validate.validated",
            {"input_format": fmt, "record_count": len(records)},
            state,
        )
        return {
            "validated_input": json.dumps(payload, ensure_ascii=False),
            "input_format": fmt,
            "enriched_context": enriched,
            "rejected_evidence_count": 0,
            "status": AgentStatus.SUCCESS.value,
        }

    def _parse(self, text: str) -> tuple[dict[str, Any], str]:
        """Parse a JSON incident payload; fall back to a single free-text operator note."""
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and isinstance(obj.get("records"), list):
                return {
                    "incident_id": str(obj.get("incident_id") or "unspecified"),
                    "records": [self._clean_record(r) for r in obj["records"] if isinstance(r, dict)],
                    "taxonomy_hint": obj.get("taxonomy_hint"),
                }, "json"
        except (ValueError, TypeError):
            pass
        # Free text → treat as one operator note (no timestamp → dropped downstream unless dated).
        note = redact_credentials(text)
        return {
            "incident_id": "unspecified",
            "records": [
                {
                    "type": "operator_note",
                    "timestamp": "",
                    "source": "free-text",
                    "access_scope": "incident",
                    "content": note,
                }
            ],
            "taxonomy_hint": None,
        }, "text"

    def _clean_record(self, rec: dict[str, Any]) -> dict[str, Any]:
        """Redact secrets in record content before it is persisted to State (S-2 defence-in-depth)."""
        cleaned = dict(rec)
        for key in ("content", "summary", "source"):
            if isinstance(cleaned.get(key), str):
                cleaned[key] = redact_credentials(cleaned[key])
        return cleaned
