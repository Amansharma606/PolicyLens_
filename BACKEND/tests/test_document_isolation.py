import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db.database import SessionLocal, init_db
from app.models.db_models import User, Document, DocumentClause, DocumentPage
from app.services.pdf_processor import PDFProcessor
from app.services.classifier import ClauseClassifier
from app.services.embeddings import EmbeddingService
from app.services.rag_engine import RAGEngine

def ingest_policy(db, filename, user_id):
    pdf_path = BASE_DIR / "sample_policies" / filename
    extract = PDFProcessor.inspect_and_extract(pdf_path)

    # Clean old if exists
    old = db.query(Document).filter(Document.filename == filename).first()
    if old:
        db.delete(old)
        db.commit()

    doc = Document(
        user_id=user_id,
        filename=filename,
        file_path=str(pdf_path),
        file_size=pdf_path.stat().st_size,
        total_pages=extract["total_pages"],
        total_words=extract["total_words"],
        status="ready"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    for p in extract["pages"]:
        db.add(DocumentPage(document_id=doc.id, page_number=p["page"], word_count=p["word_count"], text=p["text"]))

    clauses_to_embed = []
    clause_objs = []
    for c in extract["clauses"]:
        cat, conf = ClauseClassifier.classify(c["text"], section_name=c.get("section", ""))
        dc = DocumentClause(
            document_id=doc.id,
            page_number=c["page"],
            clause_number=c.get("clause_number"),
            section_name=c.get("section", "General Terms"),
            category=cat,
            classification_confidence=conf,
            original_text=c["text"],
            clean_text=" ".join(c["text"].split())
        )
        clause_objs.append(dc)
        clauses_to_embed.append(c["text"])

    vectors = EmbeddingService.encode_batch(clauses_to_embed)
    for idx, obj in enumerate(clause_objs):
        if idx < len(vectors):
            obj.embedding_json = json.dumps(vectors[idx])
        db.add(obj)
    db.commit()
    return doc

def test_document_isolation():
    print("\n--- TEST: Multi-Tenant Policy Document Isolation ---")
    init_db()
    db = SessionLocal()

    user_a = db.query(User).filter(User.email == "analyst@policylens.ai").first()
    user_b = db.query(User).filter(User.email == "admin@policylens.ai").first()

    # Ingest Policy A (CareShield) under User A
    doc_a = ingest_policy(db, "CareShield_Health_Insurance_Policy.pdf", user_a.id)
    # Ingest Policy B (StarHealth) under User B
    doc_b = ingest_policy(db, "StarHealth_Optima_Policy.pdf", user_b.id)

    print(f"Policy A: '{doc_a.filename}' (ID: {doc_a.id}) owned by User A ({user_a.email})")
    print(f"Policy B: '{doc_b.filename}' (ID: {doc_b.id}) owned by User B ({user_b.email})")

    # Question on Policy A: Maternity
    ans_a = RAGEngine.answer_question(db, doc_a.id, "Is maternity covered under this policy?")
    print(f"\nPolicy A Answer: {ans_a['answer'][:180]}...")
    assert "covered" in ans_a["answer"].lower()
    # Check that no sources from Policy B were retrieved
    for s in ans_a["sources"]:
        assert "starhealth" not in s["text"].lower(), "CRITICAL LEAK: Policy B clause leaked into Policy A answer!"

    # Question on Policy B: Maternity
    ans_b = RAGEngine.answer_question(db, doc_b.id, "Is maternity covered under this policy?")
    print(f"\nPolicy B Answer: {ans_b['answer'][:180]}...")
    assert "excluded" in ans_b["answer"].lower() or "not covered" in ans_b["answer"].lower()
    # Check that no sources from Policy A were retrieved
    for s in ans_b["sources"]:
        assert "careshield" not in s["text"].lower(), "CRITICAL LEAK: Policy A clause leaked into Policy B answer!"

    # Question on Policy A: Pre-existing Disease Waiting Period (CareShield has 36 months)
    ans_ped_a = RAGEngine.answer_question(db, doc_a.id, "What is the waiting period for pre-existing disease?")
    print(f"\nPolicy A PED Waiting Period: {ans_ped_a['answer'][:140]}...")
    assert "36" in ans_ped_a["answer"]
    assert "48" not in ans_ped_a["answer"]

    # Question on Policy B: Pre-existing Disease Waiting Period (StarHealth has 48 months)
    ans_ped_b = RAGEngine.answer_question(db, doc_b.id, "What is the waiting period for pre-existing disease?")
    print(f"\nPolicy B PED Waiting Period: {ans_ped_b['answer'][:140]}...")
    assert "48" in ans_ped_b["answer"]
    assert "36" not in ans_ped_b["answer"]

    db.close()
    print("\n[PASS] Multi-Document Strict Isolation Confirmed! Zero Cross-Document Leakage.")

if __name__ == "__main__":
    test_document_isolation()
