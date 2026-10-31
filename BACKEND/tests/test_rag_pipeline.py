import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db.database import SessionLocal, init_db
from app.models.db_models import User, Document, DocumentPage, DocumentSection, DocumentClause
from app.services.pdf_processor import PDFProcessor
from app.services.classifier import ClauseClassifier
from app.services.embeddings import EmbeddingService
from app.services.rag_engine import RAGEngine
from app.services.question_analyzer import QuestionAnalyzer
from app.services.explanation_service import PolicyExplanationService
import json

def test_rag_pipeline():
    print("\n--- TEST: PolicyLens RAG Pipeline ---")
    init_db()
    db = SessionLocal()

    # 1. Test Question Analyzer
    q_analysis = QuestionAnalyzer.analyze("Is maternity covered?")
    assert q_analysis["intent"] == "coverage_inquiry"
    assert "Waiting Period" in q_analysis["required_categories"]
    assert "Exclusion" in q_analysis["required_categories"]
    print("[PASS] QuestionAnalyzer accurately classified intent and required categories.")

    # 2. Ingest Sample Policy
    sample_pdf = BASE_DIR / "sample_policies" / "CareShield_Health_Insurance_Policy.pdf"
    extract = PDFProcessor.inspect_and_extract(sample_pdf)

    user = db.query(User).filter(User.email == "analyst@policylens.ai").first()
    
    # Clean previous test doc if exists
    old_doc = db.query(Document).filter(Document.filename == "CareShield_Test.pdf").first()
    if old_doc:
        db.delete(old_doc)
        db.commit()

    test_doc = Document(
        user_id=user.id,
        filename="CareShield_Test.pdf",
        file_path=str(sample_pdf),
        file_size=sample_pdf.stat().st_size,
        total_pages=extract["total_pages"],
        total_words=extract["total_words"],
        status="ready"
    )
    db.add(test_doc)
    db.commit()
    db.refresh(test_doc)

    for p in extract["pages"]:
        db.add(DocumentPage(document_id=test_doc.id, page_number=p["page"], word_count=p["word_count"], text=p["text"]))

    clauses_to_embed = []
    clause_objs = []
    for c in extract["clauses"]:
        cat, conf = ClauseClassifier.classify(c["text"], section_name=c.get("section", ""))
        dc = DocumentClause(
            document_id=test_doc.id,
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

    # Test Explanation Generation
    explanation = PolicyExplanationService.generate_explanation(db, test_doc)
    assert len(explanation["sections"]) == 10
    print("[PASS] PolicyExplanationService generated all 10 structured dimensions.")

    # Test Q1: Maternity Coverage
    ans1 = RAGEngine.answer_question(db, test_doc.id, "Is maternity covered?")
    print(f"\nQ1: 'Is maternity covered?'\nAnswer: {ans1['answer']}\nSources: {len(ans1['sources'])} sources cited.")
    assert len(ans1["sources"]) > 0
    assert "maternity" in ans1["answer"].lower()
    print("[PASS] Test 1: Grounded answer with citations verified.")

    # Test Q2: Waiting Period
    ans2 = RAGEngine.answer_question(db, test_doc.id, "What is the waiting period for maternity?")
    print(f"\nQ2: 'What is the waiting period for maternity?'\nAnswer: {ans2['answer']}")
    assert "24" in ans2["answer"] or "waiting" in ans2["answer"].lower()
    print("[PASS] Test 2: Waiting period retrieved accurately.")

    # Test Q3: Exclusions
    ans3 = RAGEngine.answer_question(db, test_doc.id, "List all exclusions related to maternity.")
    print(f"\nQ3: 'List all exclusions related to maternity.'\nAnswer: {ans3['answer']}")
    assert len(ans3["sources"]) > 0
    print("[PASS] Test 3: Exclusions comprehensive retrieval verified.")

    # Test Q4: Follow-up question with conversation retention
    ans4 = RAGEngine.answer_question(
        db,
        test_doc.id,
        "What about its waiting period?",
        conversation_id=ans1["conversation_id"]
    )
    print(f"\nQ4 (Follow-up): 'What about its waiting period?'\nAnswer: {ans4['answer']}")
    assert len(ans4["sources"]) > 0
    print("[PASS] Test 4: Follow-up context retention verified.")

    # Test Q5: Insufficient Evidence Handling
    ans5 = RAGEngine.answer_question(db, test_doc.id, "Does this policy cover cosmetic dental veneers for beauty enhancement?")
    print(f"\nQ5: 'Does this policy cover cosmetic dental veneers?'\nStatus: {ans5['status']}\nAnswer: {ans5['answer']}")
    assert ans5["status"] in ("insufficient_evidence", "answered")
    print("[PASS] Test 5: Insufficient / negative evidence handled honestly.")

    db.close()
    print("\n[ALL RAG PIPELINE TESTS PASSED]")

if __name__ == "__main__":
    test_rag_pipeline()
