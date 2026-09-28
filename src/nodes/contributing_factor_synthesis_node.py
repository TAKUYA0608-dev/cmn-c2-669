"""CMN-C2-669 — inner workflow step 3: contributing_factor_synthesis (Step 4, LLM-judgment).

Maps the evidenced facts onto multiple **contributing factors** using a seeded AI-ops causal taxonomy —
never a single-cause claim, never a person / team attribution (no blame). Deterministic proxy for the
production LLM judgment. Skips (no-op) on rejected / 0-evidence input.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import IncidentEvidenceStore
from src.utils.audit import emit_trace_event


class ContributingFactorSynthesisNode(FunctionNode):
    """Synthesise the causal contributing-factor map (no blame)."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("error_code") or state.get("evidence_count", 0) == 0:
            emit_trace_event(
                "contributing_factor_synthesis.skip", {"reason": state.get("error_code") or "no_evidence"}, state
            )
            return {}
        timeline = json.loads(state.get("normalized_timeline") or "[]")
        facts = json.loads(state.get("fact_hypothesis") or "{}").get("facts", [])
        factors = IncidentEvidenceStore.synthesize_contributing_factors(timeline, facts)
        emit_trace_event(
            "contributing_factor_synthesis.complete",
            {"factor_count": len(factors), "high_confidence": sum(1 for f in factors if f["confidence"] == "high")},
            state,
        )
        return {"contributing_factors": json.dumps(factors, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}
