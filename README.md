# CMN-C2-669 — AI Incident Evidence Timeline & Postmortem Synthesis Agent

> **Category**: Cat 2 (domain workflow (a job to be done))
> **Industry**: Common (industry-agnostic)

## Overview

Given an incident id and a set of incident records (deployment changes, alerts, evaluation observations and operator notes, each with a timestamp, source and access scope), the agent drafts a postmortem: it validates the records and normalises their timestamps into a chronological timeline with provenance preserved, separates evidenced facts from hedged hypotheses using a signal-type taxonomy and hedge markers, maps the facts onto a causal structure of contributing factors (never a single cause and never a person or team), routes hypotheses, low-confidence factors and unassigned corrective actions to a human gate, and composes the draft with timeline, facts, hypotheses, contributing factors, corrective-action proposals with no owner assigned, and citations. All steps are deterministic — no LLM is in the execution path. Records outside the caller's authorised scope are dropped and credentials are redacted at intake and again on output; a record set with no usable evidence receives an out-of-scope answer with no citations, and every draft carries a DRAFT disclaimer.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | 3.11 or later (`requires-python = ">=3.11"`) |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and operational documentation
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
