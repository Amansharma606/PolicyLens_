import sys
import json
from pathlib import Path

# Add backend directory to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db.database import SessionLocal, init_db
from app.models.db_models import Document
from evaluation.eval_framework import EvaluationFramework

def main():
    print("=" * 70)
    print("PolicyLens Comparative Research Evaluation Runner")
    print("Baseline RAG vs. Proposed PolicyLens Hybrid RAG")
    print("=" * 70)

    init_db()
    db = SessionLocal()

    # Find the most recently uploaded policy document
    doc = db.query(Document).filter(Document.status == "ready").order_by(Document.upload_date.desc()).first()
    if not doc:
        print("\n[!] No indexed policy document found in database.")
        print("Please upload a health insurance policy PDF through the application first, or run sample generation.")
        db.close()
        return

    print(f"\nEvaluating on active policy: '{doc.filename}' (ID: {doc.id}, Pages: {doc.total_pages})")

    # 1. Run Baseline RAG
    print("\n[1/2] Running Baseline Conventional RAG Pipeline...")
    baseline_eval = EvaluationFramework.evaluate_pipeline(db, doc.id, use_baseline=True)

    # 2. Run Proposed PolicyLens
    print("\n[2/2] Running Proposed PolicyLens Hybrid RAG Pipeline...")
    proposed_eval = EvaluationFramework.evaluate_pipeline(db, doc.id, use_baseline=False)

    # Format comparative output
    b_metrics = baseline_eval["aggregate_metrics"]
    p_metrics = proposed_eval["aggregate_metrics"]

    print("\n" + "=" * 70)
    print(f"{'METRIC':<30} | {'BASELINE RAG':<16} | {'PROPOSED POLICY_LENS':<20}")
    print("-" * 70)
    print(f"{'Fact Completeness':<30} | {b_metrics['fact_completeness'] * 100:>14.1f}% | {p_metrics['fact_completeness'] * 100:>18.1f}%")
    print(f"{'Evidence Accuracy':<30} | {b_metrics['evidence_accuracy'] * 100:>14.1f}% | {p_metrics['evidence_accuracy'] * 100:>18.1f}%")
    print(f"{'Retrieval Recall@K':<30} | {b_metrics['retrieval_recall_at_k'] * 100:>14.1f}% | {p_metrics['retrieval_recall_at_k'] * 100:>18.1f}%")
    print(f"{'Faithfulness Score':<30} | {b_metrics['faithfulness'] * 100:>14.1f}% | {p_metrics['faithfulness'] * 100:>18.1f}%")
    print(f"{'Average Latency':<30} | {b_metrics['avg_latency_sec']:>13.3f}s | {p_metrics['avg_latency_sec']:>17.3f}s")
    print("=" * 70)

    output_path = BASE_DIR / "evaluation" / "evaluation_results.json"
    with open(output_path, "w") as f:
        json.dump({"baseline": baseline_eval, "proposed": proposed_eval}, f, indent=2)

    print(f"\nFull detailed comparative results saved to: {output_path}")
    db.close()

if __name__ == "__main__":
    main()
