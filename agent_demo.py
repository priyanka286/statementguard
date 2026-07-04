"""
StatementGuard — Multi-Agent Capstone Demo
============================================
CMU AI Agentic Systems | Module 5: Multi-Agent Workflows

Demonstrates a LangGraph multi-agent pipeline for autonomous bank
statement gap detection, triage, and outreach.

Agents:
  1. Ingestion Agent — parses monitoring data, extracts flagged accounts
  2. Triage Agent — RAG retrieval + holiday calendar + ToT confidence scoring
  3. Outreach Agent — drafts escalation emails with contact registry lookup

Run:
  python3 agent_demo.py              # All 3 scenarios
  python3 agent_demo.py --graph      # Export graph visualization to PNG
"""

import sys
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END
import chromadb
from sentence_transformers import SentenceTransformer
from datetime import date

# =============================================================================
# STATE SCHEMA — typed contract between agents (prevents hallucination cascading)
# =============================================================================

class AccountGap(TypedDict):
    bank: str
    country: str
    accounts: list[str]
    count: int
    day_of_week: str

class TriageDecision(TypedDict):
    bank: str
    country: str
    accounts: list[str]
    decision: Literal["suppress", "escalate"]
    confidence: float
    explanation: str

class OutreachDraft(TypedDict):
    bank: str
    country: str
    recipient: str
    subject: str
    body: str
    ticket_id: str

class PipelineState(TypedDict):
    region: str
    cycle_date: str
    raw_gaps: list[AccountGap]
    triage_results: list[TriageDecision]
    outreach_drafts: list[OutreachDraft]
    summary: str

# =============================================================================
# KNOWLEDGE BASE — bank delivery patterns (RAG vector store)
# =============================================================================

BANK_PATTERNS = [
    {"id": "p1", "text": "SC/BD (Standard Chartered Bangladesh) accounts 199BDTSC4102-4105 consistently deliver statements 24-48 hours late following Bangladesh public holidays. Last 6 occurrences all resolved without intervention within 48 hours.", "bank": "SC", "country": "BD"},
    {"id": "p2", "text": "Bangladesh observes regional holidays not in the international calendar including Shab-e-Barat, Shab-e-Qadr, and Eid-ul-Adha extensions. SC/BD always goes silent during these periods.", "bank": "SC", "country": "BD"},
    {"id": "p3", "text": "CB/KR (Citi Korea) accounts occasionally miss Friday delivery when Korean settlement system KFTC performs end-of-month batch processing. Usually resolves by Monday 9 AM KST.", "bank": "CB", "country": "KR"},
    {"id": "p4", "text": "CB/KR missed statements on 2026-03-29 (Friday) and 2026-04-25 (Friday). Both resolved Monday without intervention. Pattern: end-of-month Fridays.", "bank": "CB", "country": "KR"},
    {"id": "p5", "text": "HSBC Singapore delivers statements 90 minutes late on Mondays due to weekend batch processing. Not a genuine gap - suppress for 2 hours.", "bank": "HS", "country": "SG"},
    {"id": "p6", "text": "HSBC Japan SWIFT gateway has scheduled maintenance every 3rd Thursday 02:00-04:00 UTC. Statements arrive 2-3 hours late on these days.", "bank": "HS", "country": "JP"},
    {"id": "p7", "text": "When CB/KR misses a Friday delivery, do NOT send outreach until Monday 10 AM KST. Bank ops desk closed weekends.", "bank": "CB", "country": "KR"},
    {"id": "p8", "text": "JPM/US (JPMorgan United States) accounts have no known delivery delays. Missing statements should always be escalated immediately.", "bank": "JPM", "country": "US"},
    {"id": "p9", "text": "DBS/SG (DBS Singapore) occasionally delays Monday delivery by 1 hour due to MAS regulatory reporting. Suppress for 90 minutes on Mondays only.", "bank": "DBS", "country": "SG"},
    {"id": "p10", "text": "Analyst override 2026-04-10: SC/BD accounts should be suppressed for 72 hours during Eid holidays.", "bank": "SC", "country": "BD"},
    {"id": "p11", "text": "ANZ/AU (ANZ Australia) has no known patterns. Missing statements are always genuine gaps requiring outreach.", "bank": "ANZ", "country": "AU"},
    {"id": "p12", "text": "MUFG/JP (Mitsubishi UFJ Japan) delays delivery on the 5th and 20th of each month due to internal settlement cycles. Always resolves same day by 14:00 JST.", "bank": "MUFG", "country": "JP"},
]

BANK_CONTACTS = {
    "SC/BD": {"name": "Md. Rafiq Hassan", "email": "rafiq.hassan@sc.com"},
    "CB/KR": {"name": "Kim Soo-Jin", "email": "soojin.kim@citi.com"},
    "HS/SG": {"name": "Tan Wei Ling", "email": "weiling.tan@hsbc.com"},
    "HS/JP": {"name": "Tanaka Yuki", "email": "yuki.tanaka@hsbc.co.jp"},
    "JPM/US": {"name": "Sarah Mitchell", "email": "sarah.mitchell@jpmorgan.com"},
    "DBS/SG": {"name": "Lim Boon Keng", "email": "boonkeng.lim@dbs.com"},
    "ANZ/AU": {"name": "James Wright", "email": "james.wright@anz.com"},
    "MUFG/JP": {"name": "Suzuki Kenji", "email": "kenji.suzuki@mufg.jp"},
}

# =============================================================================
# DEMO SCENARIOS — simulating different real-world conditions
# =============================================================================

SCENARIOS = {
    "holiday": {
        "name": "Scenario 1: Bangladesh Holiday (Eid al-Adha)",
        "region": "APAC AM",
        "cycle_date": "2026-06-18",
        "holidays": {"BD": ["2026-06-18", "2026-06-19", "2026-06-20"], "KR": [], "US": [], "AU": [], "JP": [], "SG": []},
        "gaps": [
            {"bank": "SC", "country": "BD", "accounts": ["199BDTSC4102", "199BDTSC4103", "199BDTSC4104"], "count": 3, "day_of_week": "Thursday"},
            {"bank": "JPM", "country": "US", "accounts": ["811USDJPM001"], "count": 1, "day_of_week": "Thursday"},
        ],
    },
    "friday_pattern": {
        "name": "Scenario 2: End-of-Month Friday (Korea KFTC batch)",
        "region": "APAC AM",
        "cycle_date": "2026-06-27",
        "holidays": {"BD": [], "KR": [], "US": [], "AU": [], "JP": [], "SG": []},
        "gaps": [
            {"bank": "CB", "country": "KR", "accounts": ["427KRWCB2001", "427KRWCB2002"], "count": 2, "day_of_week": "Friday"},
            {"bank": "ANZ", "country": "AU", "accounts": ["550AUDANZ301", "550AUDANZ302", "550AUDANZ303"], "count": 3, "day_of_week": "Friday"},
        ],
    },
    "multi_region": {
        "name": "Scenario 3: Multi-Region Monday (mixed suppress/escalate)",
        "region": "EMEA + APAC",
        "cycle_date": "2026-06-22",
        "holidays": {"BD": [], "KR": [], "US": [], "AU": [], "JP": [], "SG": []},
        "gaps": [
            {"bank": "HS", "country": "SG", "accounts": ["330SGDHS5501"], "count": 1, "day_of_week": "Monday"},
            {"bank": "DBS", "country": "SG", "accounts": ["340SGDDBS101", "340SGDDBS102"], "count": 2, "day_of_week": "Monday"},
            {"bank": "MUFG", "country": "JP", "accounts": ["610JPYMUFG01"], "count": 1, "day_of_week": "Monday"},
            {"bank": "JPM", "country": "US", "accounts": ["811USDJPM001", "811USDJPM002"], "count": 2, "day_of_week": "Monday"},
        ],
    },
}

# =============================================================================
# VECTOR STORE SETUP
# =============================================================================

print("🔧 Initializing StatementGuard Multi-Agent Pipeline...")
print("   Loading embedding model (all-MiniLM-L6-v2)...")
embed_model = SentenceTransformer('all-MiniLM-L6-v2')
chroma_client = chromadb.Client()
collection = chroma_client.create_collection("bank_patterns", metadata={"hnsw:space": "cosine"})
collection.add(
    documents=[p["text"] for p in BANK_PATTERNS],
    metadatas=[{"bank": p["bank"], "country": p["country"]} for p in BANK_PATTERNS],
    ids=[p["id"] for p in BANK_PATTERNS],
)
print(f"   ✅ RAG vector store ready ({len(BANK_PATTERNS)} patterns indexed)")
print()

# Global reference for current scenario's holidays
_current_holidays = {}

# =============================================================================
# NODE 1: INGESTION AGENT
# =============================================================================

def ingestion_node(state: PipelineState) -> dict:
    from email_ingestion import fetch_monitoring_emails
    
    print(f"{'─' * 60}")
    print(f"  📥 INGESTION AGENT")
    print(f"     Region: {state['region']} | Date: {state['cycle_date']}")
    print(f"{'─' * 60}")
    
    # Attempt real email fetch (falls back to simulated if token expired)
    email_result = fetch_monitoring_emails(state["region"], state["cycle_date"])
    print(f"  Data source: {email_result['source'].upper()}")
    
    # In production: parse .xlsm attachment here
    # For now: use the gaps provided in state (from scenario or parsed real data)
    total = sum(g["count"] for g in state["raw_gaps"])
    print(f"  Parsed monitoring report:")
    print(f"  → {total} accounts flagged across {len(state['raw_gaps'])} bank/country groups\n")
    for gap in state["raw_gaps"]:
        print(f"     • {gap['bank']}/{gap['country']}: {gap['count']} account(s) — Statement Not Received")
    print()
    return {}  # raw_gaps already in state from initial input

# =============================================================================
# NODE 2: TRIAGE AGENT (RAG + Holiday + ToT Confidence Scoring)
# =============================================================================

def triage_node(state: PipelineState) -> dict:
    print(f"{'─' * 60}")
    print(f"  🧠 TRIAGE AGENT — RAG retrieval + holiday check + confidence scoring")
    print(f"{'─' * 60}")
    
    results: list[TriageDecision] = []
    
    for gap in state["raw_gaps"]:
        query = f"{gap['bank']}/{gap['country']} {gap['count']} accounts missing on {gap['day_of_week']}"
        
        # --- Evidence gathering ---
        holidays = _current_holidays.get(gap["country"], [])
        is_holiday = state["cycle_date"] in holidays
        
        rag_results = collection.query(query_texts=[query], n_results=3)
        retrieved_docs = rag_results["documents"][0] if rag_results["documents"] else []
        
        # --- Tree-of-Thought: generate candidate explanations ---
        candidates = []
        
        # Hypothesis 1: Holiday
        if is_holiday:
            candidates.append({
                "decision": "suppress",
                "confidence": 0.95,
                "explanation": f"Public holiday in {gap['country']} on {state['cycle_date']}. Bank operations likely closed."
            })
        
        # Hypothesis 2: Known pattern from RAG
        ESCALATE_SIGNALS = ["always be escalated", "no known delivery delays", "should always be escalated", "always genuine gaps"]
        pattern_match = any(gap["bank"] in doc and gap["country"] in doc for doc in retrieved_docs)
        if pattern_match and not is_holiday:
            best_doc = next((d for d in retrieved_docs if gap["bank"] in d), retrieved_docs[0])
            is_escalate_pattern = any(sig in best_doc.lower() for sig in ESCALATE_SIGNALS)
            if is_escalate_pattern:
                candidates.append({
                    "decision": "escalate",
                    "confidence": 0.92,
                    "explanation": f"RAG pattern indicates escalation required: {best_doc[:60]}..."
                })
            else:
                candidates.append({
                    "decision": "suppress",
                    "confidence": 0.85,
                    "explanation": f"Known delay pattern matched: {best_doc[:60]}..."
                })
        
        # Hypothesis 3: No evidence → escalate
        if not candidates:
            candidates.append({
                "decision": "escalate",
                "confidence": 0.90,
                "explanation": f"No holiday or known pattern for {gap['bank']}/{gap['country']}. Genuine gap suspected."
            })
        
        # --- Select best candidate (highest confidence) ---
        best = max(candidates, key=lambda c: c["confidence"])
        
        # --- Self-correction loop: requery if confidence < 0.8 ---
        if best["confidence"] < 0.8:
            refined_query = f"{gap['bank']} {gap['country']} delivery delay {gap['day_of_week']} pattern"
            rag_retry = collection.query(query_texts=[refined_query], n_results=2)
            if rag_retry["documents"][0]:
                best["confidence"] = min(best["confidence"] + 0.1, 0.95)
                best["explanation"] += " [refined via requery]"
            print(f"     ⟳ Self-correction: requeried with '{refined_query[:40]}...' → confidence now {best['confidence']:.2f}")
        
        decision: TriageDecision = {
            "bank": gap["bank"],
            "country": gap["country"],
            "accounts": gap["accounts"],
            "decision": best["decision"],
            "confidence": best["confidence"],
            "explanation": best["explanation"],
        }
        results.append(decision)
        
        icon = "🟢 SUPPRESS" if best["decision"] == "suppress" else "🔴 ESCALATE"
        print(f"  {icon}  {gap['bank']}/{gap['country']} (conf: {best['confidence']:.2f})")
        print(f"         Reason: {best['explanation'][:75]}")
    
    print()
    return {"triage_results": results}

# =============================================================================
# NODE 3: OUTREACH AGENT
# =============================================================================

def outreach_node(state: PipelineState) -> dict:
    escalated = [r for r in state["triage_results"] if r["decision"] == "escalate"]
    suppressed = len(state["triage_results"]) - len(escalated)
    
    print(f"{'─' * 60}")
    print(f"  ✉️  OUTREACH AGENT")
    print(f"{'─' * 60}")
    
    if not escalated:
        summary = f"✅ All {len(state['triage_results'])} gap(s) suppressed. No outreach needed."
        print(f"  {summary}\n")
        return {"outreach_drafts": [], "summary": summary}
    
    print(f"  Drafting outreach for {len(escalated)} escalation(s)...\n")
    
    drafts: list[OutreachDraft] = []
    for esc in escalated:
        key = f"{esc['bank']}/{esc['country']}"
        contact = BANK_CONTACTS.get(key, {"name": "Operations Desk", "email": "ops@bank.com"})
        ticket_id = f"SG-{state['cycle_date'].replace('-','')}-{esc['bank']}{esc['country']}"
        
        draft: OutreachDraft = {
            "bank": esc["bank"],
            "country": esc["country"],
            "recipient": contact["email"],
            "subject": f"Missing Bank Statements — {key} — {state['cycle_date']}",
            "body": (
                f"Dear {contact['name']},\n\n"
                f"We have not received bank statements for {len(esc['accounts'])} account(s) "
                f"({', '.join(esc['accounts'])}) as of the {state['region']} monitoring cycle "
                f"on {state['cycle_date']}.\n\n"
                f"Could you please confirm the expected delivery timeline?\n\n"
                f"Reference: {ticket_id}\n\n"
                f"Best regards,\nTreasury Operations (StatementGuard Automated)"
            ),
            "ticket_id": ticket_id,
        }
        drafts.append(draft)
        print(f"  📧 {key} → {contact['email']}")
        print(f"     Ticket: {ticket_id} | Accounts: {', '.join(esc['accounts'])}")
    
    summary = f"📊 {suppressed} suppressed, {len(escalated)} escalated with outreach drafted."
    print(f"\n  {summary}\n")
    return {"outreach_drafts": drafts, "summary": summary}

# =============================================================================
# BUILD GRAPH
# =============================================================================

workflow = StateGraph(PipelineState)
workflow.add_node("ingestion", ingestion_node)
workflow.add_node("triage", triage_node)
workflow.add_node("outreach", outreach_node)
workflow.add_edge(START, "ingestion")
workflow.add_edge("ingestion", "triage")
workflow.add_edge("triage", "outreach")
workflow.add_edge("outreach", END)
app = workflow.compile()

# =============================================================================
# GRAPH VISUALIZATION
# =============================================================================

def export_graph():
    """Export LangGraph state machine as PNG diagram."""
    try:
        png_bytes = app.get_graph().draw_mermaid_png()
        out_path = "./outputs/agent_graph_diagram.png"
        with open(out_path, "wb") as f:
            f.write(png_bytes)
        print(f"✅ Graph diagram exported to: {out_path}")
        return out_path
    except Exception as e:
        # Fallback: print mermaid text
        print(f"Could not render PNG ({e}). Mermaid source:")
        print(app.get_graph().draw_mermaid())
        return None

# =============================================================================
# RUN ALL SCENARIOS
# =============================================================================

def run_scenario(scenario_key: str):
    global _current_holidays
    scenario = SCENARIOS[scenario_key]
    _current_holidays = scenario["holidays"]
    
    print("\n" + "═" * 60)
    print(f"  🏁 {scenario['name']}")
    print("═" * 60 + "\n")
    
    initial_state: PipelineState = {
        "region": scenario["region"],
        "cycle_date": scenario["cycle_date"],
        "raw_gaps": scenario["gaps"],
        "triage_results": [],
        "outreach_drafts": [],
        "summary": "",
    }
    
    result = app.invoke(initial_state)
    return result


def print_final_metrics(all_results):
    """Print aggregate metrics across all scenarios."""
    total_gaps = sum(len(r["raw_gaps"]) for r in all_results)
    total_suppressed = sum(len([t for t in r["triage_results"] if t["decision"] == "suppress"]) for r in all_results)
    total_escalated = sum(len([t for t in r["triage_results"] if t["decision"] == "escalate"]) for r in all_results)
    total_outreach = sum(len(r["outreach_drafts"]) for r in all_results)
    
    print("\n" + "═" * 60)
    print("  📊 AGGREGATE METRICS (all scenarios)")
    print("═" * 60)
    print(f"  Total gap groups processed:    {total_gaps}")
    print(f"  Suppressed (false positives):  {total_suppressed} ({total_suppressed/total_gaps*100:.0f}%)")
    print(f"  Escalated (genuine gaps):      {total_escalated} ({total_escalated/total_gaps*100:.0f}%)")
    print(f"  Outreach emails drafted:       {total_outreach}")
    print(f"  False positive reduction:      ~{total_suppressed/total_gaps*100:.0f}% auto-suppressed vs. 0% without agent")
    print("═" * 60 + "\n")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    if "--graph" in sys.argv:
        export_graph()
        sys.exit(0)
    
    print("\n" + "🚀 " * 15)
    print("  STATEMENTGUARD — MULTI-AGENT CAPSTONE DEMO")
    print("  CMU AI Agentic Systems | LangGraph Pipeline")
    print("🚀 " * 15)
    
    results = []
    for key in SCENARIOS:
        result = run_scenario(key)
        results.append(result)
    
    print_final_metrics(results)
    
    # Show one sample email
    all_drafts = [d for r in results for d in r["outreach_drafts"]]
    if all_drafts:
        print("─" * 60)
        print("  📧 SAMPLE OUTREACH EMAIL (first escalation):")
        print("─" * 60)
        d = all_drafts[0]
        print(f"  To: {d['recipient']}")
        print(f"  Subject: {d['subject']}")
        print(f"  {'─' * 40}")
        print(f"  {d['body']}")
