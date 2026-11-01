import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import json
import time
import threading
from typing import List, Dict, Any, Optional, Callable
import numpy as np
from app.core.config import settings
from app.core.logging import logger

class EmbeddingService:
    """
    High-Performance Offline Embedding Service supporting cached BAAI/bge-m3, MiniLM,
    and internal dense semantic vectorizer.
    Enforces thread-safe singleton loading, bounded sequence lengths (512 tokens),
    and incremental batch encoding with live progress reporting.
    """

    _model = None
    _model_name = "BAAI/bge-m3"
    _vector_dim = 1024
    _load_lock = threading.Lock()

    @classmethod
    def get_model(cls):
        if cls._model is None:
            with cls._load_lock:
                if cls._model is None:
                    from sentence_transformers import SentenceTransformer
                    import torch

                    # Optimize CPU worker thread count for maximum inference throughput
                    try:
                        num_cpus = os.cpu_count() or 4
                        torch.set_num_threads(min(8, num_cpus))
                    except Exception:
                        pass

                    preferred_models = [
                        "BAAI/bge-m3",
                        "sentence-transformers/all-MiniLM-L6-v2"
                    ]
                    if settings.EMBEDDING_MODEL_NAME not in preferred_models:
                        preferred_models.insert(0, settings.EMBEDDING_MODEL_NAME)

                    for target in preferred_models:
                        try:
                            logger.info(f"Loading cached embedding model '{target}'...")
                            model = SentenceTransformer(target, local_files_only=True)
                            
                            # Bound max sequence length to 512 tokens to prevent O(N^2) quadratic CPU stall
                            if hasattr(model, "max_seq_length"):
                                model.max_seq_length = 512

                            cls._model = model
                            cls._model_name = target
                            
                            # Get dimension safely across sentence-transformers versions
                            if hasattr(model, "get_sentence_embedding_dimension"):
                                cls._vector_dim = model.get_sentence_embedding_dimension()
                            elif hasattr(model, "get_embedding_dimension"):
                                cls._vector_dim = model.get_embedding_dimension()
                            else:
                                cls._vector_dim = 1024 if "bge-m3" in target else 384

                            logger.info(f"Loaded locally cached embedding model {target} (dim={cls._vector_dim}, max_seq_len=512).")
                            return cls._model
                        except Exception as e:
                            logger.debug(f"Could not load {target} with local_files_only: {e}")

                    logger.warning("Could not load neural embedding models from local cache. Using internal dense semantic vectorizer.")
                    cls._model = None
                    cls._model_name = "internal_dense_semantic_vectorizer"
                    cls._vector_dim = 256

        return cls._model

    @classmethod
    def get_model_name(cls) -> str:
        return cls._model_name or "BAAI/bge-m3"

    @classmethod
    def get_vector_dim(cls) -> int:
        return cls._vector_dim or 1024

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
    def encode_batch(
        cls,
        texts: List[str],
        batch_size: int = 16,
        on_batch_complete: Optional[Callable[[int, int, List[List[float]]], None]] = None
    ) -> List[List[float]]:
        """
        Batch encodes texts with incremental progress callbacks and batch-level timing logs.
        Guarantees that progress never freezes at 55%.
        """
        if not texts:
            return []

        model = cls.get_model()
        all_embeddings: List[List[float]] = []
        total_texts = len(texts)
        total_batches = (total_texts + batch_size - 1) // batch_size

        if model is not None:
            try:
                for batch_idx in range(total_batches):
                    t0_batch = time.time()
                    start_i = batch_idx * batch_size
                    end_i = min(start_i + batch_size, total_texts)
                    batch_texts = texts[start_i:end_i]

                    batch_embs = model.encode(
                        batch_texts,
                        batch_size=len(batch_texts),
                        normalize_embeddings=True,
                        show_progress_bar=False
                    )
                    batch_list = [e.tolist() if hasattr(e, "tolist") else list(e) for e in batch_embs]
                    all_embeddings.extend(batch_list)

                    t_batch = time.time() - t0_batch
                    logger.info(
                        f"[TIMING] BGE-M3 Batch {batch_idx + 1}/{total_batches} "
                        f"({len(batch_texts)} clauses encoded in {t_batch:.2f}s) "
                        f"[{end_i}/{total_texts} total]"
                    )

                    if on_batch_complete:
                        try:
                            on_batch_complete(batch_idx + 1, total_batches, batch_list)
                        except Exception as cb_err:
                            logger.debug(f"Error in batch completion callback: {cb_err}")

                return all_embeddings
            except Exception as e:
                logger.error(f"Error in batch model encoding: {e}")

        # Fallback dense encoder
        logger.warning("Using fallback dense encoder for batch.")
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
