import pytest
from services.shared.database import SessionLocal
from services.shared.models import User
from services.agent.memory_agent import retrieve_context, save_memory

def test_product_scoped_memory_separation():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            user = User(email="test_mem_user@nexus.com", hashed_password="hashed_pwd")
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = user.id
    finally:
        db.close()
    
    # Save a memory in "code" scope
    save_memory(
        user_id=user_id,
        content="NEXUS Code: Use pytest for all python backend test suites.",
        mem_type="fact",
        importance=8,
        product_scope="code"
    )
    
    # Save another memory in "pa" scope
    save_memory(
        user_id=user_id,
        content="NEXUS PA: Schedule dental appointment on Friday morning.",
        mem_type="fact",
        importance=8,
        product_scope="pa"
    )
    
    # Retrieve in "code" scope
    code_memories = retrieve_context(user_id=user_id, query="pytest", limit=5, product_scope="code")
    assert len(code_memories) >= 1
    # Check that none of the retrieved memories belong to another scope
    for m in code_memories:
        assert m.get("meta_data", {}).get("product_scope") == "code"
    
    # Retrieve in "pa" scope
    pa_memories = retrieve_context(user_id=user_id, query="appointment", limit=5, product_scope="pa")
    assert len(pa_memories) >= 1
    for m in pa_memories:
        assert m.get("meta_data", {}).get("product_scope") == "pa"
    
    # Cross retrieval for code related topic in pa scope should return empty or not contain the code memory
    cross_code = retrieve_context(user_id=user_id, query="pytest", limit=5, product_scope="pa")
    for m in cross_code:
        assert m.get("meta_data", {}).get("product_scope") == "pa"
        assert "pytest" not in m["content"]
