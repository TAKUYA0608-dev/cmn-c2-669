# Test Specification — CMN-C2-669

## Test Strategy
- Coverage target: **≥ 89%** (achieved ~90% overall; core nodes/services 96–100%; `src/api/server.py`
  and inner-graph wiring are exercised only under the real SDK).
- Test types: Unit (`tests/unit/`) / Integration (`tests/integration/`) / Proof-of-Boundary (`tests/proof_of_boundary/`).
- Run: `python -m pytest tests/ -v` then `python -m pytest tests/proof_of_boundary/ -v` (mirrors central CI `run-tests`).

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | No Pydantic/dataclass; complex fields are JSON strings (ADR-005) | PASS (`test_state_safety`) |
| TC-02 | Injection/oversize = degraded (not ERROR) | injection/oversize → `SUCCESS + error_code` (`INJECTION_REJECTED`/`INPUT_TOO_LONG`, body discarded); `post_process` S-3/S-4 always runs | PASS (`test_s2_injection_degrades_not_error`, `test_s2_oversize_degrades_not_error`, `TestGraphInvoke`) |
| TC-03 | No JWT/credential in State/src | `gate-credential-scan`: 0 violations; secrets redacted at S-2/S-3 | PASS (`test_credential_redacted_in_record`, `test_output_redacts_leaked_secret`) |
| TC-04 | InvocationContext not stored in State | State carries primitives only | PASS (`test_state_safety`) |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start`/`node_complete`/`node_error` absent from bodies | PASS (domain events only) |
| TC-06 | S-2 `_security_gate_input()` not overridden | `@final` enforced; only `_extra_*` extended | PASS |
| TC-07 | S-3 `_security_gate_output()` not overridden | `@final` enforced; only `_extra_*` extended | PASS |
| TC-08 | `required_trust_level` declared on every FunctionNode | `check_trust_level.py` PASS | PASS |
| TC-09 | S-2 `_extra_security_gate_input()` non-trivial | size cap + injection markers | PASS |
| TC-10 | S-3 `_extra_security_gate_output()` non-trivial | DRAFT-disclaimer preservation (may raise) | PASS (`test_gate_raises_when_disclaimer_missing`) |
| TC-11 | S-4: ≥1 domain `emit_trace_event()` per `execute()` path | event emitted on every path (incl. degraded) | PASS (`test_empty_degrades_but_audits`) |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Expected Result | Result |
|-------|----------|----------------|--------|
| PB-1 | `emit_trace_event()` fires on every path | No silent failures | PASS |
| PB-2 | Post-invoke State is primitives only | No Pydantic/dataclass | PASS (`test_state_safety`) |
| PB-3 | Template reaches domain services via L1 | Deterministic evidence synthesis | PASS |
| PB-4 | Import isolation — no Level 0 imports | AST scan: 0 violations | PASS (`test_import_isolation`) |
| PB-5 | Checkpoint safety — no JWT/Pydantic | Inspection pass | PASS |
| PB-6 | Invoke order: S-1 → node_start → S-2 → execute → S-3 → node_complete | Order verified (real SDK) | PASS in CI (the local SDK stub local diff) |
| PB-7 | HITL interrupt propagation *(conditional)* | **Auto-waived — non-HITL** (`hitl.enabled` unset → 2 SKIPPED) | Waived |

> **PB-7:** `config/agent.yaml` does not set `hitl.enabled: true`, so PB-7 is auto-waived (the scaffold
> stub emits SKIPPED and does not block the gate).

## Business Logic Tests

| BL-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Evidence chain ordering | 4 out-of-order records | Chronologically sorted, stable `EV-NNN` ids | PASS (`test_normalize_orders_and_chains`) |
| BL-02 | S-2 unauthorised-scope drop | record `access_scope=public` | dropped, `rejected_evidence_count` incremented | PASS (`test_normalize_drops_unauthorized_scope`) |
| BL-03 | Fact vs hypothesis split | objective signals + hedged note | facts vs hypotheses separated | PASS (`test_classify_facts_and_hypotheses`) |
| BL-04 | Multi-factor synthesis (no blame) | deploy + regression evidence | ≥2 contributing factors, no person/team attribution | PASS (`test_synthesize_multiple_factors_no_blame`) |
| BL-05 | HumanGate escalation | hypothesis present | `required=True`, `escalation=elevated`, review items | PASS (`test_human_gate_flags_hypothesis`) |
| BL-06 | Corrective actions unassigned | full draft | every action `owner=None`, `requires_human_assignment=True` | PASS (`test_corrective_actions_are_unassigned_proposals`) |
| BL-07 | 0-evidence out-of-scope safe answer | no authorised evidence | `status_kind=out_of_scope`, `citations=[]` | PASS (`test_out_of_scope_safe_when_no_authorized_evidence`) |
| BL-08 | Degraded path still audits | empty input | `status=SUCCESS`, `audit_logged=True` | PASS (`test_empty_degrades_but_audits`) |

## Test Execution Summary
- Total tests: 39 (unit 32 + integration 4 + proof_of_boundary 3 active; PB-7 = 2 SKIPPED)
- Pass: unit+integration 36 pass / 1 skip (server import — the local SDK stub). PB-6/PB-7 pass/skip in real SDK.
- Coverage: ~90% overall (core nodes/services 96–100%).
