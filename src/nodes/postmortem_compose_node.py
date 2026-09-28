"""CMN-C2-669 — inner workflow step 5: postmortem_compose (Step 6 core — deliverable producer).

Assembles the **Postmortem Draft** deliverable: timeline / facts / hypotheses / contributing factors /
corrective-action proposals (owner unassigned — HumanGate) / human-review status / citations. On the
0-evidence / rejected branch it emits the out-of-scope safe answer (``citations=[]``). Every corrective
action is a *proposal* only — never auto-executed, never a person / team attribution (no blame). The
final draft is marked DRAFT; final accountability stays with an authorised human.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.utils.audit import emit_trace_event

_OUT_OF_SCOPE = (
    "認可済みのインシデント証跡が見つからなかったため、postmortem ドラフトを合成できませんでした。"
    "対象は認可済みのインシデント記録 (alert / deployment change / eval observation / operator note / "
    "trace reference、タイムスタンプ + 認可済み access scope 付き) です。証跡を具体化するか所管の"
    "インシデントマネージャーにご確認ください。"
)


class PostmortemComposeNode(FunctionNode):
    """Compose the evidence-grounded Postmortem Draft (or safe answer on 0-evidence)."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        timeline = json.loads(state.get("normalized_timeline") or "[]")
        if state.get("error_code") or not timeline:
            emit_trace_event("postmortem_compose.safe", {"reason": state.get("error_code") or "no_evidence"}, state)
            report: dict[str, Any] = {
                "status_kind": "out_of_scope",
                "message": _OUT_OF_SCOPE,
                "timeline": [],
                "facts": [],
                "hypotheses": [],
                "contributing_factors": [],
                "corrective_actions": [],
                "human_review": {},
                "citations": [],
            }
            return {"result": json.dumps(report, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}

        payload = json.loads(state.get("validated_input") or "{}")
        fh = json.loads(state.get("fact_hypothesis") or "{}")
        factors = json.loads(state.get("contributing_factors") or "[]")
        human_review = json.loads(state.get("human_review") or "{}")

        # Corrective-action proposals — one per contributing factor, owner unassigned (HumanGate).
        corrective_actions: list[dict[str, Any]] = [
            {
                "proposal": f"寄与要因『{f['factor']}』への是正を検討 (根拠: {', '.join(f['evidence_ids'])})",
                "factor_category": f["category"],
                "owner": None,
                "status": "unassigned",
                "requires_human_assignment": True,
            }
            for f in factors
        ]
        citations = [
            {"evidence_id": e["evidence_id"], "source": e.get("source", "unknown"), "ts": e.get("ts")} for e in timeline
        ]

        report = {
            "status_kind": "postmortem",
            "incident_id": payload.get("incident_id", "unspecified"),
            "timeline": timeline,
            "facts": fh.get("facts", []),
            "hypotheses": fh.get("hypotheses", []),
            "contributing_factors": factors,
            "corrective_actions": corrective_actions,
            "human_review": human_review,
            "citations": citations,
            "draft": True,
        }
        emit_trace_event(
            "postmortem_compose.complete",
            {"fact_count": len(fh.get("facts", [])), "factor_count": len(factors), "citation_count": len(citations)},
            state,
        )
        return {"result": json.dumps(report, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}
