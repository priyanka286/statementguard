# StatementGuard Evaluation Results

## Evaluation Framework

Following the **5-Metric Rule** from Module 6 (Evaluation, Guardrails, and Observability):

## Metrics

| Metric | Target | Demo Result | Notes |
|--------|--------|-------------|-------|
| Suppression accuracy | > 95% | 100% | All suppressions matched ground truth |
| False positive rate | < 2% | 0% | No incorrect outreach sent |
| Escalation rate | 10–20% | 25% | 2/8 accounts escalated (demo designed to test both paths) |
| Mean time to detection | < 5 min | < 2 sec | Full pipeline per scenario |
| Analyst override rate | < 10% | N/A | No live analyst in prototype |

## Test Scenarios

### Scenario 1: Bangladesh Holiday
- **Input:** 2 accounts flagged (Standard Chartered, BD)
- **Expected:** Suppress — Eid al-Adha public holiday
- **Result:** ✅ Suppressed with confidence 0.95
- **Method:** Direct holiday calendar lookup (DynamoDB)

### Scenario 2: End-of-Month Friday
- **Input:** 2 accounts flagged (Citibank, KR)
- **Expected:** Suppress — known timing pattern
- **Result:** ✅ Suppressed with confidence 0.85
- **Method:** RAG vector search (ChromaDB, cosine 0.91)

### Scenario 3: Multi-Region Monday
- **Input:** 4 accounts flagged (DBS SG, HSBC SG, JPMorgan US)
- **Expected:** Mixed — 2 suppress (HSBC pattern), 2 escalate (no pattern)
- **Result:** ✅ Correct split — HSBC suppressed, DBS + JPMorgan escalated
- **Method:** Combination of RAG match + ToT beam search

## Confidence Calibration

| Confidence Range | Expected Action | Observed |
|-----------------|-----------------|----------|
| 0.90–1.00 | Auto-suppress | ✅ Scenario 1 (0.95) |
| 0.80–0.89 | Auto-suppress with logging | ✅ Scenario 2 (0.85), HSBC (0.88) |
| 0.70–0.79 | Route to human review | ✅ DBS (0.72) |
| < 0.70 | Auto-escalate | ✅ JPMorgan (0.65) |

## Guardrail Validation

| Guardrail | Triggered | Outcome |
|-----------|-----------|---------|
| Calendar freshness | No | Calendar data was current |
| Confidence gate (0.8) | Yes (2×) | DBS and JPMorgan correctly escalated |
| Volume anomaly (40%) | No | Only 25% escalation rate |
| Outreach content check | Yes (2×) | Bank/account/contact verified before send |

## Limitations

1. **Simulated data** — All scenarios use hand-crafted inputs with known correct answers
2. **Small sample** — 3 scenarios (8 accounts) is insufficient for statistical significance
3. **No adversarial testing** — Edge cases (corrupted files, stale calendars, novel banks) not tested
4. **No temporal evaluation** — Single-point-in-time; no drift detection over days/weeks
5. **No human comparison** — Would need 30+ days of parallel human + agent decisions to validate

## Production Evaluation Plan

1. **Shadow mode (30 days):** Run agent alongside human analysts; compare decisions without auto-acting
2. **Metric collection:** Track suppression accuracy, override rate, and time-to-detection vs. human baseline
3. **A/B rollout:** Enable auto-suppress for high-confidence decisions (>0.95) first; expand threshold over time
4. **Drift monitoring:** Alert if suppression rate changes >10% week-over-week
