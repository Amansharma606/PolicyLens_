import os
import shutil
import json
import hashlib
import threading
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.db_models import User, Document, DocumentPage, DocumentSection, DocumentClause
from app.models.schemas import (
    DocumentResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    DocumentTextResponse,
    PageText,
    PolicyExplanationResponse
)
from app.core.config import settings
from app.core.security import get_current_user_optional
from app.services.document_worker import DocumentWorker
from app.services.explanation_service import PolicyExplanationService
from app.services.bm25_retriever import get_bm25_index
from app.core.logging import logger

router = APIRouter()
_expl_locks: Dict[str, threading.Lock] = {}
_expl_locks_guard = threading.Lock()


def _get_expl_lock(doc_id: str) -> threading.Lock:
    with _expl_locks_guard:
        if doc_id not in _expl_locks:
            _expl_locks[doc_id] = threading.Lock()
        return _expl_locks[doc_id]

def _format_doc_response(d: Document) -> DocumentResponse:
    is_ready = d.status in ["chat_ready", "completed", "ready"]
    return DocumentResponse(
        id=d.id,
        filename=d.filename,
        file_size=d.file_size,
        total_pages=d.total_pages or 0,
        total_words=d.total_words or 0,
        upload_date=d.upload_date.isoformat() if d.upload_date else "",
        status=d.status,
        processing_stage=d.processing_stage or ("Completed" if is_ready else "Processing"),
        processing_progress=d.processing_progress if d.processing_progress is not None else (100 if d.status in ["completed", "ready"] else 40),
        error_message=d.error_message,
        has_explanation=bool(d.explanation_json),
        is_ready_for_chat=is_ready
    )

@router.get("/documents", response_model=List[DocumentResponse], tags=["Documents"])
def list_documents(
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    docs = db.query(Document).order_by(Document.upload_date.desc()).all()
    return [_format_doc_response(d) for d in docs]

@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Documents"]
)
def upload_document(
    response: Response,
    file: UploadFile = File(...),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Asynchronous Document Upload:
    Saves PDF file, calculates SHA-256 hash to prevent duplicate jobs,
    registers document record, launches background AI pipeline,
    and returns HTTP 202 Accepted immediately.
    """
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

    # 3. Read file contents and compute hash
    try:
        file_bytes = file.file.read()
        file_size = len(file_bytes)
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read uploaded file."
        )

    # 4. Validate Size
    if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
        )
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)."
        )

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # 5. Check for Duplicate Uploads (instant return if already indexed; fast re-index otherwise)
    existing_doc = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing_doc:
        clause_cnt = db.query(DocumentClause).filter(DocumentClause.document_id == existing_doc.id).count()
        if existing_doc.status in ["completed", "ready", "chat_ready"] and clause_cnt > 0:
            if existing_doc.status != "ready":
                existing_doc.status = "ready"
                existing_doc.processing_progress = 100
                existing_doc.processing_stage = "Ready for instant Q&A"
                db.commit()
                db.refresh(existing_doc)
            clauses_db = db.query(DocumentClause).filter(DocumentClause.document_id == existing_doc.id).all()
            get_bm25_index(existing_doc.id, [{
                "id": c.id,
                "clean_text": c.clean_text,
                "search_text": f"[Section: {c.section_name or ''}] [Clause: {c.clause_number or ''}] [Category: {c.category or ''}] {c.clean_text}",
                "category": c.category,
                "page": c.page_number,
            } for c in clauses_db])
            logger.info(f"Duplicate upload detected: Document {existing_doc.id} ({existing_doc.filename}) ready.")
            response.status_code = status.HTTP_200_OK
            return DocumentUploadResponse(
                message="Policy document already uploaded and ready for instant Q&A.",
                document=_format_doc_response(existing_doc)
            )
        else:
            logger.info(f"Re-indexing existing document {existing_doc.id} ({existing_doc.filename}) with fast pipeline.")
            DocumentWorker.run_stage1_sync(db, existing_doc.id)
            db.refresh(existing_doc)
            response.status_code = status.HTTP_200_OK
            return DocumentUploadResponse(
                message="Policy extracted and ready for instant Q&A.",
                document=_format_doc_response(existing_doc)
            )

    # 6. Store uploaded file safely on disk
    timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_disk_filename = f"{timestamp_prefix}_{clean_filename}"
    saved_file_path = settings.UPLOAD_DIR / safe_disk_filename

    try:
        with open(saved_file_path, "wb") as buffer:
            buffer.write(file_bytes)
            buffer.flush()
    except Exception as e:
        logger.error(f"Failed to save file to disk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file on server storage."
        )

    # 7. Create Database Record and run fast single-stage extraction + BM25+TF-IDF indexing (< 1-3s)
    doc = Document(
        user_id=user_id,
        filename=clean_filename,
        file_path=str(saved_file_path),
        file_size=file_size,
        total_pages=0,
        total_words=0,
        status="processing",
        processing_stage="Extracting text & building instant search index...",
        processing_progress=10,
        file_hash=file_hash,
        error_message=None
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    DocumentWorker.run_stage1_sync(db, doc.id)
    db.refresh(doc)

    response.status_code = status.HTTP_200_OK
    return DocumentUploadResponse(
        message="Policy parsed and ready for instant Q&A.",
        document=_format_doc_response(doc)
    )

@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse, tags=["Documents"])
def get_document_status(document_id: str, db: Session = Depends(get_db)):
    """
    Persistent Document Processing Status Polling API.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Policy document '{document_id}' not found.")

    clause_count = db.query(DocumentClause).filter(DocumentClause.document_id == document_id).count()
    is_ready = doc.status in ["chat_ready", "completed", "ready"]

    return DocumentStatusResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        processing_stage=doc.processing_stage or ("Ready for instant Q&A" if is_ready else "Processing"),
        processing_progress=doc.processing_progress if doc.processing_progress is not None else (100 if is_ready else 50),
        total_pages=doc.total_pages or 0,
        total_words=doc.total_words or 0,
        total_clauses=clause_count,
        error_message=doc.error_message,
        has_explanation=bool(doc.explanation_json),
        is_ready_for_chat=is_ready
    )

@router.get("/documents/{document_id}", response_model=DocumentResponse, tags=["Documents"])
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Policy document not found.")
    return _format_doc_response(doc)

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
        total_pages=doc.total_pages or len(pages_data),
        total_words=doc.total_words or sum(p.word_count for p in pages_data),
        pages=pages_data
    )

@router.get("/documents/{document_id}/explanation", response_model=PolicyExplanationResponse, tags=["Documents"])
def get_document_explanation(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Policy document not found.")

    has_v31 = bool(doc.explanation_json and '"pipeline_version": "3.1"' in doc.explanation_json)
    if not has_v31:
        if doc.status not in ("ready", "completed", "chat_ready"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document text extraction must complete before generating structured explanation."
            )
        lock = _get_expl_lock(document_id)
        with lock:
            db.refresh(doc)
            if not (doc.explanation_json and '"pipeline_version": "3.1"' in doc.explanation_json):
                logger.info(f"Lazily generating 10-dimension explanation in single batch for {doc.id}...")
                explanation_data = PolicyExplanationService.generate_explanation(db, doc)
                return PolicyExplanationResponse(**explanation_data)

    try:
        explanation_data = json.loads(doc.explanation_json)
        return PolicyExplanationResponse(**explanation_data)
    except Exception as e:
        logger.error(f"Failed to parse stored explanation JSON for document {document_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to parse structured policy explanation."
        )

@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Documents"])
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Policy document not found.")

    file_path = Path(doc.file_path)
    try:
        if file_path.exists():
            os.remove(file_path)
    except Exception as e:
        logger.warning(f"Could not remove physical file at {file_path}: {e}")

    db.delete(doc)
    db.commit()
    logger.info(f"Policy document {document_id} and all related records deleted.")
    return None
