"""CMN-C2-669 — inner domain workflow graph (Cat 2).

Instantiated by IncidentPostmortemWorkflowGraphNode.get_subgraph() in graph.py. Linear topology with
per-node skip guards (the portable Cat 2 form; conditional edges don't propagate across the subgraph
boundary):

    START → timeline_normalize → fact_hypothesis_classify → contributing_factor_synthesis
          → human_gate → postmortem_compose → END

On rejected / 0-evidence input, timeline_normalize sets evidence_count=0 (+error_code); the classify,
synthesis and human_gate nodes no-op, and postmortem_compose emits the out-of-scope safe answer — no
fabricated postmortem.
"""

from __future__ import annotations
from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState

from src.nodes.contributing_factor_synthesis_node import ContributingFactorSynthesisNode
from src.nodes.fact_hypothesis_classify_node import FactHypothesisClassifyNode
from src.nodes.human_gate_node import HumanGateNode
from src.nodes.postmortem_compose_node import PostmortemComposeNode
from src.nodes.timeline_normalize_node import TimelineNormalizeNode
from src.schemas.state import State


class IncidentPostmortemWorkflow(BaseGraph):
    """Inner graph: timeline → fact/hypothesis → factors → human_gate → compose."""

    @property
    def name(self) -> str:
        return "IncidentPostmortemWorkflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        # No super() — BaseGraph.register_nodes() is abstract.
        self._nodes["timeline_normalize"] = TimelineNormalizeNode()
        self._nodes["fact_hypothesis_classify"] = FactHypothesisClassifyNode()
        self._nodes["contributing_factor_synthesis"] = ContributingFactorSynthesisNode()
        self._nodes["human_gate"] = HumanGateNode()
        self._nodes["postmortem_compose"] = PostmortemComposeNode()

    def add_edges(self) -> None:
        # Static linear backbone; the 0-evidence / rejected skip is handled by per-node guards.
        self._sg.add_edge(START, "timeline_normalize")
        self._sg.add_edge("timeline_normalize", "fact_hypothesis_classify")
        self._sg.add_edge("fact_hypothesis_classify", "contributing_factor_synthesis")
        self._sg.add_edge("contributing_factor_synthesis", "human_gate")
        self._sg.add_edge("human_gate", "postmortem_compose")
        self._sg.add_edge("postmortem_compose", END)

    def route(self, state: AgentState) -> str:
        """Required by the BaseGraph ABC. Linear topology → not wired to a conditional edge."""
        if state.get("error_code") or state.get("evidence_count", 0) == 0:
            return "postmortem_compose"
        return "fact_hypothesis_classify"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "output": state.get("result"),
            "status": state.get("status"),
            "evidence_count": state.get("evidence_count", 0),
            "error_code": state.get("error_code"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
