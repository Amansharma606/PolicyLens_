import json
import os
from typing import List, Dict, Any, Optional
import numpy as np
from app.core.config import settings
from app.core.logging import logger

class EmbeddingService:
    """
    Embedding Service supporting BGE-M3, MiniLM (cached locally), and internal dense vectorizer.
    """

    _model = None
    _model_name = None
    _vector_dim = 384

    @classmethod
    def get_model(cls):
        if cls._model is None:
            # 1. Try local cached model (e.g. all-MiniLM-L6-v2)
            try:
                from sentence_transformers import SentenceTransformer
                # Try loading with local_files_only first to prevent unwanted network retries
                try:
                    cls._model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", local_files_only=True)
                    cls._model_name = "sentence-transformers/all-MiniLM-L6-v2"
                    cls._vector_dim = cls._model.get_sentence_embedding_dimension()
                    logger.info(f"Loaded locally cached embedding model {cls._model_name} (dim={cls._vector_dim}).")
                    return cls._model
                except Exception:
                    pass

                # If primary model is explicitly configured and not local-only:
                target = settings.EMBEDDING_MODEL_NAME
                cls._model = SentenceTransformer(target)
                cls._model_name = target
                cls._vector_dim = cls._model.get_sentence_embedding_dimension()
                logger.info(f"Loaded embedding model {target} (dim={cls._vector_dim}).")
                return cls._model
            except Exception as e:
                logger.warning(f"Could not load neural model: {e}. Using internal dense semantic vectorizer.")
                cls._model = None
                cls._model_name = "internal_dense_semantic_vectorizer"
                cls._vector_dim = 256
        return cls._model

    @classmethod
    def encode_text(cls, text: str) -> List[float]:
        model = cls.get_model()
        if model is not None:
            try:
                emb = model.encode(text, normalize_embeddings=True)
                return emb.tolist() if hasattr(emb, "tolist") else list(emb)
            except Exception as e:
                logger.error(f"Error in model encoding: {e}")

        return cls._fallback_dense_encode(text)

    @classmethod
    def encode_batch(cls, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        model = cls.get_model()
        if model is not None:
            try:
                embs = model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
                return [e.tolist() if hasattr(e, "tolist") else list(e) for e in embs]
            except Exception as e:
                logger.error(f"Error in batch model encoding: {e}")

        return [cls._fallback_dense_encode(t) for t in texts]

    @classmethod
    def cosine_similarity(cls, vec_a: List[float], vec_b: List[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @classmethod
    def _fallback_dense_encode(cls, text: str) -> List[float]:
        dim = cls._vector_dim
        vec = np.zeros(dim, dtype=np.float32)
        words = text.lower().split()
        for word in words:
            h1 = hash(word) % dim
            vec[h1] += 1.0
            for i in range(len(word) - 2):
                tri = word[i:i+3]
                h2 = hash(tri) % dim
                vec[h2] += 0.5

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()
