# StatementGuard: An Autonomous Multi-Agent System for Bank Statement Gap Detection and Resolution

## Final Capstone Report — CMU AI Agentic Systems Program
**Author:** Priyanka Mehrotra  
**Date:** June 2026

---

## 1. Problem and User

Corporate treasury operations teams at large multinational organizations monitor thousands of bank accounts daily for missing statements. At the scale addressed by StatementGuard — 3,600+ accounts across 80+ banking partners, seven daily monitoring cycles spanning six global regions — this process is entirely manual. Analysts spend 3.5 to 9 hours per day navigating treasury management system dashboards, visually inspecting account statuses, mentally filtering false positives against undocumented bank-specific timing patterns, composing outreach emails to banks, and tracking resolution in ad-hoc tickets.

The process produces no reliable metrics, does not scale with account growth, and concentrates critical institutional knowledge in a few experienced analysts. When those analysts are unavailable, false positive rates spike to 15–20%, and genuine gaps may go undetected until month-end close — when they become urgent reconciliation problems.

**Intended users:** Treasury Operations analysts who execute daily monitoring cycles, and Regional Treasury Center leads who manage escalations and bank relationship conversations.

**Why it matters:** A missed bank statement can mask a significant reconciliation break — potentially millions of dollars in unreconciled transactions. The cost of a false negative (missing a real gap) far exceeds the cost of a false positive (unnecessarily contacting a bank).

---

## 2. System Goal and Scope

**Goal:** Reduce daily monitoring effort from 3.5–9 hours to under 30 minutes while maintaining a false positive rate below 2% and a false negative rate below 1%.

**What success looks like:**
- Genuine gaps are detected and escalated within 5 minutes of the monitoring cycle window
- Known false positives (holidays, bank timing patterns, scheduled maintenance) are automatically suppressed with documented reasoning
- Bank outreach is sent within minutes rather than 30–60 minutes
- Escalation timers fire automatically at defined thresholds (4h → 8h → 24h → 48h → 72h)
- Analysts review only the 10–20% of cases where the agent lacks confidence

**Boundaries and constraints:**
- The agent observes, triages, and communicates — it never modifies financial data, payment instructions, or account configurations
- All suppression decisions include an auditable reasoning trail
- The system defaults to escalation (safe) when uncertain, never to suppression (risky)
- Human analysts retain final authority over all decisions

---

## 3. Final System Architecture

StatementGuard comprises four specialized agents coordinated through a LangGraph state machine:

**Ingestion Agent** polls a shared monitoring mailbox at seven scheduled cycle windows, downloads .xlsm attachments, and parses Excel data into structured JSON identifying which accounts are missing statements by bank and country.

**Triage Agent** evaluates each flagged account against a pattern store containing holiday calendars, bank-specific delivery schedules, and historical timing data. It uses a hybrid approach: deterministic DynamoDB lookups resolve 85–90% of cases; the remaining ambiguous cases undergo Tree-of-Thought reasoning with beam search (width 3) to generate, score, and prune candidate explanations. Decisions below 0.8 confidence are routed to human review.

**Outreach Agent** selects the appropriate bank contact and communication channel, composes templated outreach, sends it, and creates a tracking ticket.

**Escalation Agent** operates asynchronously on timers, monitoring elapsed time since outreach and triggering follow-ups at defined thresholds. It detects resolution (statement received) and auto-closes tickets.

**Coordination:** The primary flow is sequential (Ingestion → Triage → Outreach), with Triage containing an internal iterative loop and Escalation running independently on event-driven timers. Agents communicate through typed, validated state objects — not free text — preventing error cascading between stages.

**Retrieval:** The Triage Agent uses a hybrid retrieval strategy. Structured patterns (bank + country + day-of-week) resolve via DynamoDB key lookups in sub-millisecond time. Unstructured knowledge (analyst free-text overrides, novel situations) uses vector similarity search against a ChromaDB pattern store with cosine similarity scoring.

**Guardrails:** A three-layer pipeline protects the system: pre-generation checks (attachment format validation, calendar freshness), during-generation checks (confidence threshold gate at 0.8), and post-generation checks (outreach content verification against source data). A volume anomaly detector halts processing if 40%+ of accounts are flagged in a single cycle.

**Human-in-the-loop:** Low-confidence decisions, high-impact accounts (top-10 banking partners), novel patterns, and stale contacts all route to an analyst escalation queue. The system operates as a router, not a gatekeeper — most decisions flow through automatically.

---

## 4. Design Evolution Across the Program

**Module 1 → 2 (Problem → Reasoning):** The initial concept was a monolithic monitoring agent. Designing the reasoning loop revealed that the triage step was the critical decision point — everything else was relatively deterministic. This insight shaped all subsequent design decisions.

**Module 2 → 3 (Reasoning → Retrieval):** Building the ReAct loop exposed that the agent could not make triage decisions without access to institutional knowledge locked in analyst experience. This motivated the hybrid retrieval system — DynamoDB for structured patterns, vector search for unstructured analyst overrides.

**Module 3 → 4 (Retrieval → Tree-of-Thought):** Initial testing of single-pass triage showed premature commitment — the agent would escalate the first account before recognizing that a regional holiday explained all 12 gaps from that country. ToT with beam search solved this by keeping multiple explanations alive until the evidence clearly favored one.

**Module 4 → 5 (ToT → Multi-Agent):** The complexity of handling ingestion, triage, outreach, and escalation in a single agent exceeded practical context limits. Decomposition into four agents with typed state contracts reduced failure coupling — a parsing error in Ingestion no longer blocks Outreach for already-triaged accounts.

**Module 5 → 6 (Architecture → Safety):** Moving from "does it work?" to "is it safe?" added the guardrail pipeline, evaluation metrics, and the human-in-the-loop escalation queue. The key insight was that guardrails, evaluation, and human intervention form a closed loop — not three separate concerns.

---

## 5. Implementation Overview

**Framework:** LangGraph (state machine orchestration with explicit conditional edges)  
**Retrieval:** ChromaDB (vector similarity search for bank patterns) + DynamoDB (structured key-value lookups)  
**Language model:** GPT-4 (triage reasoning and evaluation) via OpenAI API  
**Data parsing:** openpyxl (Excel .xlsm attachment parsing)  
**Embedding:** text-embedding-ada-002 (pattern store indexing)  
**Visualization:** Mermaid (architecture diagrams), matplotlib (metrics)  
**Runtime:** Python 3.11, deployed as a scheduled pipeline

The working prototype (`agent_demo.py`, 413 lines) demonstrates the full Ingestion → Triage → Outreach pipeline across three representative scenarios:
1. Bangladesh Holiday — 2 accounts correctly suppressed (confidence 0.95)
2. End-of-Month Friday — 2 accounts suppressed based on pattern matching (confidence 0.85)
3. Multi-Region Monday — mixed suppression and escalation across Singapore and US accounts

Aggregate result: 50% of flagged accounts auto-suppressed, remainder escalated with outreach drafted.

---

## 6. Evaluation and Results

**Metrics used (following the 5-Metric Rule):**

| Metric | Target | Demo Result |
|--------|--------|-------------|
| Suppression accuracy | > 95% | 100% (all suppressions correct in test scenarios) |
| False positive rate | < 2% | 0% (no incorrect outreach in demo) |
| Escalation rate | 10–20% | 50% (3 scenarios designed to test both paths) |
| Mean time to detection | < 5 min | < 5 seconds (demo pipeline) |
| Analyst override rate | < 10% | N/A (no live analyst in prototype) |

**Evaluation approach:**
- Three hand-crafted scenarios testing distinct triage patterns (holiday suppression, timing pattern, genuine gap)
- Confidence scoring verified against expected outcomes
- End-to-end pipeline timing measured
- Outreach content validated against source data

**Limitations of current evaluation:** The prototype uses simulated data with known correct answers. Production evaluation would require running in shadow mode alongside human analysts for 30+ days to measure real suppression accuracy and override rates.

---

## 7. Safety and Reliability Considerations

**Guardrails:**
- Pre-generation: Attachment format validator blocks malformed inputs; calendar freshness check forces human review when holiday data is stale
- During-generation: Confidence threshold (0.8) prevents auto-action on uncertain decisions
- Post-generation: Outreach content verifier confirms bank name, account, and contact match source data
- Runtime: Volume anomaly detector halts processing if 40%+ accounts flagged (likely data source failure)
- Tool access: Agent cannot modify financial data, payment instructions, or account configurations

**Monitoring:** Structured traces log every decision with confidence score, sources consulted, and action taken. A trace evaluator scores each run on correctness and safety dimensions.

**Fallback logic:** If any component fails (calendar service down, email parsing error, contact registry unavailable), the system escalates everything rather than suppressing anything. The safest failure mode is always human involvement.

**Human oversight:** Analysts review low-confidence decisions, high-impact accounts, novel patterns, and repeated escalations. Every analyst override feeds back into the pattern store, closing the learning loop.

**Feedback loop:** Guardrails prevent bad actions → Metrics detect drift → Humans correct mistakes → Corrections update the agent → Fewer mistakes next cycle.

---

## 8. Limitations and Next Steps

**Current limitations:**
- Escalation Agent (async timer-based follow-ups) is designed but not yet implemented in the prototype
- Triage retry loop (beam search with re-evaluation) is described in architecture but the demo uses single-pass scoring
- Live email integration requires token authentication that is not included in the public demo
- Evaluation uses simulated scenarios — no production validation yet
- Pattern store is pre-populated with synthetic data; real deployment requires 30+ days of baseline collection

**Realistic next steps:**
1. **Shadow mode deployment** — Run alongside human analysts for one region (APAC) for 30 days, measuring real suppression accuracy before enabling auto-send
2. **Escalation Agent implementation** — Add timer-based follow-up logic using event-driven architecture
3. **Live email ingestion** — Connect to shared mailbox via Graph API polling for real monitoring data
4. **Fine-tuning** — Once sufficient analyst override data accumulates, fine-tune (SFT) the Triage model on confirmed patterns to reduce inference cost and latency
5. **Multi-region expansion** — Progressive rollout: APAC → EMEA → Americas, one region at a time

---

## 9. Public GitHub Repository

**Repository:** [Link to be added upon creation]

The repository contains:
- `README.md` — Project overview, architecture diagram, setup instructions, usage guide
- `agent_demo.py` — Working 3-scenario prototype demonstrating the full pipeline
- `agent_graph.py` — LangGraph state machine implementation
- `requirements.txt` — Python dependencies
- `data/` — Sample inputs (synthetic bank data, holiday calendars)
- `docs/` — Architecture diagram, evaluation results
- `outputs/` — Sample demo outputs showing suppression and escalation decisions

Setup: `pip install -r requirements.txt && python agent_demo.py`
