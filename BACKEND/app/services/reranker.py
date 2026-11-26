import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import math
import re
import threading
from typing import List, Dict, Any
from app.core.config import settings
from app.core.logging import logger


class CrossEncoderReranker:
    """
    Reranks retrieved candidate clauses using locally cached Cross-Encoder model
    with calibrated sigmoid relevance probabilities [0.0, 1.0],
    falling back to lexical-semantic interaction scoring if Cross-Encoder is unavailable.
    """

    _model = None
    _is_loaded = False
    _load_lock = threading.Lock()

    @classmethod
    def get_model(cls):
        if not cls._is_loaded:
            with cls._load_lock:
                if not cls._is_loaded:
                    try:
                        from sentence_transformers import CrossEncoder
                        target = settings.RERANKER_MODEL_NAME
                        cls._model = CrossEncoder(target, max_length=512, local_files_only=True)
                        logger.info("Loaded locally cached CrossEncoder reranker successfully.")
                    except Exception as e:
                        logger.warning(f"CrossEncoder reranker not loaded offline ({e}). Using interaction reranking fallback.")
                        cls._model = None
                    cls._is_loaded = True
        return cls._model

    @staticmethod
    def _sigmoid(logit: float) -> float:
        if logit >= 0:
            z = math.exp(-min(20.0, logit))
            return 1.0 / (1.0 + z)
        else:
            z = math.exp(max(-20.0, logit))
            return z / (1.0 + z)

    @classmethod
    def rerank(cls, query: str, candidate_clauses: List[Dict[str, Any]], top_k: int = 8) -> List[Dict[str, Any]]:
        if not candidate_clauses:
            return []

        model = cls.get_model()
        if model is not None:
            try:
                pairs = []
                for c in candidate_clauses:
                    sec = c.get("section") or "General Terms"
                    text = c.get("clean_text") or c.get("text", "")
                    pairs.append([query, f"[{sec}] {text[:1200]}"])

                logits = model.predict(pairs)
                for idx, sc in enumerate(logits):
                    logit = float(sc)
                    prob = cls._sigmoid(logit)
                    # Mild boost for strong hybrid BM25+Dense score so exact policy tables never lose to vague mentions
                    hyb = float(candidate_clauses[idx].get("hybrid_score", 0.5))
                    blended = (0.78 * prob) + (0.22 * min(1.0, hyb))
                    candidate_clauses[idx]["rerank_logit"] = round(logit, 4)
                    candidate_clauses[idx]["rerank_prob"] = round(prob, 4)
                    candidate_clauses[idx]["rerank_score"] = round(blended, 4)

                candidate_clauses.sort(key=lambda x: x["rerank_score"], reverse=True)
                return candidate_clauses[:top_k]
            except Exception as e:
                logger.error(f"Error in CrossEncoder reranking: {e}")

        # Transparent lexical-semantic interaction fallback (calibrated [0.0, 1.0])
        query_terms = set(re.findall(r"\w{3,}", query.lower()))
        stop = {"what", "does", "this", "policy", "cover", "are", "the", "for", "with", "under"}
        query_terms -= stop
        if not query_terms:
            query_terms = set(re.findall(r"\w{2,}", query.lower()))

        for c in candidate_clauses:
            text = (c.get("clean_text") or c["text"]).lower()
            sec = (c.get("section") or "").lower()
            matches = sum(1 for t in query_terms if t in text)
            sec_matches = sum(1 for t in query_terms if t in sec)
            coverage_ratio = matches / max(1, len(query_terms))
            sec_bonus = min(0.25, sec_matches * 0.12)
            hyb = float(c.get("hybrid_score", 0.5))
            raw_score = min(0.99, (0.45 * coverage_ratio) + sec_bonus + (0.45 * hyb))
            c["rerank_prob"] = round(raw_score, 4)
            c["rerank_score"] = round(raw_score, 4)

        candidate_clauses.sort(key=lambda x: x["rerank_score"], reverse=True)
        return candidate_clauses[:top_k]
