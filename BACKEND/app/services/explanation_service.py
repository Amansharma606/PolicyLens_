import json
from typing import Dict, Any, List, Optional, Callable
from sqlalchemy.orm import Session
from app.models.db_models import Document, DocumentClause
from app.services.classifier import ClauseClassifier
from app.services.llm_service import LLMService
from app.core.logging import logger


class PolicyExplanationService:
    """
    Generates a generalized, domain-agnostic 10-dimensional Policy Explanation
    lazily on demand using fast lexical/rule scoring (~15ms) plus ONE single fast LLM
    synthesis call over all found dimensions (never 10 slow sequential calls).
    """

    @classmethod
    def generate_explanation(
        cls,
        db: Session,
        document: Document,
        clauses: Optional[List[Any]] = None,
        chunk_types: Optional[Dict[int, str]] = None,
        on_dimension_done: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Extracts evidence for all 10 dimensions and synthesizes human-readable findings in one pass.
        """
        if clauses is None:
            clauses = db.query(DocumentClause).filter(DocumentClause.document_id == document.id).all()

        parsed_clauses = []
        for idx, c in enumerate(clauses):
            c_type = (chunk_types or {}).get(idx, "clause")
            clean_t = getattr(c, "clean_text", "") or getattr(c, "original_text", "")
            sec_t = getattr(c, "section_name", "") or "General Policy Terms"
            cat = getattr(c, "category", "") or "General"
            pg = getattr(c, "page_number", 1) or 1

            dim_scores = ClauseClassifier.score_clause_for_dimensions(
                clause_text=clean_t,
                section_name=sec_t,
                category=cat,
                page_number=pg,
                chunk_type=c_type,
                clause_embedding=None,
            )
            parsed_clauses.append({
                "clause": c,
                "dim_scores": dim_scores,
                "clean_text": clean_t,
            })

        total_dims = len(ClauseClassifier.DIMENSIONS)
        overview_text = (
            f"PolicyLens analyzed '{document.filename}' across {document.total_pages} pages "
            f"({document.total_words:,} words, {len(clauses)} indexed clauses). "
            f"Each dimension below translates verified policy clauses into plain English while keeping exact page citations."
        )

        used_clause_ids = set()
        dim_selections: Dict[str, Dict[str, Any]] = {}
        ordered_entries: List[Dict[str, Any]] = []

        for d_idx, dim in enumerate(ClauseClassifier.DIMENSIONS):
            key = dim["key"]
            title = dim["title"]
            min_score = dim.get("min_total_score", 0.50)
            require_sig = dim.get("require_signal", True)

            candidates = []
            for item in parsed_clauses:
                c = item["clause"]
                score, has_sig = item["dim_scores"].get(key, (0.0, False))
                if require_sig and not has_sig:
                    continue
                if score < min_score:
                    continue

                c_uid = getattr(c, "id", None) or id(c)
                adj_score = score - (0.06 if (c_uid in used_clause_ids and key != "overview") else 0.0)
                candidates.append((c, score, adj_score, item["clean_text"]))

            candidates.sort(key=lambda x: x[2], reverse=True)

            top_entries = []
            seen_prefixes = set()
            for c, raw_score, _, clean_t in candidates:
                sig_prefix = clean_t[:80].lower()
                if sig_prefix in seen_prefixes:
                    continue
                seen_prefixes.add(sig_prefix)
                top_entries.append((c, raw_score))
                if len(top_entries) >= 4:
                    break

            if top_entries:
                top_clauses = [e[0] for e in top_entries]
                for c in top_clauses:
                    c_uid = getattr(c, "id", None) or id(c)
                    used_clause_ids.add(c_uid)
                dim_selections[key] = {"title": title, "clauses": top_clauses}

            ordered_entries.append({
                "key": key,
                "title": title,
                "top_entries": top_entries,
            })

        # Single fast batch synthesis call across all found dimensions
        synthesized = LLMService.synthesize_all_dimensions_once(
            dims_clauses=dim_selections,
            filename=document.filename,
        )

        sections_found = []
        for d_idx, entry in enumerate(ordered_entries):
            key = entry["key"]
            title = entry["title"]
            top_entries = entry["top_entries"]

            if top_entries and key in synthesized:
                summary, key_points = synthesized[key]
                sources = []
                for c, raw_score in top_entries:
                    verbatim = " ".join((getattr(c, "original_text", "") or "").split()).strip()
                    sources.append({
                        "page": getattr(c, "page_number", 1),
                        "section": getattr(c, "section_name", None) or "Policy Section",
                        "clause_number": getattr(c, "clause_number", None),
                        "category": getattr(c, "category", None) or "General",
                        "relevance_score": min(0.99, max(0.55, round(float(raw_score), 2))),
                        "text": verbatim,
                    })

                sections_found.append({
                    "key": key,
                    "title": title,
                    "summary": summary,
                    "key_points": key_points,
                    "sources": sources,
                    "limitations": None,
                    "status": "found",
                })
            else:
                sections_found.append({
                    "key": key,
                    "title": title,
                    "summary": "Not specified in this policy document.",
                    "key_points": [],
                    "sources": [],
                    "limitations": "Not specified in this policy document.",
                    "status": "not_found",
                })

            if on_dimension_done:
                try:
                    on_dimension_done(d_idx + 1, total_dims, title)
                except Exception:
                    pass

        explanation_payload = {
            "pipeline_version": "3.1",
            "document_id": document.id,
            "filename": document.filename,
            "total_pages": document.total_pages,
            "generated_at": document.upload_date.isoformat() if document.upload_date else "",
            "overview": overview_text,
            "sections": sections_found,
        }

        try:
            document.explanation_json = json.dumps(explanation_payload)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to persist explanation JSON: {e}")
            db.rollback()

        return explanation_payload
