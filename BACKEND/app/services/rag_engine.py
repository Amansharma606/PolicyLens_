import time
import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models.db_models import Document, Conversation, ChatMessage, DocumentClause
from app.services.question_analyzer import QuestionAnalyzer
from app.services.hybrid_retriever import HybridRetriever
from app.services.reranker import CrossEncoderReranker
from app.services.completeness_checker import CompletenessChecker
from app.services.llm_service import LLMService
from app.services.embeddings import EmbeddingService
from app.core.logging import logger

class RAGEngine:
    """
    Orchestrates both:
    1. Proposed PolicyLens RAG (Structure-Aware + Classification + Hybrid + Rerank + Completeness)
    2. Baseline RAG (Fixed Dense Retrieval Top-K)
    for transparent research comparison.
    """

    @classmethod
    def answer_question(
        cls,
        db: Session,
        document_id: str,
        question: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        use_baseline: bool = False
    ) -> Dict[str, Any]:
        start_time = time.time()

        # Verify Document exists
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document with ID {document_id} not found.")

        # Manage conversation thread
        conv = None
        conv_context = []
        if conversation_id:
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if conv:
                recent_msgs = db.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id).order_by(ChatMessage.id).all()
                conv_context = [{"role": m.role, "content": m.content} for m in recent_msgs]
        
        if not conv:
            conv = Conversation(
                document_id=document_id,
                user_id=user_id or doc.user_id,
                title=question[:40] + ("..." if len(question) > 40 else "")
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)

        # Record User Message
        user_msg = ChatMessage(
            conversation_id=conv.id,
            document_id=document_id,
            role="user",
            content=question
        )
        db.add(user_msg)
        db.commit()

        # =========================================================================
        # PIPELINE SELECTION
        # =========================================================================
        if use_baseline:
            # ---------------------------------------------------------------------
            # BASELINE RAG: Simple Dense Cosine Top-K without Structure/Intent/BM25
            # ---------------------------------------------------------------------
            logger.info(f"Executing BASELINE RAG for document {document_id}...")
            q_emb = EmbeddingService.encode_text(question)
            clauses = db.query(DocumentClause).filter(DocumentClause.document_id == document_id).all()
            scored = []
            for c in clauses:
                emb = json.loads(c.embedding_json) if c.embedding_json else None
                sim = EmbeddingService.cosine_similarity(q_emb, emb) if emb else 0.0
                scored.append({
                    "id": c.id,
                    "page": c.page_number,
                    "section": c.section_name or "Policy",
                    "clause_number": c.clause_number,
                    "category": c.category or "General",
                    "text": c.original_text,
                    "hybrid_score": (sim + 1.0) / 2.0,
                    "rerank_score": (sim + 1.0) / 2.0
                })
            scored.sort(key=lambda x: x["hybrid_score"], reverse=True)
            top_evidence = scored[:5]

            llm_result = LLMService.generate_grounded_answer(
                question=question,
                retrieved_clauses=top_evidence,
                analysis={"topic": "general", "intent": "general_qa"},
                conversation_context=conv_context,
                is_insufficient=(len(top_evidence) == 0)
            )

            latency = round(time.time() - start_time, 3)
            pipeline_type = "Baseline_Conventional_RAG"
            completeness_score = 0.50
            retrieved_categories = list(set(c["category"] for c in top_evidence))
            topic = "general"

        else:
            # ---------------------------------------------------------------------
            # PROPOSED POLICY_LENS ADVANCED RAG PIPELINE
            # ---------------------------------------------------------------------
            logger.info(f"Executing PROPOSED PolicyLens RAG for document {document_id}...")
            # 1. Question Understanding & Intent Analysis
            analysis = QuestionAnalyzer.analyze(question)
            topic = analysis.get("topic", "general")

            # 2. Hybrid Retrieval (Dense BGE-M3 + BM25 Sparse + Category Boost)
            candidates = HybridRetriever.retrieve(
                db=db,
                document_id=document_id,
                query=question,
                analysis=analysis,
                top_k=15
            )

            # 3. Cross-Encoder Reranking
            reranked = CrossEncoderReranker.rerank(
                query=question,
                candidate_clauses=candidates,
                top_k=10
            )

            # 4. Completeness Verification and Category Expansion
            final_evidence, completeness_score, missing_cats, is_insufficient = CompletenessChecker.verify_and_expand(
                db=db,
                document_id=document_id,
                retrieved_clauses=reranked,
                analysis=analysis
            )

            # 5. Grounded LLM Generation
            llm_result = LLMService.generate_grounded_answer(
                question=question,
                retrieved_clauses=final_evidence,
                analysis=analysis,
                conversation_context=conv_context,
                is_insufficient=is_insufficient
            )

            latency = round(time.time() - start_time, 3)
            pipeline_type = "PolicyLens_Hybrid_RAG"
            retrieved_categories = list(set(c["category"] for c in final_evidence if c.get("category")))

        # Record Assistant Response in Chat DB
        bot_msg = ChatMessage(
            conversation_id=conv.id,
            document_id=document_id,
            role="assistant",
            content=llm_result["answer"],
            topic=topic,
            status=llm_result["status"],
            sources_json=json.dumps(llm_result["citations"])
        )
        db.add(bot_msg)
        db.commit()

        return {
            "answer": llm_result["answer"],
            "conversation_id": conv.id,
            "topic": topic,
            "status": llm_result["status"],
            "sources": llm_result["citations"],
            "completeness_score": completeness_score,
            "retrieved_categories": retrieved_categories,
            "pipeline_type": pipeline_type,
            "latency_seconds": latency
        }
