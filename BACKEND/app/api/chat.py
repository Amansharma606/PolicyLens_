import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.db_models import Document, Conversation, ChatMessage, User
from app.models.schemas import (
    QuestionRequest,
    AnswerResponse,
    ConversationHistoryResponse,
    ConversationSummary,
    ChatMessageSchema,
    SourceCitation
)
from app.services.rag_engine import RAGEngine
from app.core.security import get_current_user_optional
from app.core.logging import logger

router = APIRouter()

@router.post("/documents/{document_id}/ask", response_model=AnswerResponse, tags=["Chat & RAG"])
def ask_document_question(
    document_id: str,
    request: QuestionRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    RAG Question-Answering endpoint grounded strictly in the specified document.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question text cannot be empty."
        )

    # Document ownership / isolation verification
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy document '{document_id}' not found."
        )

    if doc.status == "scanned_ocr_required":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This document is an unsearchable scanned image PDF. OCR processing is required before asking questions."
        )

    user_email = current_user.get("sub") if current_user else "analyst@policylens.ai"
    user = db.query(User).filter(User.email == user_email).first()
    user_id = user.id if user else doc.user_id

    try:
        result = RAGEngine.answer_question(
            db=db,
            document_id=document_id,
            question=request.question.strip(),
            user_id=user_id,
            conversation_id=request.conversation_id,
            use_baseline=request.use_baseline or False
        )
        return AnswerResponse(
            answer=result["answer"],
            conversation_id=result["conversation_id"],
            topic=result["topic"],
            status=result["status"],
            sources=[SourceCitation(**s) for s in result["sources"]],
            completeness_score=result.get("completeness_score", 1.0),
            retrieved_categories=result.get("retrieved_categories", []),
            pipeline_type=result.get("pipeline_type", "PolicyLens_Hybrid_RAG")
        )
    except Exception as e:
        logger.error(f"Error answering question: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating grounded answer: {str(e)}"
        )

@router.get("/documents/{document_id}/history", response_model=ConversationHistoryResponse, tags=["Chat & RAG"])
def get_document_history(
    document_id: str,
    conversation_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Retrieves message history for a given policy document conversation.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if conversation_id:
        conv = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.document_id == document_id
        ).first()
    else:
        # Get most recent conversation for this document
        conv = db.query(Conversation).filter(
            Conversation.document_id == document_id
        ).order_by(Conversation.updated_at.desc()).first()

    if not conv:
        return ConversationHistoryResponse(
            conversation_id="",
            document_id=document_id,
            filename=doc.filename,
            title="New Conversation",
            messages=[]
        )

    db_messages = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conv.id
    ).order_by(ChatMessage.id).all()

    formatted_messages = []
    for m in db_messages:
        sources = []
        if m.sources_json:
            try:
                sources = [SourceCitation(**s) for s in json.loads(m.sources_json)]
            except Exception:
                pass

        formatted_messages.append(ChatMessageSchema(
            id=m.id,
            role=m.role,
            content=m.content,
            topic=m.topic,
            status=m.status,
            sources=sources,
            timestamp=m.created_at.isoformat() if m.created_at else ""
        ))

    return ConversationHistoryResponse(
        conversation_id=conv.id,
        document_id=document_id,
        filename=doc.filename,
        title=conv.title,
        messages=formatted_messages
    )

@router.get("/conversations", response_model=List[ConversationSummary], tags=["Chat & RAG"])
def list_conversations(
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Lists all saved conversations across documents.
    """
    convs = db.query(Conversation).order_by(Conversation.updated_at.desc()).all()
    results = []
    for c in convs:
        doc = db.query(Document).filter(Document.id == c.document_id).first()
        msg_count = db.query(ChatMessage).filter(ChatMessage.conversation_id == c.id).count()
        results.append(ConversationSummary(
            conversation_id=c.id,
            document_id=c.document_id,
            filename=doc.filename if doc else "Deleted Document",
            title=c.title,
            message_count=msg_count,
            last_updated=c.updated_at.isoformat() if c.updated_at else ""
        ))
    return results

@router.delete("/conversations/{conversation_id}", tags=["Chat & RAG"])
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """
    Deletes a conversation thread and its associated chat history.
    """
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    db.delete(conv)
    db.commit()
    return {"message": "Conversation deleted successfully."}
