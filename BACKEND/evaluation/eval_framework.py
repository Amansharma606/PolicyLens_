import time
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.services.rag_engine import RAGEngine

EVAL_BENCHMARK = [
    {
        "id": "q1_maternity_coverage",
        "question": "Is maternity covered?",
        "topic": "maternity",
        "expected_category": "Coverage",
        "ground_truth_facets": ["covered", "waiting period", "exclusion", "conditions"],
        "must_cite_pages": [1, 2, 3]  # Document dependent
    },
    {
        "id": "q2_maternity_waiting_period",
        "question": "What is the waiting period for maternity?",
        "topic": "maternity",
        "expected_category": "Waiting Period",
        "ground_truth_facets": ["waiting period", "months"],
        "must_cite_pages": [1, 2, 3]
    },
    {
        "id": "q3_maternity_exclusions",
        "question": "List all exclusions related to maternity.",
        "topic": "maternity",
        "expected_category": "Exclusion",
        "ground_truth_facets": ["exclusion", "not covered", "surrogacy", "infertility"],
        "must_cite_pages": [2, 3, 4]
    },
    {
        "id": "q4_claim_documents",
        "question": "What documents are required to file a reimbursement claim?",
        "topic": "claim_procedure",
        "expected_category": "Claim Requirement",
        "ground_truth_facets": ["bills", "discharge summary", "prescriptions"],
        "must_cite_pages": [2, 3, 4]
    },
    {
        "id": "q5_unmentioned_condition",
        "question": "Does this policy cover space tourism medical evacuation?",
        "topic": "unmentioned_condition",
        "expected_category": "General",
        "ground_truth_facets": ["insufficient evidence", "not mentioned", "not found"],
        "must_cite_pages": []
    }
]

class EvaluationFramework:
    """
    Empirical research evaluation framework comparing:
    - Baseline RAG (Fixed Dense Retrieval Top-K)
    - Proposed PolicyLens (Structure-aware + Classification + Hybrid + Reranking + Completeness)
    """

    @classmethod
    def evaluate_pipeline(
        cls,
        db: Session,
        document_id: str,
        use_baseline: bool = False
    ) -> Dict[str, Any]:
        results = []
        total_latency = 0.0

        for item in EVAL_BENCHMARK:
            q = item["question"]
            start_t = time.time()
            ans_data = RAGEngine.answer_question(
                db=db,
                document_id=document_id,
                question=q,
                use_baseline=use_baseline
            )
            elapsed = time.time() - start_t
            total_latency += elapsed

            answer_text = ans_data["answer"].lower()
            sources = ans_data.get("sources", [])

            # 1. Fact Completeness: fraction of ground truth facets mentioned
            facets = item["ground_truth_facets"]
            matched_facets = sum(1 for f in facets if f in answer_text)
            completeness = matched_facets / len(facets) if facets else 1.0

            # 2. Evidence Accuracy: Valid source citations with text
            has_sources = len(sources) > 0
            evidence_accuracy = 1.0 if (has_sources or item["id"] == "q5_unmentioned_condition") else 0.0

            # 3. Retrieval Recall@K: Did it retrieve the expected category?
            retrieved_cats = ans_data.get("retrieved_categories", [])
            expected_cat = item["expected_category"]
            recall_k = 1.0 if (expected_cat in retrieved_cats or expected_cat == "General") else 0.0

            # 4. Faithfulness: Answers say "insufficient evidence" when facts are not in document
            if item["id"] == "q5_unmentioned_condition":
                faithfulness = 1.0 if ans_data["status"] == "insufficient_evidence" or "insufficient" in answer_text else 0.2
            else:
                faithfulness = 1.0 if has_sources and ans_data["status"] == "answered" else 0.5

            results.append({
                "test_id": item["id"],
                "question": q,
                "latency_sec": round(elapsed, 3),
                "completeness": round(completeness, 2),
                "evidence_accuracy": round(evidence_accuracy, 2),
                "recall_at_k": round(recall_k, 2),
                "faithfulness": round(faithfulness, 2),
                "sources_count": len(sources),
                "status": ans_data["status"]
            })

        avg_latency = round(total_latency / len(EVAL_BENCHMARK), 3)
        avg_completeness = round(sum(r["completeness"] for r in results) / len(results), 2)
        avg_evidence_acc = round(sum(r["evidence_accuracy"] for r in results) / len(results), 2)
        avg_recall_k = round(sum(r["recall_at_k"] for r in results) / len(results), 2)
        avg_faithfulness = round(sum(r["faithfulness"] for r in results) / len(results), 2)

        return {
            "pipeline": "Baseline_Conventional_RAG" if use_baseline else "PolicyLens_Hybrid_RAG",
            "aggregate_metrics": {
                "avg_latency_sec": avg_latency,
                "fact_completeness": avg_completeness,
                "evidence_accuracy": avg_evidence_acc,
                "retrieval_recall_at_k": avg_recall_k,
                "faithfulness": avg_faithfulness
            },
            "detailed_results": results
        }
