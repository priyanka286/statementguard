# StatementGuard Architecture

## System Overview

StatementGuard is a 4-agent LangGraph pipeline that automates bank statement gap detection, triage, and resolution for corporate treasury operations.

## Agent Pipeline

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Ingestion  │───▶│   Triage    │───▶│  Outreach   │    │ Escalation  │
│    Agent    │    │    Agent    │    │    Agent    │    │   Agent     │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                   │
  Parse email        RAG + ToT          Draft email         Timer-based
  attachments       confidence          + create            follow-ups
  → JSON gaps        scoring             ticket             (async)
```

## Coordination Model

| Pattern | Where Used | Rationale |
|---------|-----------|-----------|
| Sequential | Ingestion → Triage → Outreach | Each stage depends on prior output |
| Iterative | Triage internal loop | ToT beam search evaluates multiple hypotheses |
| Event-driven | Escalation Agent | Fires on timers, not on pipeline completion |

## State Machine (LangGraph)

```python
graph = StateGraph(PipelineState)
graph.add_node("ingestion", ingestion_agent)
graph.add_node("triage", triage_agent)
graph.add_node("outreach", outreach_agent)
graph.add_edge(START, "ingestion")
graph.add_edge("ingestion", "triage")
graph.add_conditional_edges("triage", route_decision)  # suppress → END, escalate → outreach
graph.add_edge("outreach", END)
```

## Retrieval Strategy

**Hybrid approach:**
- **Structured (90%):** DynamoDB key lookups — bank + country + day_of_week → known pattern
- **Unstructured (10%):** ChromaDB vector search — cosine similarity against analyst knowledge base

**Why hybrid?** Most decisions are deterministic (holiday = suppress). Only novel/ambiguous cases need semantic reasoning. This keeps 90% of decisions fast (<10ms) and cheap (no LLM call).

## Tree-of-Thought (Triage)

When pattern lookup returns no match:
1. Generate 3 candidate hypotheses (beam width = 3)
2. Score each against available evidence
3. Select highest-scoring hypothesis
4. If max score < 0.8 → route to human analyst

## Guardrail Pipeline

```
Input → [Pre-gen] → [During-gen] → [Post-gen] → Output
          │              │              │
   Format check    Confidence     Content
   Calendar age     gate (0.8)    verification
```

## Data Flow

```
Monitoring Email (.xlsm)
  → Ingestion Agent (openpyxl parse)
    → List[AccountGap] (typed state)
      → Triage Agent (DynamoDB + ChromaDB + ToT)
        → List[TriageDecision] (suppress | escalate)
          → Outreach Agent (for escalated only)
            → List[OutreachDraft] (email + ticket)
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Orchestration | LangGraph | State machine with conditional edges |
| Vector Store | ChromaDB | Pattern similarity search |
| Key-Value Store | DynamoDB | Structured pattern lookups |
| LLM | GPT-4 | Triage reasoning, ToT scoring |
| Embeddings | text-embedding-ada-002 | Pattern indexing |
| Data Parsing | openpyxl | Excel .xlsm processing |
| Runtime | Python 3.11 | Scheduled pipeline execution |
