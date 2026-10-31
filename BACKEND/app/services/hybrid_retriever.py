import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.db_models import DocumentClause
from app.services.embeddings import EmbeddingService
from app.services.bm25_retriever import get_bm25_index
from app.services.question_analyzer import QuestionAnalyzer
from app.core.config import settings
from app.core.logging import logger

class HybridRetriever:
    """
    Document-Isolated Dynamic Hybrid Retrieval Engine.
    Combines Dense Semantic Vectors (BGE-M3 / MiniLM), BM25 Sparse Keywords,
    and Question Intent Category Signals with dynamic weight adaptation.
    """

    @classmethod
    def retrieve(
        cls,
        db: Session,
        document_id: str,
        query: str,
        analysis: Dict[str, Any],
        top_k: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Retrieves candidate clauses strictly isolated to document_id.
        """
        # 1. Fetch all clauses for this specific document
        db_clauses = db.query(DocumentClause).filter(DocumentClause.document_id == document_id).all()
        if not db_clauses:
            return []

        clauses_data = []
        for c in db_clauses:
            embedding = None
            if c.embedding_json:
                try:
                    embedding = json.loads(c.embedding_json)
                except Exception:
                    pass

            sec_name = c.section_name or "General Terms"
            clause_num = c.clause_number or ""
            cat = c.category or "General"
            clean_t = c.clean_text or c.original_text
            search_t = f"[Section: {sec_name}] [Clause: {clause_num}] [Category: {cat}] {clean_t}"

            clauses_data.append({
                "id": c.id,
                "document_id": c.document_id,
                "page": c.page_number,
                "section": sec_name,
                "clause_number": c.clause_number,
                "category": cat,
                "confidence": c.classification_confidence or 0.8,
                "text": c.original_text,
                "clean_text": clean_t,
                "search_text": search_t,
                "embedding": embedding
            })

        expanded_query = analysis.get("expanded_query", query)
        intent = analysis.get("intent", "general_qa")
        is_comprehensive = analysis.get("is_comprehensive", False)

        # 2. Dense Semantic Search using query and expanded query
        query_embedding = EmbeddingService.encode_text(expanded_query)
        dense_scores: Dict[int, float] = {}
        for c in clauses_data:
            if c["embedding"]:
                sim = EmbeddingService.cosine_similarity(query_embedding, c["embedding"])
                norm_sim = max(0.0, (sim + 1.0) / 2.0)
                dense_scores[c["id"]] = norm_sim
            else:
                dense_scores[c["id"]] = 0.0

        # 3. BM25 Sparse Search
        bm25_idx = get_bm25_index(document_id, clauses_data)
        bm25_results = bm25_idx.search(expanded_query, top_k=len(clauses_data))
        bm25_scores: Dict[int, float] = {r["clause_id"]: r["bm25_score"] for r in bm25_results}

        # 4. Question Category Boosts
        category_boosts = analysis.get("category_boosts", {})

        # 5. Dynamic Weight Tuning
        if intent in ["limit_inquiry", "claim_inquiry"]:
            # High precision for numbers, rupee amounts, forms, specific names
            alpha = 0.40  # Dense
            beta = 0.45   # BM25
            gamma = 0.15  # Category
        elif intent in ["waiting_period_inquiry", "exclusion_inquiry"]:
            # High category priority
            alpha = 0.35
            beta = 0.30
            gamma = 0.35
        elif intent in ["overview_coverage"]:
            # High dense conceptual coverage
            alpha = 0.55
            beta = 0.30
            gamma = 0.15
        else:
            alpha = settings.HYBRID_ALPHA
            beta = settings.HYBRID_BETA
            gamma = settings.HYBRID_GAMMA

        scored_candidates = []
        for c in clauses_data:
            cid = c["id"]
            d_score = dense_scores.get(cid, 0.0)
            b_score = bm25_scores.get(cid, 0.0)
            cat_score = category_boosts.get(c["category"], 0.0)

            hybrid_score = (alpha * d_score) + (beta * b_score) + (gamma * cat_score)

            scored_candidates.append({
                **c,
                "dense_score": round(d_score, 4),
                "bm25_score": round(b_score, 4),
                "category_score": round(cat_score, 4),
                "hybrid_score": round(hybrid_score, 4)
            })

        scored_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
        retrieval_limit = 25 if is_comprehensive else top_k
        return scored_candidates[:retrieval_limit]
