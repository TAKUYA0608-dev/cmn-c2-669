# Template Design Specification — CMN-C2-669

**AI Incident Evidence Timeline & Postmortem Synthesis Agent** (Cat 2 · CMN)

Post-incident, advisory-only synthesis of a Postmortem Draft from **authorised** incident records.
Read-only: no live response, no containment, no blame assignment, no production change. Final
accountability stays with an authorised human via a mandatory HumanGate.

## Position in AgentCore Architecture

- **Agent Class**: `IncidentEvidenceTimelinePostmortemSynthesisAgent` (module `src.graph`, alias of `Graph`)
- **L1 Base**: **AgentBaseGraph** (L1-direct). `DocGenerationAgent` is a §5/§10 *pattern reference only* —
  the Incident Postmortem Synthesis pattern is enclosed inside this template (2026-05-18 PM
  Level-2-abolition policy). Not `AutonomousBaseGraph`.
- **Category**: Cat 2 — a fixed multi-step workflow that produces one deliverable (a Postmortem Draft).
- **Three-Layer Separation**:
  - State: flat `TypedDict` (`src/schemas/state.py`); complex values are JSON strings (ADR-005) — no Pydantic.
  - Node: L1 inheritance (Template Method — override `execute(self, state: dict) -> dict` only; never `__call__`).
  - Graph: composition — outer `AgentBaseGraph` 5-slot backbone + a `GraphNode` in the `main` slot wrapping
    the inner domain workflow (`src/graph/domain_workflow_graph.py`).

## Architecture Overview — Cat 2 GraphNode-in-main

The outer graph is the standard fixed 5-slot backbone. All domain complexity is encapsulated inside
`IncidentPostmortemWorkflowGraphNode.get_subgraph()`, which wraps the inner `IncidentPostmortemWorkflow`
(a `BaseGraph`). The inner graph is **linear with per-node skip guards** — conditional edges are not used
because they do not propagate across the subgraph boundary.

### Outer Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | user_input | framework fields | InitializeNode (default) |
| pre_process | **EvidenceValidate** — S-1 NFKC/size cap + S-2 authorised-scope gate + credential redaction; parse the incident record set | user_input | validated_input, input_format, enriched_context, rejected_evidence_count | PreProcessNode (FunctionNode) |
| main | **IncidentPostmortemWorkflowGraphNode** — runs the inner 5-node workflow | validated_input | result, evidence_count, error_code, status | GraphNode (wraps inner BaseGraph) |
| post_process | **PostmortemEnvelope** — S-3 output gate (DRAFT disclaimer + citation completeness + credential-leak redaction) + S-4 audit | result | formatted_output, disclaimer, audit_logged | PostProcessNode (FunctionNode) |
| finalize | response_metadata, total_time_ms | — | framework fields | FinalizeNode (default) |

### Inner Workflow Node Configuration (`domain_workflow_graph.py`)

| Inner Node | Responsibility | required_trust_level |
|------------|----------------|----------------------|
| timeline_normalize | Validate records, normalise timestamps into a consistent chronological timeline, build the evidence chain (provenance + access scope preserved). Sets `evidence_count`; 0 → `error_code=NO_EVIDENCE`. Deterministic. | VERIFIED_EXTERNAL |
| fact_hypothesis_classify | Deterministic (taxonomy + hedge markers), no LLM in the execution path: separate **evidenced facts** from **hypotheses** (objective signal types = fact; hedged operator notes = hypothesis). | VERIFIED_EXTERNAL |
| contributing_factor_synthesis | Deterministic (AI-ops taxonomy), no LLM in the execution path: map multiple **contributing factors** to a causal structure — never a single-cause claim, never a person/team attribution (no blame). | VERIFIED_EXTERNAL |
| human_gate | Deterministic HumanGate: route material decisions / uncertainty (hypotheses, non-high-confidence factors, unassigned corrective actions) to authorised review; record exceptions. | VERIFIED_EXTERNAL |
| postmortem_compose | Compose the Postmortem Draft deliverable (timeline / facts / hypotheses / contributing factors / corrective-action proposals [owner unassigned — HumanGate] / human-review status / citations / DRAFT disclaimer). 0-evidence → out-of-scope safe answer (`citations=[]`). | VERIFIED_EXTERNAL |

### Data Flow

```
START → initialize → pre_process → main(GraphNode) → {route} → post_process → finalize → END
                                          ↓ (retry, max 3)
                                       pre_process

inner (linear + per-node skip guard):
  START → timeline_normalize → fact_hypothesis_classify → contributing_factor_synthesis
        → human_gate → postmortem_compose → END
```

On rejected / 0-evidence input, `timeline_normalize` sets `evidence_count=0` (+`error_code`), the
classify / synthesis / human_gate nodes no-op, and `postmortem_compose` emits the out-of-scope safe
answer — no fabricated postmortem, `citations=[]`.

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| validated_input | str (JSON) | `{incident_id, records[], taxonomy_hint}` after S-1/S-2 | progressive |
| input_format | str | `json` / `text` / `empty` | progressive |
| enriched_context | str (JSON) | read-only caller context `{source, channel}` | progressive |
| rejected_evidence_count | int | records dropped by the S-2 access-scope check | progressive |
| normalized_timeline | str (JSON) | chronological evidence chain | progressive |
| evidence_count | int | valid evidence entries (0 → safe answer) | progressive |
| fact_hypothesis | str (JSON) | `{facts[], hypotheses[]}` | progressive |
| contributing_factors | str (JSON) | `[{factor, category, evidence_ids, confidence}]` | progressive |
| human_review | str (JSON) | `{required, escalation, material_review_items}` | progressive |
| result | str (JSON) | assembled Postmortem Draft | progressive |
| formatted_output | str (JSON) | final envelope + DRAFT disclaimer | progressive |
| disclaimer | str | mandatory DRAFT / "final postmortem is a human decision" note | progressive |
| audit_logged | bool | terminal S-4 audit emitted | progressive |
| error_code | str | INPUT_REJECTED / INJECTION_REJECTED / INPUT_TOO_LONG / NO_EVIDENCE | on degraded path |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serialisable types); complex values are JSON strings (ADR-005).
- No JWT, API keys, credentials, PII, Pydantic, dataclass, or `InvocationContext` in State.
- Degraded / rejected paths return `status=SUCCESS + error_code` — never `status=ERROR` (ERROR skips
  post_process / S-3 / S-4 in the production SDK).

## Framework Utilization

### Shared Components Used
- [x] S-2: `_extra_security_gate_input()` on PreProcessNode — no hard reject (returns state unchanged;
      framework default PII masking applies). Prompt-injection / oversize are detected in `execute()` and
      returned as the degraded **`SUCCESS + error_code`** path (untrusted content never processed), **never
      `status=ERROR`** (ERROR short-circuits `__call__` and skips post_process / S-3 / S-4). Access-scope
      filtering + credential redaction happen inside `execute()`.
- [x] S-3: `_extra_security_gate_output()` on PostProcessNode — verifies the DRAFT disclaimer is present;
      **may raise** to block an unsafe output. Receives the `execute()` result delta.
- [x] S-4: `emit_trace_event()` — one domain event inside **every** `execute()` (counts / kinds only —
      never the raw evidence content; APPI/secret-safe). Sourced from `src.utils.audit` (platform
      `shared.utils.audit_logger` with a local SDK stub stderr fallback).

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass (pre/post/all 5 inner nodes) → framework `@final` gate always runs; extend via
>   `_extra_security_gate_input/output()` only.
> - `GraphNode` (main slot) → deliberate no-op (the inner nodes' gates already applied).

### Composition Pattern

- **Pattern**: GraphNode (subgraph) in the `main` slot wrapping an inner `BaseGraph` domain workflow.
- **Composition target**: `IncidentPostmortemWorkflow` (inner) via `get_subgraph()` (cached in `self._subgraph`).
- **Error propagation strategy**: `error_strategy = "propagate"`; degraded paths carry `error_code`
  with `status=SUCCESS`.

## Import Isolation Confirmation
- [x] Template does not import the `agenticstar` SDK (Level 0) — `framework.*` / `shared.*` only (PB-4).
- [x] Deterministic domain services (`src/services/service.py`) import no framework — pure Python.

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | **AgentBaseGraph** | AutonomousBaseGraph | **AgentBaseGraph** | Fixed multi-step workflow; no autonomous loop needed. |
| Composition pattern | FunctionNode-in-main (Cat 1) | **GraphNode-in-main (Cat 2)** | **GraphNode-in-main** | Domain complexity is a 5-node workflow → encapsulate in inner BaseGraph. |
| Inner topology | conditional edges | **linear + per-node skip guard** | **linear + skip guard** | Conditional edges do not propagate across the subgraph boundary. |
| Degraded signalling | status=ERROR | **status=SUCCESS + error_code** | **SUCCESS + error_code** | ERROR skips post_process / S-3 / S-4 in the production SDK. |
| Fact vs hypothesis / factors | real LLM at build | **deterministic proxy (taxonomy + hedge markers)** | **deterministic proxy** | Auditable, testable; production LLM reserved for phrasing. |
