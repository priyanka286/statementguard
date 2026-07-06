# StatementGuard: An Autonomous Multi-Agent System for Bank Statement Gap Detection and Resolution

## Final Capstone Report
**Author:** Priyanka Mehrotra
**Date:** July 2026
**Program:** CMU AI Agentic Systems

---

## 1. Problem and User

Corporate treasury teams monitor thousands of bank accounts daily for missing statements. At the scale StatementGuard addresses (3,600+ accounts, 80+ banks, 7 daily cycles, 6 regions), this process is entirely manual. Analysts spend 3.5 to 9 hours per day checking dashboards, filtering false positives based on patterns they carry in their heads, emailing banks about gaps, and tracking resolution in ad-hoc tickets.

This monitoring matters because bank statements feed cash positioning. Cash positioning determines how much money sits in each account and drives funding decisions. If a statement is missing or contains incorrect transactions, the cash position is wrong. An incorrect cash position can cause overdrafts, which damage the organization's credit rating and trigger bank fee charges.

Missing statements must be resolved by the next business day. If they are not, unreconciled transactions accumulate day over day. This creates compounding operational overhead as analysts must investigate an ever-growing backlog instead of only the current day's gaps.

The operational burden is high. Analysts must track holidays across dozens of countries manually, understand bank-specific delivery schedules that are not documented anywhere, and manage back-and-forth email chains with banks that cause churn and delays. This process produces no metrics, does not scale, and depends on a few experienced analysts. When those analysts are unavailable, false positive rates spike to 15-20% and real gaps go undetected until month-end close.

The intended users are Treasury Operations analysts who run daily monitoring cycles and Regional Treasury Center leads who manage escalations.

A false negative (missing a real gap) is far more costly than a false positive (an unnecessary email to a bank). Undetected gaps lead to wrong cash positions, overdrafts, credit rating damage, bank fees, and compounding backlogs that grow with each day the gap remains open.

---

## 2. System Goal and Scope

StatementGuard reduces daily monitoring effort from 3.5-9 hours to under 30 minutes while maintaining a false positive rate below 2% and a false negative rate below 1%.

The system detects genuine gaps and escalates them within 5 minutes of the monitoring cycle window. It automatically suppresses known false positives (holidays, bank timing patterns, scheduled maintenance) with documented reasoning. It sends bank outreach within minutes rather than 30-60 minutes. Escalation timers fire automatically at defined thresholds (4h, 8h, 24h, 48h, 72h). Analysts review only the 10-20% of cases where the agent lacks confidence.

The agent observes, triages, and communicates. It never modifies financial data, payment instructions, or account configurations. All suppression decisions include an auditable reasoning trail. The system defaults to escalation (safe) when uncertain, never to suppression (risky). Human analysts retain final authority over all decisions.

---

## 3. Final System Architecture

StatementGuard comprises 4 specialized agents coordinated through a LangGraph state machine.

```
┌───────────┐     ┌───────────┐     ┌───────────┐
│ Ingestion │────>│  Triage   │────>│ Outreach  │
└───────────┘     └─────┬─────┘     └───────────┘
                        │
                        │ confidence < 0.8
                        v
                  ┌───────────┐
                  │  Human    │
                  │  Review   │
                  └───────────┘

                  ┌───────────┐
                  │ Escalation│  (async timers: 4h, 8h, 24h, 48h, 72h)
                  └───────────┘
```

**Agents:**

- **Ingestion Agent:** Polls a shared monitoring mailbox at 7 scheduled cycle windows. Downloads .xlsm attachments. Parses Excel data into structured JSON identifying which accounts are missing statements by bank and country.

- **Triage Agent:** Evaluates each flagged account against a pattern store containing holiday calendars, bank-specific delivery schedules, and historical timing data. Uses deterministic DynamoDB lookups to resolve an estimated 85-90% of cases. Routes ambiguous cases through Tree-of-Thought reasoning with beam search (width 3) to generate, score, and prune candidate explanations. Decisions below 0.8 confidence route to human review.

- **Outreach Agent:** Selects the appropriate bank contact and communication channel. Composes templated outreach, sends it, and creates a tracking ticket.

- **Escalation Agent:** Operates asynchronously on timers. Monitors elapsed time since outreach and triggers follow-ups at defined thresholds. Detects resolution (statement received) and auto-closes tickets.

**Coordination:**

The primary flow is sequential (Ingestion, Triage, Outreach), with Triage containing an internal iterative loop and Escalation running independently on event-driven timers. Agents communicate through typed, validated state objects, not free text. This prevents error cascading between stages.

**Retrieval:**

The Triage Agent uses a hybrid retrieval strategy. Structured patterns (bank + country + day-of-week) resolve via DynamoDB key lookups in sub-millisecond time. Unstructured knowledge (analyst free-text overrides, novel situations) uses vector similarity search against a ChromaDB pattern store with cosine similarity scoring.

**Guardrails:**

A 3-layer guardrail pipeline protects the system: pre-generation checks (attachment format validation, calendar freshness), during-generation checks (confidence threshold gate at 0.8), and post-generation checks (outreach content verification against source data). A volume anomaly detector halts processing if 40%+ of accounts are flagged in a single cycle.

**Human-in-the-loop:**

Low-confidence decisions, high-impact accounts (top-10 banking partners), novel patterns, and stale contacts all route to an analyst escalation queue. The system operates as a router, not a gatekeeper. Most decisions flow through automatically.

---

## 4. Design Evolution Across the Program

The initial concept was a monolithic monitoring agent. Designing the reasoning loop in Module 2 revealed that the triage step was the only non-trivial decision point. Everything else was relatively deterministic. This insight shaped all subsequent design decisions.

Building the ReAct loop in Module 3 exposed that the agent could not make triage decisions without access to institutional knowledge locked in analyst experience. This motivated the hybrid retrieval system: DynamoDB for structured patterns, vector search for unstructured analyst overrides.

Initial testing of single-pass triage in Module 4 showed premature commitment. The agent would escalate the first account before recognizing that a regional holiday explained all 12 gaps from that country. Tree-of-Thought with beam search solved this by keeping multiple explanations alive until the evidence clearly favored one.

The complexity of handling ingestion, triage, outreach, and escalation in a single agent exceeded practical context limits in Module 5. Decomposition into 4 agents with typed state contracts reduced failure coupling. A parsing error in Ingestion no longer blocks Outreach for already-triaged accounts.

Moving from "does it work?" to "is it safe?" in Module 6 added the guardrail pipeline, evaluation metrics, and the human-in-the-loop escalation queue. Guardrails, evaluation, and human intervention form a closed loop, not 3 separate concerns.

---

## 5. Implementation Overview

The system uses LangGraph for state machine orchestration with explicit conditional edges, ChromaDB for vector similarity search, DynamoDB for structured key-value lookups, GPT-4 for triage reasoning via OpenAI API, openpyxl for Excel parsing, text-embedding-ada-002 for pattern store indexing, and Python 3.11 as the runtime.

The prototype (agent_demo.py, 413 lines) runs end-to-end using synthetic data. It demonstrates the full Ingestion, Triage, and Outreach pipeline across 3 scenarios with simulated confidence scores. Live LLM integration (GPT-4 for triage reasoning) requires an OpenAI API key not included in the public repository.

1. Bangladesh Holiday: 2 accounts correctly suppressed (confidence 0.95)
2. End-of-Month Friday: 2 accounts suppressed based on pattern matching (confidence 0.85)
3. Multi-Region Monday: mixed suppression and escalation across Singapore and US accounts

50% of flagged accounts were auto-suppressed. The remainder were escalated with outreach drafted.

---

## 6. Evaluation and Results

The evaluation follows a 5-metric framework:

| Metric | Target | Demo Result |
|--------|--------|-------------|
| Suppression accuracy | > 95% | 100% (all suppressions correct in test scenarios) |
| False positive rate | < 2% | 0% (no incorrect outreach in demo) |
| Escalation rate | 10-20% | 50% (3 scenarios designed to test both paths) |
| Mean time to detection | < 5 min | < 5 seconds (demo pipeline) |
| Analyst override rate | < 10% | N/A (no live analyst in prototype) |

The evaluation used 3 hand-crafted scenarios testing distinct triage patterns (holiday suppression, timing pattern, genuine gap). Confidence scoring was verified against expected outcomes. End-to-end pipeline timing was measured. Outreach content was validated against source data.

The prototype uses simulated data with known correct answers. Production evaluation requires running in shadow mode alongside human analysts for 30+ days to measure real suppression accuracy and override rates.

---

## 7. Safety and Reliability Considerations

The pre-generation layer validates attachment format and blocks malformed inputs. A calendar freshness check forces human review when holiday data is stale.

The during-generation layer applies a confidence threshold at 0.8 that prevents auto-action on uncertain decisions.

The post-generation layer verifies that outreach content matches source data: bank name, account number, and contact all confirmed against the original flagged record.

A volume anomaly detector halts processing if 40%+ of accounts are flagged in a single cycle. This pattern indicates a data source failure, not 40% of banks failing simultaneously.

The agent cannot modify financial data, payment instructions, or account configurations.

Structured traces log every decision with confidence score, sources consulted, and action taken. A trace evaluator scores each run on correctness and safety dimensions.

If any component fails (calendar service down, email parsing error, contact registry unavailable), the system escalates everything rather than suppressing anything. The safest failure mode is always human involvement.

Analysts review low-confidence decisions, high-impact accounts, novel patterns, and repeated escalations. Every analyst override feeds back into the pattern store. This closes the learning loop: guardrails prevent bad actions, metrics detect drift, humans correct mistakes, corrections update the agent, fewer mistakes occur next cycle.

---

## 8. Limitations and Next Steps

The Escalation Agent (async timer-based follow-ups) is designed but not implemented in the prototype. The triage retry loop (beam search with re-evaluation) is described in architecture but the demo uses single-pass scoring. Live email integration requires token authentication not included in the public demo. Evaluation uses simulated scenarios with no production validation. The pattern store is pre-populated with synthetic data. Real deployment requires 30+ days of baseline collection.

The path to production is:

1. Shadow mode deployment: run alongside human analysts for 1 region (APAC) for 30 days, measuring real suppression accuracy before enabling auto-send
2. Escalation Agent implementation: add timer-based follow-up logic using event-driven architecture
3. Live email ingestion: connect to shared mailbox via Graph API polling for real monitoring data
4. Fine-tuning: once sufficient analyst override data accumulates, fine-tune (SFT) the triage model on confirmed patterns to reduce inference cost and latency
5. Multi-region expansion: progressive rollout from APAC to EMEA to Americas, 1 region at a time

---

## 9. Public GitHub Repository

**Repository:** [https://github.com/priyanka286/statementguard](https://github.com/priyanka286/statementguard)

The repository contains a README that explains the project, architecture, setup, and usage. It includes the working 3-scenario prototype (agent_demo.py), the LangGraph state machine implementation (agent_graph.py), Python dependencies (requirements.txt), sample inputs (synthetic bank data, holiday calendars in data/), architecture and evaluation documentation (docs/), and sample demo outputs showing suppression and escalation decisions (outputs/).

Setup: `pip install -r requirements.txt && python agent_demo.py`
