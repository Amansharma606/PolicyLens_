import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import re
from typing import List, Dict, Any, Tuple
from app.core.config import settings
from app.core.logging import logger

class CrossEncoderReranker:
    """
    Reranks retrieved candidate clauses using Cross-Encoder model
    or transparent lexical-semantic interaction fallback.
    """

    _model = None
    _is_loaded = False

    @classmethod
    def get_model(cls):
        if not cls._is_loaded:
            try:
                from sentence_transformers import CrossEncoder
                target = settings.RERANKER_MODEL_NAME
                cls._model = CrossEncoder(target, max_length=512, local_files_only=True)
                logger.info("Loaded locally cached CrossEncoder reranker successfully.")
            except Exception as e:
                logger.warning(f"CrossEncoder reranker not loaded offline ({e}). Using transparent interaction reranking fallback.")
                cls._model = None
            cls._is_loaded = True
        return cls._model

    @classmethod
    def rerank(cls, query: str, candidate_clauses: List[Dict[str, Any]], top_k: int = 8) -> List[Dict[str, Any]]:
        if not candidate_clauses:
            return []

        model = cls.get_model()
        if model is not None:
            try:
                # Pair query with section-enriched text for stronger Cross-Encoder alignment
                pairs = []
                for c in candidate_clauses:
                    sec = c.get("section") or "General Terms"
                    text = c.get("text", "")
                    pairs.append([query, f"[Section: {sec}] {text}"])

                scores = model.predict(pairs)
                for idx, sc in enumerate(scores):
                    candidate_clauses[idx]["rerank_score"] = float(sc)
                candidate_clauses.sort(key=lambda x: x["rerank_score"], reverse=True)
                return candidate_clauses[:top_k]
            except Exception as e:
                logger.error(f"Error in CrossEncoder reranking: {e}")

        # Transparent interaction reranking fallback
        query_terms = set(re.findall(r"\w{3,}", query.lower()))
        for c in candidate_clauses:
            text = c["text"].lower()
            sec = (c.get("section") or "").lower()
            matches = sum(1 for t in query_terms if t in text)
            sec_matches = sum(1 for t in query_terms if t in sec)
            density = matches / (len(text.split()) + 1)
            raw_score = (matches * 1.5) + (sec_matches * 2.0) + (density * 5.0) + (c.get("hybrid_score", 0.5))
            c["rerank_score"] = round(raw_score, 4)

        candidate_clauses.sort(key=lambda x: x["rerank_score"], reverse=True)
        return candidate_clauses[:top_k]
