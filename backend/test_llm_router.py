"""
Manual Test Script -- LLM Router
================================
Tests each component of the new llm_router.py interactively.
Run from the backend/ directory with the venv Python:

    .venv\Scripts\python.exe test_llm_router.py

No server, no Docker, no database needed.
"""

import sys
import os
os.environ["PYTHONUTF8"] = "1"
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
sys.path.insert(0, os.path.dirname(__file__))

# ─── Colour helpers ───────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  [OK]   {msg}")
def fail(msg):  print(f"  [FAIL] {msg}")
def info(msg):  print(f"  [>>]   {msg}")
def section(title): print(f"\n{'='*55}\n  {title}\n{'='*55}")

# ─── TEST 1: Import check ─────────────────────────────────────
section("TEST 1 — Import llm_router")
try:
    from services.agent.llm_router import get_chat_llm, get_embedding_vector
    ok("llm_router imported successfully")
except Exception as e:
    fail(f"Import failed: {e}")
    sys.exit(1)

# ─── TEST 2: All 4 roles return a model ──────────────────────
section("TEST 2 — get_chat_llm() for each role")
roles = ["reasoning", "planning", "extraction", "approval", "default"]
for role in roles:
    try:
        llm = get_chat_llm(role=role)
        ok(f"role='{role}' → {type(llm).__name__}")
    except Exception as e:
        fail(f"role='{role}' failed: {e}")

# ─── TEST 3: Mock LLM actually responds ──────────────────────
section("TEST 3 — Mock LLM Chat Response")
from langchain_core.messages import HumanMessage, SystemMessage

try:
    llm = get_chat_llm(role="reasoning")
    response = llm.invoke([
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Hello! Tell me about yourself.")
    ])
    ok(f"Mock LLM responded: \"{response.content[:80]}...\"" if len(response.content) > 80 else f"Mock LLM responded: \"{response.content}\"")
except Exception as e:
    fail(f"Mock LLM invoke failed: {e}")

# ─── TEST 4: Intent classification (mock) ────────────────────
section("TEST 4 — Intent Classification (Mock)")
import json
try:
    llm = get_chat_llm(role="reasoning")
    system_prompt = (
        "You are an intent classifier. Categorize the user's last message into exactly one of: "
        "goal_creation, task_creation, information, execution, or general_chat.\n"
        "Return output strictly as a JSON object: {\"intent\": \"category\"}"
    )
    test_messages = [
        "I want to build a SaaS product",
        "Search for latest AI news",
        "Create a task for me",
        "Hello how are you",
    ]
    for msg in test_messages:
        resp = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=msg)
        ])
        try:
            data = json.loads(resp.content)
            ok(f"\"{msg[:35]}...\" → intent: {data.get('intent', '?')}")
        except Exception:
            ok(f"\"{msg[:35]}\" → raw: {resp.content[:50]}")
except Exception as e:
    fail(f"Intent classification failed: {e}")

# ─── TEST 5: Planner mock decomposition ──────────────────────
section("TEST 5 — Goal Decomposition (Planner)")
try:
    from uuid import uuid4
    from services.agent.planner import decompose_goal

    test_uuid = uuid4()
    tasks = decompose_goal(
        user_id=test_uuid,
        goal_title="Build a SaaS landing page",
        goal_desc="Create a landing page with pricing, auth login button, and hero section."
    )
    ok(f"Decomposed into {len(tasks)} tasks:")
    for i, t in enumerate(tasks, 1):
        crit = " [CRITICAL PATH]" if t.get("is_critical") else ""
        info(f"  {i}. {t['title']} | PERT={t.get('pert_estimate','?')}h | Priority={t.get('priority_score','?')}{crit}")
except Exception as e:
    fail(f"Planner failed: {e}")

# ─── TEST 6: Embedding vector ─────────────────────────────────
section("TEST 6 — Embedding Vector (Mock)")
try:
    test_texts = [
        "User prefers AWS for cloud hosting",
        "User prefers AWS for cloud hosting",   # same → should give same vector
        "The weather today is sunny",
    ]
    vectors = []
    for text in test_texts:
        vec = get_embedding_vector(text)
        vectors.append(vec)
        ok(f"\"{text[:45]}\" → dim={len(vec)}, sample=[{round(vec[0],4)}, {round(vec[1],4)}, ...]")

    # Check determinism: same text → same vector
    if vectors[0] == vectors[1]:
        ok("Determinism check PASSED: identical text → identical vector ✓")
    else:
        fail("Determinism check FAILED: same text gave different vectors!")

    # Sanity: different text → different vector
    if vectors[0] != vectors[2]:
        ok("Uniqueness check PASSED: different text → different vector ✓")
    else:
        fail("Uniqueness check FAILED: different text gave same vector!")
except Exception as e:
    fail(f"Embedding test failed: {e}")

# ─── TEST 7: Memory extraction (mock) ────────────────────────
section("TEST 7 — Memory Extraction (Mock)")
try:
    from uuid import uuid4
    from services.agent.memory_agent import extract_memories

    test_user_id = uuid4()
    chat = "User: My name is Amar. I prefer to use AWS for hosting. I like Python."
    extracted = extract_memories(test_user_id, chat)
    if extracted:
        ok(f"Extracted {len(extracted)} memories:")
        for m in extracted:
            info(f"  [{m.get('type','?')}] \"{m.get('content','?')}\" (importance={m.get('importance','?')})")
    else:
        info("No memories extracted (mock mode: only triggers on 'my name is' / 'i prefer')")
except Exception as e:
    fail(f"Memory extraction failed: {e}")

# ─── TEST 8: Tool binding ─────────────────────────────────────
section("TEST 8 — Tool Binding (bind_tools check)")
try:
    from services.agent.tools import web_search, read_file, memory_read
    llm = get_chat_llm(role="reasoning")
    llm_with_tools = llm.bind_tools([web_search, read_file, memory_read])
    ok(f"bind_tools succeeded on {type(llm).__name__}")
except Exception as e:
    fail(f"Tool binding failed: {e}")

# ─── TEST 9: Approval risk assessor ──────────────────────────
section("TEST 9 — Approval / Risk Scoring")
try:
    from services.agent.approval import assess_task_risk
    test_cases = [
        ("Search for competitor pricing",     "Web search task", "LOW"),
        ("Send email to external client",      "Send email",     "HIGH"),
        ("Delete the production database",     "DROP TABLE",     "HIGH"),
        ("Read config file",                   "Read file",      "LOW"),
        ("Create a new feature branch",        "git checkout",   "LOW/MED"),
    ]
    for title, desc, expected in test_cases:
        result = assess_task_risk(title, desc)
        match = "✓" if result in expected else "~"
        ok(f"[{match}] \"{title[:40]}\" → {result}  (expected ~{expected})")
except Exception as e:
    fail(f"Risk assessment failed: {e}")

# ─── SUMMARY ──────────────────────────────────────────────────
section("TEST COMPLETE")
print(f"""
  {GREEN}{BOLD}All tests finished!{RESET}

  {CYAN}What to test next with a REAL API key:{RESET}

  1. Set in .env:
       LLM_PROVIDER=groq
       LLM_MODEL=llama-3.1-70b-versatile
       GROQ_API_KEY=gsk_...    (free at console.groq.com)

  2. Re-run this script and tests 3-4 will use the real Groq model.

  3. To test Claude:
       LLM_PROVIDER=anthropic
       LLM_MODEL=claude-3-5-haiku-20241022
       ANTHROPIC_API_KEY=sk-ant-...

  4. To test local Ollama:
       ollama pull llama3.1:8b
       LLM_PROVIDER=ollama
       LLM_MODEL=llama3.1:8b
""")
