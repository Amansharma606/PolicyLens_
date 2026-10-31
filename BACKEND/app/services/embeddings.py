import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import json
from typing import List, Dict, Any, Optional
import numpy as np
from app.core.config import settings
from app.core.logging import logger

class EmbeddingService:
    """
    Local Offline Embedding Service supporting cached BGE-M3, MiniLM, and internal dense semantic vectorizer.
    Guarantees no network hangs by enforcing offline execution.
    """

    _model = None
    _model_name = None
    _vector_dim = 384

    @classmethod
    def get_model(cls):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer

            # 1. Try BAAI/bge-m3 if requested or available locally
            preferred_models = [
                "BAAI/bge-m3",
                "sentence-transformers/all-MiniLM-L6-v2"
            ]
            if settings.EMBEDDING_MODEL_NAME not in preferred_models:
                preferred_models.insert(0, settings.EMBEDDING_MODEL_NAME)

            for target in preferred_models:
                try:
                    cls._model = SentenceTransformer(target, local_files_only=True)
                    cls._model_name = target
                    cls._vector_dim = cls._model.get_sentence_embedding_dimension()
                    logger.info(f"Loaded locally cached embedding model {target} (dim={cls._vector_dim}).")
                    return cls._model
                except Exception as e:
                    logger.debug(f"Could not load {target} with local_files_only: {e}")

            logger.warning("Could not load neural embedding models from local cache. Using internal dense semantic vectorizer.")
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
