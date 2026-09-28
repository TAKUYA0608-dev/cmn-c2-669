"""CMN-C2-669 — inner workflow step 1: timeline_normalize (Step 2 EvidenceValidate → TimelineNormalize).

Deterministic normalisation of the authorised incident records into a timestamp-consistent chronological
timeline + evidence chain (stable ``evidence_id``, provenance and access scope preserved). Sets
``evidence_count``; **0 valid entries (rejected input or none authorised) routes to the out-of-scope safe
answer** — the agent never fabricates a postmortem that is not grounded in the evidence chain.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import IncidentEvidenceStore
from src.utils.audit import emit_trace_event


class TimelineNormalizeNode(FunctionNode):
    """Build the chronological evidence chain from the authorised records."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(state.get("validated_input") or state.get("user_input") or "{}")
        canonical = json.dumps(payload, ensure_ascii=False)
        if state.get("error_code") or not isinstance(payload, dict):
            emit_trace_event("timeline_normalize.skip", {"reason": state.get("error_code") or "no_payload"}, state)
            return {
                "validated_input": canonical,
                "normalized_timeline": "[]",
                "evidence_count": 0,
                "rejected_evidence_count": state.get("rejected_evidence_count", 0),
                "error_code": state.get("error_code") or "NO_EVIDENCE",
                "status": AgentStatus.SUCCESS.value,
            }

        timeline, rejected = IncidentEvidenceStore.normalize_timeline(payload.get("records", []))
        emit_trace_event("timeline_normalize.complete", {"evidence_count": len(timeline), "rejected": rejected}, state)
        out = {
            "validated_input": canonical,
            "normalized_timeline": json.dumps(timeline, ensure_ascii=False),
            "evidence_count": len(timeline),
            "rejected_evidence_count": rejected,
            "status": AgentStatus.SUCCESS.value,
        }
        if not timeline:
            out["error_code"] = "NO_EVIDENCE"
        return out
