from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.logging import logger
from app.db.database import init_db
from app.api import health, auth, documents, chat
from app.services.llm_service import LLMService

# Initialize Database Schema & Seed default accounts
init_db()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_TITLE,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)


@app.on_event("startup")
def startup_event():
    """
    Fast startup (<0.3s): warm configured LLM backend asynchronously without blocking on PyTorch.
    """
    import threading

    def _warm_llm():
        try:
            LLMService.warmup()
        except Exception as le:
            logger.debug(f"LLM warmup note: {le}")

    threading.Thread(target=_warm_llm, daemon=True, name="LLMWarmup").start()
    logger.info("PolicyLens backend online (instant BM25+TF-IDF indexing + streaming QA).")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred while processing the insurance policy request."}
    )


app.include_router(health.router, prefix=settings.API_PREFIX)
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(documents.router, prefix=settings.API_PREFIX)
app.include_router(chat.router, prefix=settings.API_PREFIX)


@app.get("/")
def root():
    return {
        "app": settings.PROJECT_NAME,
        "title": settings.PROJECT_TITLE,
        "status": "online",
        "docs": "/docs",
        "api_health": f"{settings.API_PREFIX}/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
