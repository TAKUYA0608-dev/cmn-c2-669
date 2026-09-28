"""CMN-C2-669 — Agent state (AI Incident Evidence Timeline & Postmortem Synthesis, Cat 2).

ADR-005: State is a flat ``TypedDict`` — never a validation/BaseModel instance. Complex fields are
stored as JSON strings (``NotRequired[str]`` + ``# JSON:``); nodes ``json.dumps`` on write /
``json.loads`` on read so every field stays msgpack-serialisable (checkpoint-safe).

Post-incident, advisory-only: the agent synthesises a Postmortem Draft from **authorised** incident
records. It never touches production, never contains a person/team attribution (no blame), and any
secret inadvertently present in evidence is redacted at S-2 (input) and S-3 (output) — defence in depth.

All agent-specific fields are ``NotRequired`` (populated progressively; absent at empty-start invoke).
"""

from __future__ import annotations


from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for the incident postmortem-synthesis workflow."""

    # ── pre_process (EvidenceValidate, S-1 sanitise + S-2 authorised-scope gate) ──
    validated_input: str  # JSON: {incident_id, records:[...], taxonomy_hint}
    input_format: str  # "json" | "text" | "empty"
    enriched_context: str  # JSON: {source, channel} (read-only caller context)
    rejected_evidence_count: int  # records dropped by the S-2 access-scope check

    # ── inner workflow (timeline → fact/hypothesis → factors → human-gate → compose) ──
    normalized_timeline: str  # JSON: [{evidence_id, ts, type, source, access_scope, summary}]
    evidence_count: int  # valid evidence entries (0 → out-of-scope safe answer)
    fact_hypothesis: str  # JSON: {facts:[...], hypotheses:[...]}
    contributing_factors: str  # JSON: [{factor, category, evidence_ids, confidence}]
    human_review: str  # JSON: {required, escalation, material_review_items}
    result: str  # JSON: assembled Postmortem Draft (deliverable)

    # ── post_process (S-3 output gate + citation + S-4 audit) ──
    formatted_output: str  # JSON: final response envelope (draft + DRAFT disclaimer)
    disclaimer: str  # mandatory DRAFT / "final postmortem is a human decision" note
    audit_logged: bool  # True once the terminal audit event is emitted

    # ── degraded-path signalling (SUCCESS + error_code, never status=ERROR) ──
    error_code: str  # INPUT_REJECTED | INPUT_TOO_LONG | NO_EVIDENCE
    error_message: str  # operator-facing detail
