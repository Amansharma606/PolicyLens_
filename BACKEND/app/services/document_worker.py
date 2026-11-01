import time
import json
import threading
from pathlib import Path
from typing import Set, Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.db_models import Document, DocumentPage, DocumentSection, DocumentClause
from app.services.pdf_processor import PDFProcessor, PDFProcessingError
from app.services.classifier import ClauseClassifier
from app.services.embeddings import EmbeddingService
from app.services.bm25_retriever import get_bm25_index, invalidate_bm25_index
from app.services.explanation_service import PolicyExplanationService
from app.core.logging import logger

class DocumentWorker:
    """
    Asynchronous Document Processing Worker.
    Executes extraction, clause classification, batched semantic embeddings,
    BM25 indexing, and 10-point policy explanation in the background.
    Maintains persistent progress and stage timing logs.
    """

    _active_jobs: Set[str] = set()
    _lock = threading.Lock()

    @classmethod
    def is_job_active(cls, document_id: str) -> bool:
        with cls._lock:
            return document_id in cls._active_jobs

    @classmethod
    def start_processing(cls, document_id: str) -> bool:
        """
        Launches processing for document_id in a detached background thread if not already active.
        Returns True if job was started, False if already running.
        """
        with cls._lock:
            if document_id in cls._active_jobs:
                logger.warning(f"Document {document_id} is already being processed. Skipping duplicate job trigger.")
                return False
            cls._active_jobs.add(document_id)

        worker_thread = threading.Thread(
            target=cls._run_pipeline,
            args=(document_id,),
            daemon=True,
            name=f"DocWorker-{document_id[:8]}"
        )
        worker_thread.start()
        logger.info(f"Background worker thread started for document {document_id}.")
        return True

    @classmethod
    def _run_pipeline(cls, document_id: str):
        pipeline_start = time.time()
        db: Session = SessionLocal()

        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if not doc:
                logger.error(f"DocumentWorker: Document {document_id} not found in database.")
                return

            file_path = Path(doc.file_path)
            if not file_path.exists():
                logger.error(f"DocumentWorker: File not found at path {file_path}")
                doc.status = "failed"
                doc.error_message = f"File missing on disk: {file_path}"
                doc.processing_stage = "Failed: file missing"
                db.commit()
                return

            # =========================================================================
            # STAGE 1: PDF EXTRACTION & STRUCTURE DETECTION
            # =========================================================================
            t0_extract = time.time()
            doc.status = "processing"
            doc.processing_stage = "Extracting text, structure, and tabular benefit schedules..."
            doc.processing_progress = 10
            db.commit()

            extract_result = PDFProcessor.inspect_and_extract(file_path)
            t_extract = time.time() - t0_extract

            total_pages = extract_result["total_pages"]
            total_words = extract_result["total_words"]
            clauses = extract_result["clauses"]
            sections = extract_result["sections"]
            is_scanned = extract_result.get("is_scanned", False)

            logger.info(
                f"[TIMING] Document {document_id} - STAGE 1 (PDF Extraction): {t_extract:.2f}s "
                f"({total_pages} pages, {total_words} words, {len(clauses)} clauses, {len(sections)} sections)"
            )

            # Update document stats
            doc.total_pages = total_pages
            doc.total_words = total_words

            # Check if image-only scanned document
            if is_scanned:
                doc.status = "scanned_ocr_required"
                doc.error_message = "Scanned image PDF detected: No selectable digital text was extracted. OCR is required."
                doc.processing_stage = "Scanned image PDF: OCR required"
                doc.processing_progress = 100

                # Still store raw pages
                for p in extract_result["pages"]:
                    db.add(DocumentPage(
                        document_id=doc.id,
                        page_number=p["page"],
                        word_count=p["word_count"],
                        text=p["text"]
                    ))
                db.commit()
                logger.info(f"Document {document_id} flagged as scanned_ocr_required.")
                return

            # Store Pages in DB
            db.query(DocumentPage).filter(DocumentPage.document_id == doc.id).delete()
            for p in extract_result["pages"]:
                db.add(DocumentPage(
                    document_id=doc.id,
                    page_number=p["page"],
                    word_count=p["word_count"],
                    text=p["text"]
                ))
            db.commit()

            # Store Sections in DB
            db.query(DocumentSection).filter(DocumentSection.document_id == doc.id).delete()
            for s in sections:
                db.add(DocumentSection(
                    document_id=doc.id,
                    title=s["title"],
                    page_number=s["page"],
                    level=s["level"]
                ))
            db.commit()

            doc.processing_stage = f"Extracted {total_pages} pages. Classifying clauses across policy dimensions..."
            doc.processing_progress = 35
            db.commit()

            # =========================================================================
            # STAGE 2: CLAUSE CLASSIFICATION
            # =========================================================================
            t0_classify = time.time()
            clause_objs = []
            clauses_to_encode = []

            # Clear existing clauses if re-running
            db.query(DocumentClause).filter(DocumentClause.document_id == doc.id).delete()
            db.commit()

            for raw_c in clauses:
                text = raw_c["text"]
                sec_name = raw_c.get("section", "General Terms")
                clause_num = raw_c.get("clause_number")
                cat, conf = ClauseClassifier.classify(text, section_name=sec_name)

                db_clause = DocumentClause(
                    document_id=doc.id,
                    page_number=raw_c["page"],
                    clause_number=clause_num,
                    section_name=sec_name,
                    category=cat,
                    classification_confidence=conf,
                    original_text=text,
                    clean_text=" ".join(text.split())
                )
                clause_objs.append(db_clause)
                enriched_text = f"[Section: {sec_name}] [Clause: {clause_num or ''}] [Category: {cat}] {text}"
                clauses_to_encode.append(enriched_text)

            t_classify = time.time() - t0_classify
            logger.info(f"[TIMING] Document {document_id} - STAGE 2 (Clause Classification): {t_classify:.2f}s ({len(clause_objs)} clauses)")

            # Batch save initial clauses to database
            for c_obj in clause_objs:
                db.add(c_obj)
            db.commit()

            doc.processing_stage = f"Classified {len(clause_objs)} clauses. Generating semantic vector embeddings in batches..."
            doc.processing_progress = 55
            db.commit()

            # =========================================================================
            # STAGE 3: BATCHED SEMANTIC VECTOR EMBEDDING (BGE-M3 / MiniLM)
            # =========================================================================
            t0_embed = time.time()
            total_clauses = len(clauses_to_encode)
            logger.info(f"Document {document_id}: Generating embeddings for {total_clauses} clauses in batches with {EmbeddingService.get_model_name()}...")

            # Callback to update database progress continuously as batches finish (55% -> 85%)
            def on_embed_batch_done(batch_num: int, total_batches: int, batch_embs: List[List[float]]):
                frac = batch_num / total_batches
                current_pct = int(55 + (frac * 29))
                doc.processing_progress = min(84, current_pct)
                processed_so_far = min(batch_num * 16, total_clauses)
                doc.processing_stage = f"Generating vector embeddings: {processed_so_far}/{total_clauses} clauses ({int(frac * 100)}%)..."
                try:
                    db.commit()
                except Exception as commit_err:
                    logger.debug(f"Progress commit error: {commit_err}")

            # Embed all clauses using batched encoder (batch_size=16) with live progress
            dense_vectors = EmbeddingService.encode_batch(
                clauses_to_encode,
                batch_size=16,
                on_batch_complete=on_embed_batch_done
            )

            # Persist embeddings to database records
            for idx, c_obj in enumerate(clause_objs):
                if idx < len(dense_vectors):
                    c_obj.embedding_json = json.dumps(dense_vectors[idx])
            db.commit()

            t_embed = time.time() - t0_embed
            logger.info(f"[TIMING] Document {document_id} - STAGE 3 (Semantic Embeddings): {t_embed:.2f}s ({total_clauses} vectors generated)")

            doc.processing_stage = "Building sparse keyword index (BM25 Okapi)..."
            doc.processing_progress = 85
            db.commit()

            # =========================================================================
            # STAGE 4: BM25 SPARSE KEYWORD INDEXING
            # =========================================================================
            t0_index = time.time()
            invalidate_bm25_index(doc.id)

            db_clauses = db.query(DocumentClause).filter(DocumentClause.document_id == doc.id).all()
            cached_clauses = [{
                "id": c.id,
                "clean_text": c.clean_text,
                "search_text": f"[Section: {c.section_name or ''}] [Clause: {c.clause_number or ''}] [Category: {c.category or ''}] {c.clean_text}",
                "category": c.category,
                "page": c.page_number
            } for c in db_clauses]
            get_bm25_index(doc.id, cached_clauses)

            t_index = time.time() - t0_index
            logger.info(f"[TIMING] Document {document_id} - STAGE 4 (BM25 Indexing): {t_index:.2f}s")

            doc.processing_stage = "Synthesizing 10-dimensional structured policy explanation..."
            doc.processing_progress = 92
            db.commit()

            # =========================================================================
            # STAGE 5: STRUCTURED POLICY EXPLANATION SYNTHESIS
            # =========================================================================
            t0_explain = time.time()
            try:
                PolicyExplanationService.generate_explanation(db, doc)
            except Exception as e:
                logger.error(f"Document {document_id}: Error generating initial policy explanation: {e}")
            t_explain = time.time() - t0_explain
            logger.info(f"[TIMING] Document {document_id} - STAGE 5 (Policy Explanation): {t_explain:.2f}s")

            # =========================================================================
            # STAGE 6: COMPLETION
            # =========================================================================
            t_total = time.time() - pipeline_start
            doc.status = "completed"
            doc.processing_stage = "Completed"
            doc.processing_progress = 100
            doc.error_message = None
            db.commit()

            logger.info(
                f"[TIMING] Document {document_id} - TOTAL PIPELINE DURATION: {t_total:.2f}s | "
                f"Extract: {t_extract:.2f}s | Classify: {t_classify:.2f}s | Embed: {t_embed:.2f}s | "
                f"Index: {t_index:.2f}s | Explain: {t_explain:.2f}s"
            )

        except Exception as e:
            logger.error(f"DocumentWorker: Error processing document {document_id}: {e}", exc_info=True)
            try:
                doc = db.query(Document).filter(Document.id == document_id).first()
                if doc:
                    doc.status = "failed"
                    doc.error_message = str(e)
                    doc.processing_stage = f"Failed: {str(e)}"
                    db.commit()
            except Exception as db_err:
                logger.error(f"DocumentWorker: Failed to record error status in DB: {db_err}")

        finally:
            with cls._lock:
                cls._active_jobs.discard(document_id)
            db.close()
