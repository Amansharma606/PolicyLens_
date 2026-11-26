import time
import threading
from pathlib import Path
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.db_models import Document, DocumentPage, DocumentSection, DocumentClause
from app.services.pdf_processor import PDFProcessor
from app.services.classifier import ClauseClassifier
from app.services.bm25_retriever import get_bm25_index, invalidate_bm25_index
from app.core.logging import logger


class DocumentWorker:
    """
    Ultra-Fast Document Ingestion Pipeline (< 1-3s Total):
    - Layout-sorted PyMuPDF extraction + clean clause segmentation
    - Rule-based clause classification (zero slow PyTorch/LLM overhead)
    - Instant BM25 + TF-IDF n-gram hybrid index warm-up (~30-60ms)
    - Immediately sets document status = 'ready'
    - 10-Dimension Structured Explanation is synthesized lazily on demand in 1 single call!
    """

    _lock = threading.Lock()
    _active_jobs: set = set()
    _chunk_types_cache: Dict[str, Dict[int, str]] = {}

    @classmethod
    def is_active(cls, document_id: str) -> bool:
        with cls._lock:
            return document_id in cls._active_jobs

    @classmethod
    def run_stage1_sync(cls, db: Session, document_id: str) -> str:
        """
        Extracts pages/clauses and builds the instant BM25+TF-IDF hybrid search index in < 1-3s,
        marking the document READY immediately without loading PyTorch or running slow LLM loops.
        """
        t0 = time.time()
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return "failed"

        doc.status = "processing"
        doc.processing_stage = "Extracting policy text & building search index..."
        doc.processing_progress = 20
        doc.error_message = None
        db.commit()

        try:
            file_path = Path(doc.file_path)
            t_extract0 = time.time()
            extract_result = PDFProcessor.inspect_and_extract(file_path)
            t_extract = time.time() - t_extract0

            total_pages = extract_result["total_pages"]
            total_words = extract_result["total_words"]
            is_scanned = extract_result["is_scanned"]
            clauses = extract_result["clauses"]
            sections = extract_result["sections"]

            doc.total_pages = total_pages
            doc.total_words = total_words
            doc.is_scanned = is_scanned

            if is_scanned:
                doc.status = "scanned_ocr_required"
                doc.error_message = (
                    "Scanned image PDF detected: No selectable digital text was extracted. OCR is required."
                )
                doc.processing_stage = "Scanned image PDF: OCR required"
                doc.processing_progress = 100
                db.query(DocumentPage).filter(DocumentPage.document_id == doc.id).delete()
                db.add_all([
                    DocumentPage(
                        document_id=doc.id,
                        page_number=p["page"],
                        word_count=p["word_count"],
                        text=p["text"],
                    )
                    for p in extract_result["pages"]
                ])
                db.commit()
                return doc.status

            # Store Pages & Sections cleanly
            db.query(DocumentPage).filter(DocumentPage.document_id == doc.id).delete()
            db.add_all([
                DocumentPage(
                    document_id=doc.id,
                    page_number=p["page"],
                    word_count=p["word_count"],
                    text=p["text"],
                )
                for p in extract_result["pages"]
            ])

            db.query(DocumentSection).filter(DocumentSection.document_id == doc.id).delete()
            db.add_all([
                DocumentSection(
                    document_id=doc.id,
                    title=s["title"],
                    page_number=s["page"],
                    level=s["level"],
                )
                for s in sections
            ])

            # Classify and save clauses cleanly (fast rule engine, zero PyTorch overhead)
            db.query(DocumentClause).filter(DocumentClause.document_id == doc.id).delete()
            clause_objs: List[DocumentClause] = []
            chunk_types_map: Dict[int, str] = {}

            for idx, raw_c in enumerate(clauses):
                text = raw_c["text"]
                sec_name = raw_c.get("section", "General Terms")
                clause_num = raw_c.get("clause_number")
                c_type = raw_c.get("chunk_type", "clause")
                chunk_types_map[idx] = c_type

                cat, conf = ClauseClassifier.classify(text, section_name=sec_name, chunk_type=c_type)
                clause_objs.append(DocumentClause(
                    document_id=doc.id,
                    page_number=raw_c["page"],
                    clause_number=clause_num,
                    section_name=sec_name,
                    category=cat,
                    classification_confidence=conf,
                    original_text=text,
                    clean_text=" ".join(text.split()),
                ))

            db.add_all(clause_objs)
            db.commit()
            for obj in clause_objs:
                db.refresh(obj)

            cls._chunk_types_cache[doc.id] = chunk_types_map

            # Build in-memory BM25 + TF-IDF n-gram index immediately (< 60ms)
            invalidate_bm25_index(doc.id)
            cached_clauses = [{
                "id": c.id,
                "clean_text": c.clean_text,
                "search_text": f"[Section: {c.section_name or ''}] [Clause: {c.clause_number or ''}] [Category: {c.category or ''}] {c.clean_text}",
                "category": c.category,
                "page": c.page_number,
            } for c in clause_objs]
            get_bm25_index(doc.id, cached_clauses)

            doc.status = "ready"
            doc.explanation_json = None
            doc.processing_stage = "Ready for instant Q&A"
            doc.processing_progress = 100
            doc.error_message = None
            db.commit()

            logger.info(
                f"[TIMING] Document {document_id} - READY IN {time.time() - t0:.2f}s "
                f"(Extract: {t_extract:.2f}s | {total_pages} pages, {total_words} words, {len(clause_objs)} clauses)"
            )
            return doc.status

        except Exception as e:
            logger.error(f"Document ingestion failed for {document_id}: {e}", exc_info=True)
            doc.status = "failed"
            doc.error_message = str(e)
            doc.processing_stage = f"Failed: {str(e)}"
            doc.processing_progress = 0
            db.commit()
            return "failed"

    @classmethod
    def start_background_enrichment(cls, document_id: str) -> bool:
        """
        No-op compatibility hook: document is already READY immediately after run_stage1_sync
        with BM25+TF-IDF indexing, and 10-dimension explanation is generated lazily on tab open.
        """
        return False

    @classmethod
    def start_processing(cls, document_id: str) -> bool:
        """
        Runs fast ingestion asynchronously if invoked via legacy background path.
        """
        with cls._lock:
            if document_id in cls._active_jobs:
                return False
            cls._active_jobs.add(document_id)

        def _run():
            db = SessionLocal()
            try:
                cls.run_stage1_sync(db, document_id)
            finally:
                with cls._lock:
                    cls._active_jobs.discard(document_id)
                db.close()

        threading.Thread(target=_run, daemon=True, name=f"DocIngest-{document_id[:8]}").start()
        return True
