from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

@router.get("/health", tags=["Health"])
def health_check():
    """
    Returns system health, active models, and pipeline configurations.
    """
    return {
        "status": "ok",
        "app": settings.PROJECT_NAME,
        "title": settings.PROJECT_TITLE,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "models": {
            "embedding": settings.EMBEDDING_MODEL_NAME,
            "classifier": settings.CLASSIFIER_MODEL_NAME,
            "reranker": settings.RERANKER_MODEL_NAME,
            "hybrid_weights": {
                "alpha_dense": settings.HYBRID_ALPHA,
                "beta_bm25": settings.HYBRID_BETA,
                "gamma_category": settings.HYBRID_GAMMA
            }
        }
    }
