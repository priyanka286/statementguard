# StatementGuard

An autonomous multi-agent system for detecting, triaging, and resolving missing bank statements in corporate treasury operations.

## Problem

Corporate treasury teams monitor thousands of bank accounts daily for missing statements. At scale (3,600+ accounts, 80+ banks, 6 global regions, 7 daily cycles), this manual process takes 3.5–9 hours per day and produces a 15–20% false positive rate. StatementGuard automates this workflow, reducing monitoring time to under 30 minutes with a <2% false positive target.

## Architecture

StatementGuard uses a **4-agent LangGraph pipeline**:

```
Ingestion → Triage → Outreach → Escalation (async)
```

| Agent | Role |
|-------|------|
| **Ingestion** | Parses monitoring emails and Excel attachments into structured gap data |
| **Triage** | Classifies gaps as suppress (false alarm) or escalate (genuine) using RAG + Tree-of-Thought |
| **Outreach** | Sends templated communication to the correct bank contact |
| **Escalation** | Monitors elapsed time and triggers follow-ups at 4h/8h/24h/48h/72h |

### Key Design Decisions

- **LangGraph over CrewAI**: Explicit state graph gives deterministic routing; CrewAI's autonomous delegation adds unpredictability inappropriate for financial workflows
- **Hybrid retrieval**: DynamoDB for structured patterns (90% of lookups), ChromaDB vector search for unstructured analyst knowledge (10%)
- **Tree-of-Thought in Triage**: Beam search (width 3) generates multiple candidate explanations before committing — prevents premature escalation when a regional holiday explains all gaps
- **Confidence-gated HITL**: Decisions below 0.8 confidence route to human analyst review

## Demo

The prototype demonstrates the full Ingestion → Triage → Outreach pipeline across 3 scenarios:

```bash
pip install -r requirements.txt
python agent_demo.py
```

**Sample output:**
- Scenario 1 (Bangladesh Holiday): 2 accounts suppressed, confidence 0.95
- Scenario 2 (End-of-Month Friday): 2 accounts suppressed, confidence 0.85  
- Scenario 3 (Multi-Region Monday): 2 suppressed + 2 escalated with outreach drafted
- **Aggregate: 50% auto-suppressed, 50% escalated**

## Project Structure

```
├── agent_demo.py          # Full 3-scenario capstone demo (413 lines)
├── agent_graph.py         # LangGraph state machine prototype
├── requirements.txt       # Python dependencies
├── data/
│   ├── sample_gaps.json   # Synthetic missing statement data
│   └── holidays.json      # Sample holiday calendar
├── docs/
│   ├── architecture.md    # Detailed architecture description
│   └── evaluation.md      # Metrics and results
└── outputs/
    └── demo_output.txt    # Sample run output
```

## Guardrails & Safety

| Layer | Guardrail | Purpose |
|-------|-----------|---------|
| Pre-generation | Attachment validator | Blocks malformed inputs |
| Pre-generation | Calendar freshness | Forces human review if holiday data is stale |
| During-generation | Confidence gate (0.8) | Routes uncertain decisions to analyst |
| Post-generation | Outreach verifier | Confirms bank/account/contact match source |
| Runtime | Volume anomaly (40%) | Halts if likely data source failure |

**Safe failure mode**: When uncertain or broken, the system escalates everything rather than suppressing anything.

## Evaluation Metrics

| Metric | Target | Demo Result |
|--------|--------|-------------|
| Suppression accuracy | > 95% | 100% |
| False positive rate | < 2% | 0% |
| Mean time to detection | < 5 min | < 5 sec |
| Escalation rate | 10–20% | 50% (test scenarios) |

## Limitations

- Escalation Agent (async timers) is designed but not implemented in prototype
- Triage uses single-pass scoring; beam search ToT loop is architecture-only
- Evaluation uses synthetic scenarios — no production validation yet
- Pattern store is pre-populated; real deployment requires 30+ days of baseline

## Tech Stack

- **Orchestration**: LangGraph
- **Vector store**: ChromaDB
- **Data parsing**: openpyxl
- **Language model**: OpenAI GPT-4
- **Embeddings**: text-embedding-ada-002
- **Runtime**: Python 3.11

## Author

Priyanka Mehrotra — CMU AI Agentic Systems Program, June 2026

## License

MIT
