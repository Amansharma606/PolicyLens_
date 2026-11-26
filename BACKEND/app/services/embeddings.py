import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import json
import time
import zlib
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import numpy as np
from app.core.config import settings
from app.core.logging import logger

class EmbeddingService:
    """
    High-Performance Embedding Service supporting cached neural models (BGE-M3, MiniLM)
    and an ultra-fast, deterministic dense semantic vectorizer.
    Guarantees zero-hang offline execution, persistent singleton initialization,
    and batched live progress reporting.
    """

    _model = None
    _model_name = "internal_dense_semantic_vectorizer"
    _vector_dim = 256
    _is_initialized = False
    _load_lock = threading.Lock()

    @classmethod
    def _has_local_model_cache(cls, model_name: str) -> bool:
        """
        Fast disk check to see if local HuggingFace cache contains model weights.
        Avoids triggering slow dynamic imports or network/offline errors when no cache exists.
        """
        try:
            hub_dir = Path.home() / ".cache" / "huggingface" / "hub"
            if not hub_dir.exists():
                return False
            safe_name = "models--" + model_name.replace("/", "--")
            model_path = hub_dir / safe_name
            if model_path.exists():
                # Check that snapshots exist with actual files
                snapshots_dir = model_path / "snapshots"
                if snapshots_dir.exists() and any(snapshots_dir.iterdir()):
                    return True
            # Also check if it is a direct local directory path
            direct_path = Path(model_name)
            if direct_path.exists() and direct_path.is_dir():
                return True
        except Exception:
            pass
        return False

    @classmethod
    def initialize(cls):
        """
        Idempotent singleton initializer. Inspects local models and initializes the appropriate
        embedder. Once executed, future checks take 0 ms.
        """
        if cls._is_initialized:
            return cls._model

        with cls._load_lock:
            if cls._is_initialized:
                return cls._model

            preferred_models = [
                settings.EMBEDDING_MODEL_NAME,
                "sentence-transformers/all-MiniLM-L6-v2",
                "BAAI/bge-m3",
            ]
            # On CPU without CUDA, prefer fast MiniLM (~125 clauses/s) unless explicitly overridden
            try:
                import torch
                if not torch.cuda.is_available() and settings.EMBEDDING_MODEL_NAME == "BAAI/bge-m3" and not os.getenv("FORCE_CPU_BGE_M3"):
                    if cls._has_local_model_cache("sentence-transformers/all-MiniLM-L6-v2"):
                        preferred_models = ["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-m3"]
            except Exception:
                pass
            # Deduplicate preserving order
            seen = set()
            targets_to_check = []
            for m in preferred_models:
                if m and m not in seen:
                    seen.add(m)
                    targets_to_check.append(m)

            found_target = None
            for target in targets_to_check:
                if cls._has_local_model_cache(target):
                    found_target = target
                    break

            if found_target:
                try:
                    logger.info(f"Loading local cached embedding model '{found_target}'...")
                    from sentence_transformers import SentenceTransformer
                    import torch

                    num_cpus = os.cpu_count() or 4
                    torch.set_num_threads(min(10, num_cpus))

                    model = SentenceTransformer(found_target, local_files_only=True)
                    if hasattr(model, "max_seq_length"):
                        model.max_seq_length = 384 if "minilm" in found_target.lower() else 512

                    cls._model = model
                    cls._model_name = found_target

                    if hasattr(model, "get_embedding_dimension"):
                        cls._vector_dim = model.get_embedding_dimension()
                    elif hasattr(model, "get_sentence_embedding_dimension"):
                        cls._vector_dim = model.get_sentence_embedding_dimension()
                    else:
                        cls._vector_dim = 1024 if "bge-m3" in found_target else 384

                    logger.info(f"Successfully loaded embedding model '{found_target}' (dim={cls._vector_dim}).")
                except Exception as e:
                    logger.warning(f"Could not load '{found_target}' ({e}). Falling back to fast dense vectorizer.")
                    cls._model = None
                    cls._model_name = "internal_dense_semantic_vectorizer"
                    cls._vector_dim = 256
            else:
                logger.info("Using internal high-speed dense semantic vectorizer (dim=256).")
                cls._model = None
                cls._model_name = "internal_dense_semantic_vectorizer"
                cls._vector_dim = 256

            cls._is_initialized = True
            return cls._model

    @classmethod
    def get_model(cls):
        if not cls._is_initialized:
            cls.initialize()
        return cls._model

    @classmethod
    def get_model_name(cls) -> str:
        if not cls._is_initialized:
            cls.initialize()
        return cls._model_name

    @classmethod
    def get_vector_dim(cls) -> int:
        if not cls._is_initialized:
            cls.initialize()
        return cls._vector_dim

    @classmethod
    def encode_text(cls, text: str) -> List[float]:
        model = cls.get_model()
        if model is not None:
            try:
                emb = model.encode(text, normalize_embeddings=True)
                return emb.tolist() if hasattr(emb, "tolist") else list(emb)
            except Exception as e:
                logger.error(f"Error in neural model encoding: {e}")

        return cls._fallback_dense_encode(text)

    @classmethod
    def encode_batch(
        cls,
        texts: List[str],
        batch_size: int = 64,
        on_batch_complete: Optional[Callable[[int, int, List[List[float]]], None]] = None
    ) -> List[List[float]]:
        """
        Batch encodes texts with incremental progress callbacks and high throughput.
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

                    if on_batch_complete:
                        try:
                            on_batch_complete(batch_idx + 1, total_batches, batch_list)
                        except Exception as cb_err:
                            logger.debug(f"Error in batch completion callback: {cb_err}")

                return all_embeddings
            except Exception as e:
                logger.error(f"Error in batch neural encoding: {e}. Falling back to dense vectorizer.")

        # High-speed deterministic fallback vectorizer with batch callbacks
        for batch_idx in range(total_batches):
            start_i = batch_idx * batch_size
            end_i = min(start_i + batch_size, total_texts)
            batch_texts = texts[start_i:end_i]
            batch_embs = [cls._fallback_dense_encode(t) for t in batch_texts]
            all_embeddings.extend(batch_embs)

            if on_batch_complete:
                try:
                    on_batch_complete(batch_idx + 1, total_batches, batch_embs)
                except Exception as cb_err:
                    logger.debug(f"Error in batch callback: {cb_err}")

        return all_embeddings

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
        """
        Fast deterministic dense vector encoder.
        Uses CRC32 hashing over words and tri-grams to produce a normalized 256-d vector.
        100% reproducible across Python process restarts and platforms.
        """
        dim = cls._vector_dim
        vec = np.zeros(dim, dtype=np.float32)
        if not text:
            return vec.tolist()

        words = text.lower().split()
        for word in words:
            encoded_word = word.encode("utf-8", errors="ignore")
            h1 = zlib.crc32(encoded_word) % dim
            vec[h1] += 1.0

            w_len = len(word)
            if w_len > 3:
                for i in range(w_len - 2):
                    tri = word[i:i+3].encode("utf-8", errors="ignore")
                    h2 = zlib.crc32(tri) % dim
                    vec[h2] += 0.5

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()

