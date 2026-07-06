# StatementGuard — Video Narration Script (Final)
## Total time: ~9:40 minutes | 13 slides

---

## Slide 1: Title (0:00–0:25)

Hi, I'm Priyanka Mehrotra. This is StatementGuard — my capstone project for the CMU AI Agentic Systems program.

It's an autonomous multi-agent system that detects missing bank statements and resolves them — without human intervention for the eighty percent of cases that follow known patterns.

Let me show you why this matters.

---

## Slide 2: The Problem (0:25–1:45)

Corporate treasury teams monitor thousands of bank accounts daily for missing statements. At the scale I'm addressing, thirty-six hundred accounts, eighty banks, seven cycles per day across six regions, this is done entirely by hand.

Analysts spend three and a half to nine hours every day checking dashboards, filtering false positives based on patterns they carry in their heads, emailing banks, and tracking resolution in ad-hoc tickets.

Here's why this matters. Bank statements feed cash positioning. Cash positioning determines how much money sits in each account and drives funding decisions. If a statement is missing, the cash position is wrong. A wrong cash position can cause overdrafts, which damage the organization's credit rating and trigger bank fee charges.

Missing statements must be resolved by the next business day. If they are not, unreconciled transactions accumulate day over day. The backlog compounds. Analysts are now investigating yesterday's gaps plus today's, plus the day before.

The operational burden is high. Analysts track holidays across dozens of countries manually. Bank-specific delivery schedules are not documented anywhere. Back-and-forth email chains with banks cause churn and delays. And when experienced analysts are out, false positive rates jump to fifteen or twenty percent because the knowledge lives in their heads.

---

## Slide 3: Users and Stakes (1:45–2:10)

The intended users are Treasury Operations analysts who run daily monitoring cycles and Regional Treasury Center leads who manage escalations.

A false negative, missing a real gap, is far more costly than a false positive, which is just an unnecessary email to a bank. Undetected gaps lead to wrong cash positions, overdrafts, credit rating damage, bank fees, and compounding backlogs that grow with each day the gap remains open.

---

## Slide 4: System Goal (2:10–2:50)

The goal: reduce daily monitoring from up to nine hours to under thirty minutes.

Four quantified targets. False positive rate below two percent. False negative rate below one percent. Detection within five minutes. And analysts should only touch ten to twenty percent of cases, the ambiguous ones.

One non-negotiable constraint: this agent observes, triages, and communicates. It never touches financial data, payment instructions, or account configurations. In treasury, that boundary is absolute.

---

## Slide 5: Architecture (2:50–3:50)

As you can see in this diagram, four agents are coordinated by a LangGraph state machine.

Ingestion polls the monitoring mailbox, downloads Excel attachments, and produces structured JSON — a list of flagged accounts by bank and country. It feeds directly into Triage.

Triage is the decision engine. It pulls from three data sources — DynamoDB for structured patterns, ChromaDB for analyst knowledge, and a holiday calendar. It evaluates each account and assigns a confidence score. I'll go deeper on this next.

Outreach takes confirmed gaps, picks the right contact, drafts the email, sends it, and logs a ticket.

Escalation runs independently on timers. No response after four hours? Follow up. Eight hours? Escalate. This continues at twenty-four, forty-eight, and seventy-two hours.

Notice the human analyst connection at the top — they can override any Triage decision. The agents communicate through typed state objects, not free text. A parsing error in Ingestion can't corrupt Outreach for accounts already triaged.

---

## Slide 6: End-to-End Data Flow (3:50–4:20)

This slide shows the complete pipeline from left to right.

Emails arrive via Graph API polling. The Ingestion agent parses attachments into structured JSON. Pattern matching hits DynamoDB first — this resolves about eighty-five percent of cases deterministically. For the remainder, Tree-of-Thought reasoning generates and scores three hypotheses.

Then the decision gate. If confidence is at or above zero-point-eight, the gap is auto-suppressed — no action needed. If below, it escalates to Outreach, which drafts and sends a bank communication. Timer-based follow-ups cascade at four, eight, twenty-four, and forty-eight hours.

The entire pipeline runs in under five seconds per cycle. And the volume guardrail halts everything if more than forty percent of accounts are flagged — that signals a data source failure, not actual bank issues.

---

## Slide 7: Triage Deep Dive (4:20–5:35)

Triage is the heart of the system, so let me unpack it.

First layer: deterministic lookups. Bank code plus country plus day-of-week hits DynamoDB. Sub-millisecond. This resolves eighty-five to ninety percent of cases without any language model involved.

Second layer: vector similarity search. For the remaining cases, ChromaDB stores unstructured analyst knowledge — free-text overrides, edge cases, notes about specific banks.

Third layer: Tree-of-Thought. When the first two layers are inconclusive, the system generates three candidate explanations, scores each against available evidence, and prunes the weakest. If the winner scores below zero-point-eight confidence, it goes to a human.

Why does this matter? In early testing, single-pass reasoning would escalate the first account from Bangladesh before noticing that a regional holiday explained all twelve gaps from that country. Tree-of-Thought keeps competing hypotheses alive until one clearly wins.

---

## Slide 8: Safety and Guardrails (5:35–6:15)

Safety wasn't bolted on at the end. It was designed in from Module 6.

Three layers. Pre-generation: validate the attachment format, check that holiday calendars aren't stale. During generation: the zero-point-eight confidence gate prevents auto-action on anything uncertain. Post-generation: verify that outreach content matches source data — no hallucinated bank names or wrong account numbers.

Plus a volume anomaly detector. If forty percent of accounts are flagged in one cycle, that's not forty percent of banks failing. That's your data source broken. The system halts.

The fail-safe principle in one sentence: when uncertain, escalate. Never suppress.

---

## Slide 9: Design Evolution (6:15–7:15)

This is where the program's module structure really paid off. Each module's failure mode became the next module's design driver.

Module 2 — designing the reasoning loop — revealed that triage is the only non-trivial decision. Everything else is relatively mechanical.

Module 3 — building retrieval — exposed that the agent can't reason about bank patterns without access to institutional knowledge locked in analyst experience.

Module 4 — implementing Tree-of-Thought — solved the premature commitment problem where single-pass classification fails on correlated gaps.

Module 5 — multi-agent decomposition — addressed context limits and failure coupling that made a monolithic agent impractical.

Module 6 — safety — showed that guardrails, evaluation metrics, and human oversight aren't three concerns. They're one closed feedback loop.

Each transition has a clear logic: I hit a wall, I understood why, I redesigned.

---

## Slide 10: Working Demo (7:15–8:05)

The prototype is four hundred thirteen lines of Python using LangGraph. It runs end-to-end with synthetic data and simulated confidence scores. Live LLM integration requires an OpenAI API key not included in the public repo.

Three scenarios, each testing a different triage path.

Scenario one: Bangladesh Victory Day. Two accounts flagged from Dhaka. Holiday calendar match. Suppressed at zero-point-nine-five confidence.

Scenario two: End-of-Month Friday. Two accounts from banks with known Friday delays. Pattern match. Suppressed at zero-point-eight-five.

Scenario three: Multi-Region Monday. Four accounts, Singapore and US. Singapore: public holiday identified, suppressed. US: no pattern match, escalated. Outreach emails drafted automatically.

Aggregate: fifty percent suppressed, fifty percent escalated. Full pipeline under five seconds.

---

## Slide 11: Evaluation (8:05–8:35)

Let me be direct about what the numbers mean.

On three test scenarios: one hundred percent suppression accuracy, zero false positives, sub-five-second detection. Those look perfect — and that's the problem. Three scenarios with known answers isn't a real evaluation.

Production validation means running in shadow mode for thirty-plus days, comparing the agent's decisions against what human analysts actually did. That's the honest next step before trusting any accuracy claim.

---

## Slide 12: Next Steps (8:35–9:10)

Three things are designed but not implemented: the Escalation Agent's timer logic, full beam search in Triage, and live email integration.

The production path is methodical. First, shadow mode in one region for thirty days — measure real accuracy without risk. Then implement escalation. Then connect live email. Then fine-tune on analyst override data once enough accumulates. Then expand region by region: APAC, EMEA, Americas.

No big-bang rollout. Progressive trust.

---

## Slide 13: Summary (9:10–9:40)

Four things StatementGuard demonstrates.

One: multi-agent decomposition works for complex operational workflows — typed contracts prevent error cascading.

Two: hybrid retrieval — structured plus vector — handles the mix of deterministic and fuzzy enterprise knowledge.

Three: Tree-of-Thought reasoning solves premature commitment in classification under uncertainty.

Four: safety-first design means failing toward humans, never toward silence.

The agent doesn't replace analysts. It gives them back eighty percent of their day.

Code is live at github.com/priyanka286/statementguard.

Thank you.

---
