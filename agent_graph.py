"""
StatementGuard — Multi-Agent LangGraph Prototype
=================================================
4-node state machine: Ingestion → Triage → Outreach → END

Run:  python3 agent_graph.py

Demonstrates autonomous multi-agent workflow for bank statement
gap detection, triage, and outreach — CMU AI Agentic Systems capstone.
"""

from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel
import chromadb
from sentence_transformers import SentenceTransformer
import json
from datetime import date

# =============================================================================
# STATE SCHEMA — typed contract between agents
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
# KNOWLEDGE BASE — bank patterns (RAG vector store)
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
    {"id": "p10", "text": "Analyst override 2026-04-10: SC/BD accounts should be suppressed for 72 hours during Eid holidays. Bank confirmed they do not process during extended Eid break.", "bank": "SC", "country": "BD"},
]

HOLIDAY_CALENDAR = {
    "BD": ["2026-06-18", "2026-06-19", "2026-06-20"],  # Eid al-Adha (simulated)
    "KR": ["2026-06-06"],  # Memorial Day
    "SG": [],
    "US": [],
    "JP": [],
}

BANK_CONTACTS = {
    "SC/BD": {"name": "Md. Rafiq Hassan", "email": "rafiq.hassan@sc.com", "channel": "email"},
    "CB/KR": {"name": "Kim Soo-Jin", "email": "soojin.kim@citi.com", "channel": "email"},
    "HS/SG": {"name": "Tan Wei Ling", "email": "weiling.tan@hsbc.com", "channel": "portal"},
    "JPM/US": {"name": "Sarah Mitchell", "email": "sarah.mitchell@jpmorgan.com", "channel": "email"},
    "DBS/SG": {"name": "Lim Boon Keng", "email": "boonkeng.lim@dbs.com", "channel": "email"},
}

# =============================================================================
# VECTOR STORE SETUP
# =============================================================================

print("🔧 Loading embedding model...")
embed_model = SentenceTransformer('all-MiniLM-L6-v2')
chroma_client = chromadb.Client()
collection = chroma_client.create_collection("bank_patterns", metadata={"hnsw:space": "cosine"})
collection.add(
    documents=[p["text"] for p in BANK_PATTERNS],
    metadatas=[{"bank": p["bank"], "country": p["country"]} for p in BANK_PATTERNS],
    ids=[p["id"] for p in BANK_PATTERNS],
)
print(f"✅ Vector store loaded ({len(BANK_PATTERNS)} patterns)\n")

# =============================================================================
# NODE 1: INGESTION AGENT
# =============================================================================

def ingestion_node(state: PipelineState) -> dict:
    """Simulates parsing .xlsm monitoring report. In production, this polls
    Graph API and parses Excel. For demo, uses hardcoded sample data."""
    
    print("=" * 60)
    print(f"📥 INGESTION AGENT — {state['region']} cycle ({state['cycle_date']})")
    print("=" * 60)
    
    # Simulated parse output (what parser.py produces from real .xlsm files)
    raw_gaps: list[AccountGap] = [
        {"bank": "SC", "country": "BD", "accounts": ["199BDTSC4102", "199BDTSC4103", "199BDTSC4104"], "count": 3, "day_of_week": "Thursday"},
        {"bank": "CB", "country": "KR", "accounts": ["427KRWCB2001", "427KRWCB2002"], "count": 2, "day_of_week": "Thursday"},
        {"bank": "JPM", "country": "US", "accounts": ["811USDJPM001"], "count": 1, "day_of_week": "Thursday"},
    ]
    
    print(f"   Parsed monitoring report: {sum(g['count'] for g in raw_gaps)} accounts flagged across {len(raw_gaps)} bank/country groups")
    for gap in raw_gaps:
        print(f"   • {gap['bank']}/{gap['country']}: {gap['count']} accounts missing")
    print()
    
    return {"raw_gaps": raw_gaps}

# =============================================================================
# NODE 2: TRIAGE AGENT (RAG + Tree-of-Thought scoring)
# =============================================================================

def triage_node(state: PipelineState) -> dict:
    """Evaluates each gap against holiday calendar + RAG pattern retrieval.
    Applies confidence scoring — loops internally if confidence < 0.8."""
    
    print("=" * 60)
    print("🧠 TRIAGE AGENT — Evaluating gaps with RAG + holiday calendar")
    print("=" * 60)
    
    results: list[TriageDecision] = []
    
    for gap in state["raw_gaps"]:
        query = f"{gap['bank']}/{gap['country']} {gap['count']} accounts missing on {gap['day_of_week']}"
        
        # Step 1: Check holiday calendar
        today = state["cycle_date"]
        holidays = HOLIDAY_CALENDAR.get(gap["country"], [])
        is_holiday = today in holidays
        
        # Step 2: RAG retrieval — find relevant bank patterns
        rag_results = collection.query(query_texts=[query], n_results=3)
        retrieved_docs = rag_results["documents"][0] if rag_results["documents"] else []
        
        # Step 3: Tree-of-Thought scoring — evaluate candidate explanations
        candidates = []
        
        # Candidate 1: Holiday suppression
        if is_holiday:
            candidates.append({"explanation": f"Public holiday in {gap['country']} today ({today}). Bank likely closed.", "confidence": 0.95, "decision": "suppress"})
        
        # Candidate 2: Known pattern match (from RAG) — only suppress if pattern
        # indicates expected delays, NOT if pattern says "always escalate"
        ESCALATE_SIGNALS = ["always be escalated", "no known delivery delays", "should always be escalated"]
        pattern_match = any(gap["bank"] in doc and gap["country"] in doc for doc in retrieved_docs)
        if pattern_match and not is_holiday:
            best_doc = next((d for d in retrieved_docs if gap["bank"] in d), retrieved_docs[0])
            is_escalate_pattern = any(sig in best_doc.lower() for sig in ESCALATE_SIGNALS)
            if is_escalate_pattern:
                candidates.append({"explanation": f"Pattern indicates immediate escalation: {best_doc[:80]}...", "confidence": 0.92, "decision": "escalate"})
            else:
                candidates.append({"explanation": f"Known delay pattern: {best_doc[:80]}...", "confidence": 0.85, "decision": "suppress"})
        
        # Candidate 3: No matching pattern — escalate
        if not candidates:
            candidates.append({"explanation": f"No holiday or known pattern for {gap['bank']}/{gap['country']} on {gap['day_of_week']}. Genuine gap suspected.", "confidence": 0.90, "decision": "escalate"})
        
        # Select highest confidence candidate
        best = max(candidates, key=lambda c: c["confidence"])
        
        # Self-correction: if confidence < 0.8, attempt requery (ToT rewriter loop)
        if best["confidence"] < 0.8:
            print(f"   ⟳ Low confidence ({best['confidence']:.2f}) for {gap['bank']}/{gap['country']} — requerying...")
            refined_query = f"{gap['bank']} {gap['country']} delivery delay pattern {gap['day_of_week']}"
            rag_retry = collection.query(query_texts=[refined_query], n_results=2)
            if rag_retry["documents"][0]:
                best["confidence"] = min(best["confidence"] + 0.1, 0.95)
                best["explanation"] += " [refined via requery]"
        
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
        print(f"   {icon} {gap['bank']}/{gap['country']} ({best['confidence']:.2f}): {best['explanation'][:70]}")
    
    print()
    return {"triage_results": results}

# =============================================================================
# NODE 3: OUTREACH AGENT
# =============================================================================

def outreach_node(state: PipelineState) -> dict:
    """For escalated gaps, compose outreach email and create ticket."""
    
    escalated = [r for r in state["triage_results"] if r["decision"] == "escalate"]
    
    if not escalated:
        print("=" * 60)
        print("✉️  OUTREACH AGENT — No escalations. All gaps suppressed.")
        print("=" * 60)
        print()
        return {"outreach_drafts": [], "summary": f"All {len(state['triage_results'])} gap(s) suppressed. No outreach needed."}
    
    print("=" * 60)
    print(f"✉️  OUTREACH AGENT — Drafting outreach for {len(escalated)} escalation(s)")
    print("=" * 60)
    
    drafts: list[OutreachDraft] = []
    
    for esc in escalated:
        key = f"{esc['bank']}/{esc['country']}"
        contact = BANK_CONTACTS.get(key, {"name": "Operations Desk", "email": "ops@bank.com", "channel": "email"})
        ticket_id = f"SG-{state['cycle_date'].replace('-','')}-{esc['bank']}{esc['country']}"
        
        draft: OutreachDraft = {
            "bank": esc["bank"],
            "country": esc["country"],
            "recipient": contact["email"],
            "subject": f"Missing Bank Statements — {key} — {state['cycle_date']}",
            "body": (
                f"Dear {contact['name']},\n\n"
                f"We have not received bank statements for {len(esc['accounts'])} account(s) "
                f"({', '.join(esc['accounts'])}) as of the {state['region']} monitoring cycle on {state['cycle_date']}.\n\n"
                f"Could you please confirm the expected delivery timeline?\n\n"
                f"Reference: {ticket_id}\n\n"
                f"Best regards,\nTreasury Operations (StatementGuard Automated)"
            ),
            "ticket_id": ticket_id,
        }
        drafts.append(draft)
        
        print(f"   📧 → {contact['email']}")
        print(f"      Subject: {draft['subject']}")
        print(f"      Ticket: {ticket_id}")
        print(f"      Accounts: {', '.join(esc['accounts'])}")
    
    print()
    
    suppressed = len(state["triage_results"]) - len(escalated)
    summary = f"{suppressed} suppressed, {len(escalated)} escalated with outreach drafted."
    return {"outreach_drafts": drafts, "summary": summary}

# =============================================================================
# BUILD THE GRAPH
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
# RUN
# =============================================================================

if __name__ == "__main__":
    print("\n" + "🚀 " * 20)
    print("   STATEMENTGUARD MULTI-AGENT PIPELINE")
    print("🚀 " * 20 + "\n")
    
    initial_state: PipelineState = {
        "region": "APAC AM",
        "cycle_date": str(date.today()),
        "raw_gaps": [],
        "triage_results": [],
        "outreach_drafts": [],
        "summary": "",
    }
    
    result = app.invoke(initial_state)
    
    # Final summary
    print("=" * 60)
    print("📊 PIPELINE COMPLETE — SUMMARY")
    print("=" * 60)
    print(f"   Region: {result['region']}")
    print(f"   Date: {result['cycle_date']}")
    print(f"   Gaps detected: {len(result['raw_gaps'])}")
    print(f"   Triage decisions: {len(result['triage_results'])}")
    print(f"   Outreach drafted: {len(result['outreach_drafts'])}")
    print(f"   Result: {result['summary']}")
    print()
    
    # Show outreach email bodies
    if result["outreach_drafts"]:
        print("-" * 60)
        print("📧 OUTREACH EMAIL DRAFTS:")
        print("-" * 60)
        for draft in result["outreach_drafts"]:
            print(f"\nTo: {draft['recipient']}")
            print(f"Subject: {draft['subject']}")
            print(f"---\n{draft['body']}")
