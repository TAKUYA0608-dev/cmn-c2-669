# CMN-C2-669 — Unit Tests: Cat 2 graph wiring (outer GraphNode + inner workflow)

import pytest

from src.graph.domain_workflow_graph import IncidentPostmortemWorkflow
from src.graph.graph import (
    Graph,
    IncidentEvidenceTimelinePostmortemSynthesisAgent,
    IncidentPostmortemWorkflowGraphNode,
)
from src.schemas.state import State


class TestOuterGraph:
    def test_registry_alias(self):
        assert IncidentEvidenceTimelinePostmortemSynthesisAgent is Graph

    def test_name_and_state_schema(self):
        g = Graph()
        assert g.name == "IncidentEvidenceTimelinePostmortemSynthesisAgent"
        assert g.state_schema is State

    def test_main_slot_is_graphnode(self):
        g = Graph()
        g.register_nodes()
        assert isinstance(g._nodes["main"], IncidentPostmortemWorkflowGraphNode)
        for slot in ("pre_process", "main", "post_process"):
            assert slot in g._nodes

    def test_error_strategy_propagate(self):
        assert IncidentPostmortemWorkflowGraphNode.error_strategy == "propagate"

    def test_get_subgraph_is_cached(self):
        node = IncidentPostmortemWorkflowGraphNode()
        assert node.get_subgraph() is node.get_subgraph()

    def test_merge_output_maps_fields(self):
        node = IncidentPostmortemWorkflowGraphNode()
        merged = node.merge_output({}, {"output": '{"x":1}', "evidence_count": 3, "status": "success",
                                        "error_code": None})
        assert merged["result"] == '{"x":1}' and merged["evidence_count"] == 3


class TestInnerWorkflow:
    def test_inner_registers_five_nodes(self):
        wf = IncidentPostmortemWorkflow(config={})
        wf.register_nodes()
        for slot in ("timeline_normalize", "fact_hypothesis_classify",
                     "contributing_factor_synthesis", "human_gate", "postmortem_compose"):
            assert slot in wf._nodes

    def test_route_zero_evidence_to_compose(self):
        wf = IncidentPostmortemWorkflow(config={})
        assert wf.route({"evidence_count": 0}) == "postmortem_compose"

    def test_route_normal_to_classify(self):
        wf = IncidentPostmortemWorkflow(config={})
        assert wf.route({"evidence_count": 3}) == "fact_hypothesis_classify"

    def test_inner_name_and_state_schema(self):
        wf = IncidentPostmortemWorkflow(config={})
        assert wf.name == "IncidentPostmortemWorkflow"
        assert wf.state_schema is State

    def test_inner_get_output_maps_fields(self):
        wf = IncidentPostmortemWorkflow(config={})
        out = wf.get_output({"result": '{"x":1}', "status": "success", "evidence_count": 2,
                             "error_code": None, "node_history": []})
        assert out["output"] == '{"x":1}' and out["evidence_count"] == 2 and out["status"] == "success"


class TestServerModule:
    def test_server_imports(self):
        try:
            import src.api.server as server
        except ModuleNotFoundError as exc:
            pytest.skip(f"platform module unavailable in the local stub env: {exc}")
        assert server.app is not None and server.agent is not None
