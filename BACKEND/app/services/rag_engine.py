import time
import json
from typing import Dict, Any, Optional, List, Iterator
from sqlalchemy.orm import Session
from app.models.db_models import Document, Conversation, ChatMessage, DocumentClause
from app.services.question_analyzer import QuestionAnalyzer
from app.services.hybrid_retriever import HybridRetriever
from app.services.reranker import CrossEncoderReranker
from app.services.completeness_checker import CompletenessChecker
from app.services.llm_service import LLMService
from app.services.embeddings import EmbeddingService
from app.core.config import settings
from app.core.logging import logger


class RAGEngine:
    """
    Orchestrates PolicyLens Hybrid RAG (Follow-Up Contextualization + Hybrid BM25/Dense +
    Cross-Encoder Reranking + Completeness Verification + Real-Time Streaming Local LLM)
    and Baseline Dense RAG.
    """

    @classmethod
    def _prepare_rag_evidence(
        cls,
        db: Session,
        document_id: str,
        question: str,
        user_id: Optional[str],
        conversation_id: Optional[str],
        use_baseline: bool,
    ):
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document with ID {document_id} not found.")

        conv = None
        conv_context: List[Dict[str, str]] = []
        if conversation_id:
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if conv:
                recent_msgs = (
                    db.query(ChatMessage)
                    .filter(ChatMessage.conversation_id == conv.id)
                    .order_by(ChatMessage.id)
                    .all()
                )
                conv_context = [{"role": m.role, "content": m.content} for m in recent_msgs]

        if not conv:
            conv = Conversation(
                document_id=document_id,
                user_id=user_id or doc.user_id,
                title=question[:40] + ("..." if len(question) > 40 else ""),
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)

        user_msg = ChatMessage(
            conversation_id=conv.id,
            document_id=document_id,
            role="user",
            content=question,
        )
        db.add(user_msg)
        db.commit()

        if use_baseline:
            q_emb = EmbeddingService.encode_text(question)
            clauses = db.query(DocumentClause).filter(DocumentClause.document_id == document_id).all()
            scored = []
            for c in clauses:
                emb = json.loads(c.embedding_json) if c.embedding_json else None
                sim = EmbeddingService.cosine_similarity(q_emb, emb) if emb else 0.0
                norm_sim = (sim + 1.0) / 2.0
                scored.append({
                    "id": c.id,
                    "page": c.page_number,
                    "section": c.section_name or "Policy",
                    "clause_number": c.clause_number,
                    "category": c.category or "General",
                    "text": c.original_text,
                    "hybrid_score": norm_sim,
                    "rerank_score": norm_sim,
                })
            scored.sort(key=lambda x: x["hybrid_score"], reverse=True)
            final_evidence = scored[:5]
            analysis = {"topic": "general", "intent": "general_qa", "response_style": "general_explanation", "language": QuestionAnalyzer.detect_language(question)}
            is_insufficient = (len(final_evidence) == 0)
            completeness_score = 0.50
            pipeline_type = "Baseline_Conventional_RAG"
            retrieved_categories = list(set(c["category"] for c in final_evidence))
            topic = "general"
        else:
            analysis = QuestionAnalyzer.analyze(question, conversation_context=conv_context)
            topic = analysis.get("topic", "general")
            retrieval_q = analysis.get("contextualized_question", question)

            candidates = HybridRetriever.retrieve(
                db=db,
                document_id=document_id,
                query=retrieval_q,
                analysis=analysis,
                top_k=16,
            )

            rerank_k = 8 if analysis.get("is_comprehensive") else 6
            if settings.USE_NEURAL_EMBEDDINGS and CrossEncoderReranker._model is not None:
                reranked = CrossEncoderReranker.rerank(
                    query=retrieval_q,
                    candidate_clauses=candidates,
                    top_k=rerank_k,
                )
            else:
                reranked = HybridRetriever.fast_rerank(
                    query=retrieval_q,
                    candidate_clauses=candidates,
                    analysis=analysis,
                    top_k=rerank_k,
                )

            final_evidence, completeness_score, _, is_insufficient = CompletenessChecker.verify_and_expand(
                db=db,
                document_id=document_id,
                retrieved_clauses=reranked,
                analysis=analysis,
            )

            pipeline_type = "PolicyLens_Hybrid_RAG"
            retrieved_categories = list(set(c["category"] for c in final_evidence if c.get("category")))

        return {
            "conv": conv,
            "conv_context": conv_context,
            "analysis": analysis,
            "topic": topic,
            "final_evidence": final_evidence,
            "is_insufficient": is_insufficient,
            "completeness_score": completeness_score,
            "retrieved_categories": retrieved_categories,
            "pipeline_type": pipeline_type,
        }

    @classmethod
    def stream_question(
        cls,
        db: Session,
        document_id: str,
        question: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        use_baseline: bool = False,
    ) -> Iterator[Dict[str, Any]]:
        """
        Real-time streaming Q&A generator yielding SSE events:
        - {'event': 'meta', ...} immediately after retrieval (~0.1s)
        - {'event': 'token', 'token': '...'} word/token by token
        - {'event': 'done', ...} after saving assistant reply to DB
        """
        start_time = time.time()
        prep = cls._prepare_rag_evidence(db, document_id, question, user_id, conversation_id, use_baseline)
        conv = prep["conv"]

        yield {
            "event": "meta",
            "conversation_id": conv.id,
            "topic": prep["topic"],
            "language": prep["analysis"].get("language", "english"),
            "pipeline_type": prep["pipeline_type"],
        }

        final_result = None
        for chunk in LLMService.stream_grounded_answer(
            question=question,
            retrieved_clauses=prep["final_evidence"],
            analysis=prep["analysis"],
            conversation_context=prep["conv_context"],
            is_insufficient=prep["is_insufficient"],
        ):
            if chunk["type"] == "token":
                yield {"event": "token", "token": chunk["token"]}
            elif chunk["type"] == "final":
                final_result = chunk

        if final_result is None:
            final_result = {"answer": "", "status": "insufficient_evidence", "citations": []}

        latency = round(time.time() - start_time, 2)

        bot_msg = ChatMessage(
            conversation_id=conv.id,
            document_id=document_id,
            role="assistant",
            content=final_result["answer"],
            topic=prep["topic"],
            status=final_result["status"],
            sources_json=json.dumps(final_result["citations"]),
        )
        db.add(bot_msg)
        db.commit()

        yield {
            "event": "done",
            "answer": final_result["answer"],
            "conversation_id": conv.id,
            "topic": prep["topic"],
            "status": final_result["status"],
            "sources": final_result["citations"],
            "completeness_score": prep["completeness_score"],
            "retrieved_categories": prep["retrieved_categories"],
            "pipeline_type": prep["pipeline_type"],
            "latency_seconds": latency,
        }

    @classmethod
    def answer_question(
        cls,
        db: Session,
        document_id: str,
        question: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        use_baseline: bool = False,
    ) -> Dict[str, Any]:
        start_time = time.time()
        prep = cls._prepare_rag_evidence(db, document_id, question, user_id, conversation_id, use_baseline)
        conv = prep["conv"]

        llm_result = LLMService.generate_grounded_answer(
            question=question,
            retrieved_clauses=prep["final_evidence"],
            analysis=prep["analysis"],
            conversation_context=prep["conv_context"],
            is_insufficient=prep["is_insufficient"],
        )

        latency = round(time.time() - start_time, 2)

        bot_msg = ChatMessage(
            conversation_id=conv.id,
            document_id=document_id,
            role="assistant",
            content=llm_result["answer"],
            topic=prep["topic"],
            status=llm_result["status"],
            sources_json=json.dumps(llm_result["citations"]),
        )
        db.add(bot_msg)
        db.commit()

        return {
            "answer": llm_result["answer"],
            "conversation_id": conv.id,
            "topic": prep["topic"],
            "status": llm_result["status"],
            "sources": llm_result["citations"],
            "completeness_score": prep["completeness_score"],
            "retrieved_categories": prep["retrieved_categories"],
            "pipeline_type": prep["pipeline_type"],
            "latency_seconds": latency,
        }
