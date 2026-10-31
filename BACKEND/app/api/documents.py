import os
import shutil
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.db_models import User, Document, DocumentPage, DocumentSection, DocumentClause
from app.models.schemas import (
    DocumentResponse,
    DocumentUploadResponse,
    DocumentTextResponse,
    PageText,
    PolicyExplanationResponse
)
from app.core.config import settings
from app.core.security import get_current_user_optional
from app.services.pdf_processor import PDFProcessor, PDFProcessingError
from app.services.classifier import ClauseClassifier
from app.services.embeddings import EmbeddingService
from app.services.bm25_retriever import get_bm25_index, invalidate_bm25_index
from app.services.explanation_service import PolicyExplanationService
from app.core.logging import logger

router = APIRouter()

@router.get("/documents", response_model=List[DocumentResponse], tags=["Documents"])
def list_documents(
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    docs = db.query(Document).order_by(Document.upload_date.desc()).all()
    results = []
    for d in docs:
        results.append(DocumentResponse(
            id=d.id,
            filename=d.filename,
            file_size=d.file_size,
            total_pages=d.total_pages,
            total_words=d.total_words,
            upload_date=d.upload_date.isoformat() if d.upload_date else "",
            status=d.status,
            error_message=d.error_message,
            has_explanation=bool(d.explanation_json)
        ))
    return results

@router.post("/documents/upload", response_model=DocumentUploadResponse, tags=["Documents"])
def upload_document(
    file: UploadFile = File(...),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    filename = file.filename or "policy_document.pdf"
    clean_filename = Path(filename).name

    # 1. Validate Extension
    if not clean_filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only PDF files (.pdf) are supported."
        )

    # 2. Get User
    user_email = current_user.get("sub") if isinstance(current_user, dict) else "analyst@policylens.ai"
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        user = db.query(User).first()
    user_id = user.id if user else "00000000-0000-0000-0000-000000000000"

    # 3. Store uploaded file safely
    timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_disk_filename = f"{timestamp_prefix}_{clean_filename}"
    saved_file_path = settings.UPLOAD_DIR / safe_disk_filename

    try:
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to write file to disk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file on server storage."
        )

    file_size = os.path.getsize(saved_file_path)

    # 4. Validate Size
    if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        os.remove(saved_file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
        )
    if file_size == 0:
        os.remove(saved_file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)."
        )

    # 5. Extract Text & Structure
    try:
        extract_result = PDFProcessor.inspect_and_extract(saved_file_path)
    except PDFProcessingError as pe:
        logger.error(f"PDF extraction error: {pe}")
        os.remove(saved_file_path)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(pe))
    except Exception as e:
        logger.error(f"Unexpected extraction error: {e}")
        os.remove(saved_file_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to parse PDF document structure.")

    # Check scanned status
    is_scanned = extract_result.get("is_scanned", False)
    doc_status = "scanned_ocr_required" if is_scanned else "ready"
    error_msg = (
        "Scanned image PDF detected: No selectable digital text was extracted. OCR is required."
        if is_scanned else None
    )

    # 6. Create Database Record
    doc = Document(
        user_id=user_id,
        filename=clean_filename,
        file_path=str(saved_file_path),
        file_size=file_size,
        total_pages=extract_result["total_pages"],
        total_words=extract_result["total_words"],
        status=doc_status,
        error_message=error_msg
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 7. Store Pages
    for p in extract_result["pages"]:
        db_page = DocumentPage(
            document_id=doc.id,
            page_number=p["page"],
            word_count=p["word_count"],
            text=p["text"]
        )
        db.add(db_page)

    # 8. Store Sections
    for s in extract_result["sections"]:
        db_sec = DocumentSection(
            document_id=doc.id,
            title=s["title"],
            page_number=s["page"],
            level=s["level"]
        )
        db.add(db_sec)
    db.commit()

    # 9. Classify Clauses & Compute Embeddings
    if not is_scanned and extract_result["clauses"]:
        logger.info(f"Classifying and embedding {len(extract_result['clauses'])} clauses for document {doc.id}...")
        clauses_to_encode = []
        clause_objs = []

        for raw_c in extract_result["clauses"]:
            text = raw_c["text"]
            sec_name = raw_c.get("section", "General Terms")
            cat, conf = ClauseClassifier.classify(text, section_name=sec_name)

            db_clause = DocumentClause(
                document_id=doc.id,
                page_number=raw_c["page"],
                clause_number=raw_c.get("clause_number"),
                section_name=sec_name,
                category=cat,
                classification_confidence=conf,
                original_text=text,
                clean_text=" ".join(text.split())
            )
            clause_objs.append(db_clause)
            clauses_to_encode.append(text)

        dense_vectors = EmbeddingService.encode_batch(clauses_to_encode)
        for idx, obj in enumerate(clause_objs):
            if idx < len(dense_vectors):
                obj.embedding_json = json.dumps(dense_vectors[idx])
            db.add(obj)
        db.commit()

        # Initialize BM25 index in memory
        db_clauses = db.query(DocumentClause).filter(DocumentClause.document_id == doc.id).all()
        cached_clauses = [{
            "id": c.id,
            "clean_text": c.clean_text,
            "category": c.category,
            "page": c.page_number
        } for c in db_clauses]
        get_bm25_index(doc.id, cached_clauses)

        # 10. Generate Initial Policy Explanation
        try:
            PolicyExplanationService.generate_explanation(db, doc)
        except Exception as e:
            logger.error(f"Error generating initial policy explanation: {e}")

    doc_response = DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        file_size=doc.file_size,
        total_pages=doc.total_pages,
        total_words=doc.total_words,
        upload_date=doc.upload_date.isoformat() if doc.upload_date else "",
        status=doc.status,
        error_message=doc.error_message,
        has_explanation=bool(doc.explanation_json)
    )

    return DocumentUploadResponse(
        message="Policy document uploaded and indexed successfully.",
        document=doc_response
    )

@router.get("/documents/{document_id}", response_model=DocumentResponse, tags=["Documents"])
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Policy document not found.")
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        file_size=doc.file_size,
        total_pages=doc.total_pages,
        total_words=doc.total_words,
        upload_date=doc.upload_date.isoformat() if doc.upload_date else "",
        status=doc.status,
        error_message=doc.error_message,
        has_explanation=bool(doc.explanation_json)
    )

@router.get("/documents/{document_id}/text", response_model=DocumentTextResponse, tags=["Documents"])
def get_document_text(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Policy document not found.")
    
    pages = db.query(DocumentPage).filter(DocumentPage.document_id == document_id).order_by(DocumentPage.page_number).all()
    pages_data = [
        PageText(page=p.page_number, word_count=p.word_count, text=p.text)
        for p in pages
    ]
    return DocumentTextResponse(
        document_id=doc.id,
        filename=doc.filename,
        total_pages=doc.total_pages,
        total_words=doc.total_words,
        pages=pages_data
    )

@router.get("/documents/{document_id}/explanation", tags=["Documents"])
def get_document_explanation(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Policy document not found.")
    
    if doc.explanation_json:
        try:
            return json.loads(doc.explanation_json)
        except Exception:
            pass

    return PolicyExplanationService.generate_explanation(db, doc)

@router.delete("/documents/{document_id}", tags=["Documents"])
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Policy document not found.")

    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Could not remove physical file: {e}")

    invalidate_bm25_index(document_id)
    db.delete(doc)
    db.commit()

    return {"message": f"Document '{doc.filename}' deleted successfully."}
