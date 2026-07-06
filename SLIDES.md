# StatementGuard — Capstone Presentation Slides
## CMU AI Agentic Systems Program | Priyanka Mehrotra | July 2026

---

## Slide 1: Title

**StatementGuard**
*An Autonomous Multi-Agent System for Bank Statement Gap Detection and Resolution*

- Priyanka Mehrotra
- CMU AI Agentic Systems — Capstone Project
- July 2026

---

## Slide 2: The Problem

**Daily bank statement monitoring at enterprise scale is broken.**

- 3,600+ accounts | 80+ banks | 7 daily cycles | 6 global regions
- Analysts spend 3.5–9 hours/day on manual inspection
- False positive rates spike to 15–20% when experienced staff are unavailable
- Institutional knowledge is undocumented and concentrated in a few people
- A missed gap can mask millions in unreconciled transactions

*The cost of a false negative far exceeds the cost of a false positive.*

---

## Slide 3: Users and Stakes

**Primary users:**
- Treasury Operations analysts (execute daily monitoring)
- Regional Treasury Center leads (manage escalations)

**What's at stake:**
- Month-end close delays
- Undetected reconciliation breaks
- Banking relationship damage from repeated unnecessary outreach
- No reliable metrics on process health

---

## Slide 4: System Goal

**Reduce monitoring from 3.5–9 hours to under 30 minutes.**

| Metric | Target |
|--------|--------|
| False positive rate | < 2% |
| False negative rate | < 1% |
| Time to detection | < 5 minutes |
| Analyst review load | Only 10–20% of cases |

**Key constraint:** The agent observes, triages, and communicates — it *never* modifies financial data.

---

## Slide 5: Architecture — Four Agents

```
[Ingestion] → [Triage] → [Outreach]
                              ↓
                        [Escalation] (async timers)
```

| Agent | Role |
|-------|------|
| Ingestion | Parse monitoring emails, extract flagged accounts |
| Triage | Evaluate against patterns, assign confidence scores |
| Outreach | Draft and send bank communications |
| Escalation | Timer-based follow-ups (4h → 8h → 24h → 48h → 72h) |

**Coordination:** LangGraph state machine with typed state contracts between agents.

---

## Slide 6: Triage — The Critical Decision

**Hybrid retrieval strategy:**
- **DynamoDB** — Structured lookups (bank + country + day-of-week) resolve 85–90% of cases
- **ChromaDB** — Vector similarity search for unstructured analyst knowledge

**Tree-of-Thought reasoning (ambiguous cases):**
- Generate 3 candidate explanations
- Score each against evidence
- Prune below threshold
- Route to human if confidence < 0.8

*Example: A regional holiday explains all 12 gaps from Bangladesh — single-pass would escalate the first account before seeing the pattern.*

---

## Slide 7: Safety and Guardrails

**Three-layer protection pipeline:**

| Layer | Check |
|-------|-------|
| Pre-generation | Attachment validation, calendar freshness |
| During-generation | Confidence gate (0.8 threshold) |
| Post-generation | Outreach content verified against source |

**Additional safeguards:**
- Volume anomaly halt: 40%+ flagged → stop processing (likely data source failure)
- Fail-safe default: When uncertain, escalate — never suppress
- No access to modify financial data, payments, or account configs

---

## Slide 8: Design Evolution

| Transition | Key Insight |
|-----------|-------------|
| Problem → Reasoning | Triage is the only non-trivial decision |
| Reasoning → Retrieval | Agent can't decide without institutional knowledge |
| Retrieval → ToT | Single-pass commits too early; need parallel hypotheses |
| ToT → Multi-Agent | Single agent exceeds context limits; decompose |
| Architecture → Safety | Guardrails + evaluation + humans form a closed loop |

*Each module built on the prior module's limitations.*

---

## Slide 9: Working Demo

**Prototype:** `agent_demo.py` (413 lines, Python + LangGraph)

**Three test scenarios:**
1. **Bangladesh Holiday** — 2 accounts suppressed (confidence 0.95)
2. **End-of-Month Friday** — 2 accounts suppressed (confidence 0.85)
3. **Multi-Region Monday** — Mixed: Singapore suppressed, US escalated

**Result:** 50% auto-suppressed, 50% escalated with outreach drafted.

*Demo runs end-to-end in < 5 seconds.*

---

## Slide 10: Evaluation Results

| Metric | Target | Result |
|--------|--------|--------|
| Suppression accuracy | > 95% | 100% |
| False positive rate | < 2% | 0% |
| Escalation rate | 10–20% | 50% |
| Time to detection | < 5 min | < 5 sec |
| Analyst override rate | < 10% | N/A |

**Honest limitation:** Results are from 3 hand-crafted scenarios with known answers. Production validation requires 30+ days of shadow-mode operation alongside human analysts.

---

## Slide 11: Limitations and Next Steps

**Not yet implemented:**
- Escalation Agent (async timer logic)
- Full beam search in Triage (demo uses single-pass)
- Live email integration (requires auth tokens)

**Realistic path to production:**
1. Shadow mode — 1 region, 30 days, measure real accuracy
2. Escalation Agent — timer-based follow-ups
3. Live email ingestion — Graph API polling
4. Fine-tuning — SFT on analyst override data
5. Multi-region rollout — APAC → EMEA → Americas

---

## Slide 12: Summary and Key Takeaways

**StatementGuard demonstrates:**
- Multi-agent decomposition for complex operational workflows
- Hybrid retrieval (structured + vector) for enterprise knowledge
- Tree-of-Thought for ambiguous classification under uncertainty
- Safety-first design: fail toward humans, never toward silence

**The agent doesn't replace analysts — it gives them back 80% of their day.**

**Repository:** github.com/priyanka286/statementguard

---
