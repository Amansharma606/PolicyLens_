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
    Document-Isolated Hybrid Retrieval Engine.
    Combines Dense Semantic Vectors (BGE-M3), BM25 Sparse Keywords,
    and Question Intent Category Signals.
    """

    @classmethod
    def retrieve(
        cls,
        db: Session,
        document_id: str,
        query: str,
        analysis: Dict[str, Any],
        top_k: int = 12
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

            clauses_data.append({
                "id": c.id,
                "document_id": c.document_id,
                "page": c.page_number,
                "section": c.section_name or "General Terms",
                "clause_number": c.clause_number,
                "category": c.category or "General",
                "confidence": c.classification_confidence or 0.8,
                "text": c.original_text,
                "clean_text": c.clean_text or c.original_text,
                "embedding": embedding
            })

        # 2. Dense Semantic Search
        query_embedding = EmbeddingService.encode_text(query)
        dense_scores: Dict[int, float] = {}
        for c in clauses_data:
            if c["embedding"]:
                sim = EmbeddingService.cosine_similarity(query_embedding, c["embedding"])
                # Normalize cosine similarity [-1, 1] -> [0, 1]
                norm_sim = max(0.0, (sim + 1.0) / 2.0)
                dense_scores[c["id"]] = norm_sim
            else:
                dense_scores[c["id"]] = 0.0

        # 3. BM25 Sparse Search
        bm25_idx = get_bm25_index(document_id, clauses_data)
        bm25_results = bm25_idx.search(query, top_k=len(clauses_data))
        bm25_scores: Dict[int, float] = {r["clause_id"]: r["bm25_score"] for r in bm25_results}

        # 4. Question Category Boosts
        category_boosts = analysis.get("category_boosts", {})

        # 5. Hybrid Scoring Equation:
        # FinalScore = α × DenseScore + β × BM25Score + γ × CategoryScore
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
        return scored_candidates[:top_k]
