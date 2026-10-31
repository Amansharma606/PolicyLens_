import re
from typing import List, Dict, Any, Optional
import numpy as np
from rank_bm25 import BM25Okapi
from app.core.logging import logger

class BM25Retriever:
    """
    In-memory BM25 Okapi Sparse Keyword Retrieval Index.
    Maintains document-specific tokenized inverted indexes to guarantee strict document isolation.
    """

    def __init__(self, document_id: str, clauses: List[Dict[str, Any]]):
        self.document_id = document_id
        self.clauses = clauses
        self.tokenized_corpus = [
            self._tokenize(c.get("search_text") or c.get("clean_text") or c.get("text", ""))
            for c in clauses
        ]
        if self.tokenized_corpus and any(len(doc) > 0 for doc in self.tokenized_corpus):
            self.bm25 = BM25Okapi(self.tokenized_corpus)
        else:
            self.bm25 = None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        # Clean punctuation, lower-case, split tokens
        tokens = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower())
        return tokens

    def search(self, query: str, top_k: int = 15) -> List[Dict[str, Any]]:
        """
        Retrieves top clauses with normalized BM25 scores in [0.0, 1.0].
        """
        if not self.bm25 or not self.clauses:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        raw_scores = self.bm25.get_scores(query_tokens)
        max_score = float(np.max(raw_scores)) if len(raw_scores) > 0 else 0.0

        results = []
        for idx, score in enumerate(raw_scores):
            if score <= 0.0:
                norm_score = 0.0
            elif max_score > 0:
                norm_score = float(score / max_score)
            else:
                norm_score = 0.0

            results.append({
                "clause_id": self.clauses[idx]["id"],
                "clause": self.clauses[idx],
                "bm25_score": norm_score
            })

        results.sort(key=lambda x: x["bm25_score"], reverse=True)
        return results[:top_k]

# Global cache of active BM25 indices per document
_bm25_cache: Dict[str, BM25Retriever] = {}

def get_bm25_index(document_id: str, clauses: List[Dict[str, Any]]) -> BM25Retriever:
    if document_id not in _bm25_cache:
        _bm25_cache[document_id] = BM25Retriever(document_id, clauses)
    return _bm25_cache[document_id]

def invalidate_bm25_index(document_id: str):
    if document_id in _bm25_cache:
        del _bm25_cache[document_id]
