import sys
import io
from pathlib import Path
from fastapi import UploadFile

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db.database import SessionLocal, init_db
from app.api import health, auth, documents, chat
from app.models.schemas import UserLoginRequest, QuestionRequest

def test_api_endpoints():
    print("\n--- TEST: FastAPI REST Endpoint Controllers ---")
    init_db()
    db = SessionLocal()

    # 1. Test Health Endpoint
    h_resp = health.health_check()
    assert h_resp["status"] == "ok"
    assert h_resp["app"] == "PolicyLens"
    print("[PASS] 1. GET /api/health controller verified:", h_resp["status"])

    # 2. Test Auth Login
    login_req = UserLoginRequest(
        email="analyst@policylens.ai",
        password="PolicyLens@2026",
        rememberMe=True
    )
    auth_resp = auth.login(login_req, db=db)
    assert auth_resp.token is not None
    assert auth_resp.user.email == "analyst@policylens.ai"
    user_payload = {"sub": auth_resp.user.email, "role": auth_resp.user.role}
    print("[PASS] 2. POST /api/auth/login controller verified. Logged in as:", auth_resp.user.name)

    # 3. Test Document Upload Controller
    sample_pdf = BASE_DIR / "sample_policies" / "CareShield_Health_Insurance_Policy.pdf"
    with open(sample_pdf, "rb") as f:
        pdf_bytes = f.read()

    upload_file = UploadFile(
        file=io.BytesIO(pdf_bytes),
        filename="CareShield_API_Test.pdf"
    )

    upload_resp = documents.upload_document(
        file=upload_file,
        current_user=user_payload,
        db=db
    )
    doc_id = upload_resp.document.id
    assert upload_resp.document.total_pages == 5
    print(f"[PASS] 3. POST /api/documents/upload controller verified. Uploaded doc_id: {doc_id}")

    # 4. Test List Documents
    doc_list = documents.list_documents(current_user=user_payload, db=db)
    assert len(doc_list) >= 1
    print(f"[PASS] 4. GET /api/documents controller verified. Total docs: {len(doc_list)}")

    # 5. Test Get Document Text Preview
    text_resp = documents.get_document_text(doc_id, db=db)
    assert len(text_resp.pages) == 5
    print(f"[PASS] 5. GET /api/documents/{doc_id}/text controller verified. Pages: {len(text_resp.pages)}")

    # 6. Test Get Structured Policy Explanation
    expl_resp = documents.get_document_explanation(doc_id, db=db)
    assert len(expl_resp["sections"]) == 10
    print(f"[PASS] 6. GET /api/documents/{doc_id}/explanation controller verified. 10 dimensions generated.")

    # 7. Test Ask Question (RAG)
    q_req = QuestionRequest(
        question="What is the waiting period for maternity?",
        conversation_id=None
    )
    ans_resp = chat.ask_document_question(
        document_id=doc_id,
        request=q_req,
        current_user=user_payload,
        db=db
    )
    assert ans_resp.conversation_id is not None
    assert len(ans_resp.sources) > 0
    print(f"[PASS] 7. POST /api/documents/{doc_id}/ask controller verified. Cited {len(ans_resp.sources)} sources.")

    # 8. Test Document Conversation History
    hist_resp = chat.get_document_history(
        document_id=doc_id,
        conversation_id=ans_resp.conversation_id,
        db=db
    )
    assert len(hist_resp.messages) >= 2
    print(f"[PASS] 8. GET /api/documents/{doc_id}/history controller verified. Messages in thread: {len(hist_resp.messages)}")

    # 9. Test List Conversations
    conv_list = chat.list_conversations(current_user=user_payload, db=db)
    assert len(conv_list) >= 1
    print(f"[PASS] 9. GET /api/conversations controller verified. Total threads: {len(conv_list)}")

    db.close()
    print("\n[ALL REST API CONTROLLER TESTS PASSED]")

if __name__ == "__main__":
    test_api_endpoints()
