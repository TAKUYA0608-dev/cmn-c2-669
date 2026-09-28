"""CMN-C2-669 — inner workflow step 2: fact_hypothesis_classify (Step 3, LLM-judgment).

Separates **evidenced facts** from **hypotheses** over the normalised timeline. Objective signal types
(alert / deployment change / eval observation / trace reference) are facts; hedged / speculative
operator notes are hypotheses. Deterministic proxy for the production LLM judgment — auditable and
testable. Skips (no-op) on rejected / 0-evidence input.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import IncidentEvidenceStore
from src.utils.audit import emit_trace_event


class FactHypothesisClassifyNode(FunctionNode):
    """Classify each timeline entry as an evidenced fact or a hypothesis."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("error_code") or state.get("evidence_count", 0) == 0:
            emit_trace_event(
                "fact_hypothesis_classify.skip", {"reason": state.get("error_code") or "no_evidence"}, state
            )
            return {}
        timeline = json.loads(state.get("normalized_timeline") or "[]")
        classified = IncidentEvidenceStore.classify_fact_hypothesis(timeline)
        emit_trace_event(
            "fact_hypothesis_classify.complete",
            {"fact_count": len(classified["facts"]), "hypothesis_count": len(classified["hypotheses"])},
            state,
        )
        return {"fact_hypothesis": json.dumps(classified, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}
