from typing import List, Dict, Any, Tuple
import re
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.db_models import DocumentClause
from app.services.question_analyzer import QuestionAnalyzer
from app.core.logging import logger


class CompletenessChecker:
    """
    Validates retrieved evidence completeness across required dimensions,
    performs secondary targeted expansion for missing dimensions or list/comparison queries,
    and enforces strict document-grounding abstention for unmentioned/out-of-scope topics.
    """

    @classmethod
    def verify_and_expand(
        cls,
        db: Session,
        document_id: str,
        retrieved_clauses: List[Dict[str, Any]],
        analysis: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], float, List[str], bool]:
        """
        Returns: (expanded_clauses, completeness_score, missing_categories, is_insufficient)
        """
        if not retrieved_clauses:
            return [], 0.0, analysis.get("required_categories", []), True

        # 1. Domain-agnostic Out-of-Scope / Missing Subject Gate
        distinctive_tokens = analysis.get("distinctive_tokens", [])
        detected_topics = analysis.get("all_topics", [])
        is_unrecognized = analysis.get("is_unrecognized_specific", False)

        # Build synonym lookup if topic matched
        topic_synonym_pool: List[str] = []
        for t in detected_topics:
            topic_synonym_pool.extend(QuestionAnalyzer.TOPIC_SYNONYMS.get(t, []))

        # For specific queries (e.g., "space tourism medical evacuation", "does PMSBY cover maternity",
        # "cosmetic dental veneers", "cryptocurrency loss"), verify distinctive tokens actually appear in this PDF!
        if distinctive_tokens and (is_unrecognized or analysis.get("response_style") == "yes_no_verification"):
            # Count how many distinctive tokens (or known topic synonyms) appear anywhere in document clauses
            doc_clauses_text = [
                (row[0] or "").lower()
                for row in db.query(DocumentClause.clean_text).filter(DocumentClause.document_id == document_id).all()
            ]
            full_doc_blob = " ".join(doc_clauses_text)

            matched_tokens = 0
            unmatched_rare_tokens = []
            for tok in distinctive_tokens:
                # Match token prefix (e.g., vaccinat -> vaccination, diabet -> diabetes, maternity)
                stem = tok[: max(4, len(tok) - 2)] if len(tok) >= 6 else tok
                found = bool(re.search(rf"\b{re.escape(stem)}", full_doc_blob))
                if not found and detected_topics:
                    # Check if a legitimate synonym for the matched topic is in the PDF (e.g. "childbirth"/"delivery" for "maternity")
                    found = any(syn.lower() in full_doc_blob for syn in topic_synonym_pool)
                if found:
                    matched_tokens += 1
                else:
                    unmatched_rare_tokens.append(tok)

            peak_prob = max((c.get("rerank_prob", c.get("rerank_score", 0.0)) for c in retrieved_clauses), default=0.0)
            peak_bm25 = max((c.get("bm25_score", 0.0) for c in retrieved_clauses), default=0.0)

            # Out-of-scope check:
            # A) Zero distinctive tokens exist in the PDF (e.g., asking PMSBY about "maternity")
            if matched_tokens == 0 and (len(distinctive_tokens) >= 1):
                logger.info(f"Out-of-scope abstention: none of {distinctive_tokens} appear in document {document_id}.")
                return [], 0.0, [], True

            # A2) Explicit queried insurance topic is completely absent from the PDF
            if detected_topics and topic_synonym_pool:
                primary_syns = QuestionAnalyzer.TOPIC_SYNONYMS.get(detected_topics[0], [])
                if primary_syns and not any(syn.lower() in full_doc_blob for syn in primary_syns):
                    logger.info(
                        f"Out-of-scope abstention: primary topic '{detected_topics[0]}' "
                        f"terms do not appear in document {document_id}."
                    )
                    return [], 0.0, [], True

            # B) Multi-word novel subject where rare key concepts (e.g. "space", "tourism") are missing
            # AND Cross-Encoder confidence isn't strongly decisive
            if is_unrecognized and unmatched_rare_tokens:
                missing_ratio = len(unmatched_rare_tokens) / len(distinctive_tokens)
                if missing_ratio >= 0.5 and peak_prob < 0.72:
                    logger.info(
                        f"Out-of-scope abstention: missing distinctive terms {unmatched_rare_tokens} "
                        f"(peak_prob={peak_prob:.2f}) in document {document_id}."
                    )
                    return [], 0.0, [], True

            # C) Very weak peak Cross-Encoder probability AND weak BM25 across all candidates
            if is_unrecognized and peak_prob < 0.12 and peak_bm25 < 0.15:
                logger.info(f"Low-evidence abstention: peak_prob={peak_prob:.2f}, peak_bm25={peak_bm25:.2f}.")
                return [], 0.0, [], True

        # 2. Check category coverage and expand if missing critical dimensions
        required_categories = analysis.get("required_categories", [])
        if not required_categories:
            return retrieved_clauses, 1.0, [], False

        retrieved_categories = set(c.get("category") for c in retrieved_clauses if c.get("category"))
        missing_categories = [cat for cat in required_categories if cat not in retrieved_categories]

        expanded_clauses = list(retrieved_clauses)
        existing_ids = set(c["id"] for c in expanded_clauses)

        if missing_categories and len(expanded_clauses) < 8:
            # Build search keywords dynamically from detected topics + distinctive tokens
            search_kws = list(distinctive_tokens[:4])
            for t in detected_topics[:2]:
                search_kws.extend(QuestionAnalyzer.TOPIC_SYNONYMS.get(t, [])[:5])
            search_kws = list(dict.fromkeys(k for k in search_kws if len(k) >= 3))

            for missing_cat in missing_categories:
                q_base = db.query(DocumentClause).filter(
                    DocumentClause.document_id == document_id,
                    DocumentClause.category == missing_cat,
                )

                candidates = []
                if search_kws:
                    filters = [DocumentClause.clean_text.ilike(f"%{kw}%") for kw in search_kws[:6]]
                    candidates = q_base.filter(or_(*filters)).limit(2).all()

                if not candidates and analysis.get("is_comprehensive"):
                    candidates = q_base.limit(2).all()

                for c in candidates:
                    if c.id not in existing_ids:
                        expanded_clauses.append({
                            "id": c.id,
                            "document_id": c.document_id,
                            "page": c.page_number,
                            "section": c.section_name or "Policy Clause",
                            "clause_number": c.clause_number,
                            "category": c.category,
                            "confidence": c.classification_confidence or 0.85,
                            "text": c.original_text,
                            "clean_text": c.clean_text,
                            "hybrid_score": 0.62,
                            "rerank_score": 0.62,
                            "rerank_prob": 0.62,
                            "supplemental": True,
                        })
                        existing_ids.add(c.id)
                        if len(expanded_clauses) >= 8:
                            break

        updated_categories = set(c.get("category") for c in expanded_clauses if c.get("category"))
        final_missing = [cat for cat in required_categories if cat not in updated_categories]
        total_req = len(required_categories)
        covered_req = total_req - len(final_missing)
        completeness_score = round(covered_req / total_req, 2) if total_req > 0 else 1.0

        return expanded_clauses, completeness_score, final_missing, False
