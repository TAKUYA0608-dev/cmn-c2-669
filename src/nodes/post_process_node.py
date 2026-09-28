"""CMN-C2-669 — post_process node: PostmortemEnvelope (S-3 output gate + S-4 audit).

S-3: verify citation completeness (a grounded postmortem must cite its evidence chain), redact any
credential leak (defence-in-depth), and append the mandatory DRAFT disclaimer ("the final postmortem /
accountability conclusion is a human decision"). S-4: emit an audit event (counts / kinds only — never
the raw evidence content or a secret). Runs on both the full draft and the out-of-scope safe branch.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import redact_credentials
from src.utils.audit import emit_trace_event

_DISCLAIMER = (
    "本 postmortem は認可済みインシデント証跡に基づく DRAFT の助言であり、事実 (fact) と推測 (hypothesis) を"
    "分離し、複数の寄与要因を因果構造で提示するものです。責任断定 (blame) は行わず、本番システムへの変更・"
    "封じ込め・是正の自動実行も一切行いません。最終的な postmortem の確定・accountability・監査結論、および"
    "是正アクションの owner 割当は、認可済みの人間 (HumanGate) が判断します。"
)


class PostProcessNode(FunctionNode):
    """Verify citations, redact leaks, append DRAFT disclaimer, emit audit."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """S-3 preservation check: the DRAFT disclaimer must be present in the output envelope.

        SDK 1.0.0 contract: receives the **result dict from ``execute()``**; returns the (possibly
        filtered) result. MAY raise to block an output missing the mandatory disclaimer.
        """
        out = result.get("formatted_output", "")
        if out and "DRAFT" not in out and "HumanGate" not in out:
            raise ValueError("S-3: mandatory DRAFT disclaimer missing from output")
        return dict(result)

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        report: dict[str, Any] = json.loads(state.get("result", "{}") or "{}")

        citations = report.get("citations", [])
        grounded = report.get("status_kind") == "postmortem"
        citation_complete = (not grounded) or bool(citations)

        formatted = {
            "status_kind": report.get("status_kind"),
            "incident_id": report.get("incident_id"),
            "timeline": report.get("timeline", []),
            "facts": report.get("facts", []),
            "hypotheses": report.get("hypotheses", []),
            "contributing_factors": report.get("contributing_factors", []),
            "corrective_actions": report.get("corrective_actions", []),
            "human_review": report.get("human_review", {}),
            "citations": citations,
            "citation_complete": citation_complete,
            "message": report.get("message"),
            "disclaimer": _DISCLAIMER,
        }
        # S-3 defence-in-depth: redact any secret that survived into the assembled envelope.
        envelope = redact_credentials(json.dumps(formatted, ensure_ascii=False))
        emit_trace_event(
            "post_process.complete",
            {
                "status_kind": report.get("status_kind"),
                "factor_count": len(report.get("contributing_factors", [])),
                "citation_complete": citation_complete,
                "error_code": state.get("error_code"),
            },
            state,
        )
        return {
            "formatted_output": envelope,
            "disclaimer": _DISCLAIMER,
            "audit_logged": True,
            "status": AgentStatus.SUCCESS.value,
        }
