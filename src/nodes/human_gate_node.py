"""CMN-C2-669 — inner workflow step 4: human_gate (Step 5, deterministic HumanGate).

Advisory-only design principle: the final postmortem is a human decision. This deterministic gate routes
material decisions / uncertainty to an authorised reviewer and records the exceptions:

  * ``required``  — always True (the final postmortem / accountability conclusion is a human decision).
  * ``escalation`` — "elevated" when hypotheses exist or any contributing factor is below high confidence,
    else "standard".
  * ``material_review_items`` — the specific items an authorised human must decide (unverified hypotheses,
    non-high-confidence factors, corrective-action owner assignment).

Skips (no-op) on rejected / 0-evidence input.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.utils.audit import emit_trace_event


class HumanGateNode(FunctionNode):
    """Route material decisions / uncertainty to authorised human review."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("error_code") or state.get("evidence_count", 0) == 0:
            emit_trace_event("human_gate.skip", {"reason": state.get("error_code") or "no_evidence"}, state)
            return {}
        fh = json.loads(state.get("fact_hypothesis") or "{}")
        hypotheses = fh.get("hypotheses", [])
        factors = json.loads(state.get("contributing_factors") or "[]")

        items: list[dict[str, Any]] = []
        for h in hypotheses:
            items.append(
                {
                    "kind": "unverified_hypothesis",
                    "ref": h.get("evidence_id"),
                    "detail": "推測を結論に含める前に認可済みレビューで検証が必要",
                }
            )
        for f in factors:
            if f.get("confidence") != "high":
                items.append(
                    {
                        "kind": "low_confidence_factor",
                        "ref": f.get("category"),
                        "detail": "寄与要因の確信度が high 未満 — 認可済みレビューで確認",
                    }
                )
        if factors:
            items.append(
                {
                    "kind": "corrective_action_owner",
                    "ref": None,
                    "detail": "是正アクションの owner 割当は認可済み人手のみ (自動割当なし)",
                }
            )

        escalation = "elevated" if (hypotheses or any(f.get("confidence") != "high" for f in factors)) else "standard"
        review = {"required": True, "escalation": escalation, "material_review_items": items}
        emit_trace_event("human_gate.complete", {"escalation": escalation, "review_item_count": len(items)}, state)
        return {"human_review": json.dumps(review, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}
