from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.models.db_models import DocumentClause
from app.core.logging import logger

class CompletenessChecker:
    """
    Validates whether the retrieved evidence covers all required policy categories
    (Coverage, Waiting Period, Exclusion, Condition, Claim Requirement).
    Executes secondary category-targeted retrieval when critical evidence is missing.
    """

    @classmethod
    def verify_and_expand(
        cls,
        db: Session,
        document_id: str,
        retrieved_clauses: List[Dict[str, Any]],
        analysis: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], float, List[str], bool]:
        """
        Returns: (expanded_clauses, completeness_score, missing_categories, is_insufficient)
        """
        required_categories = analysis.get("required_categories", [])
        if not required_categories:
            return retrieved_clauses, 1.0, [], len(retrieved_clauses) == 0

        # Check which categories are represented in current retrieved clauses
        retrieved_categories = set(c.get("category") for c in retrieved_clauses if c.get("category"))
        missing_categories = [cat for cat in required_categories if cat not in retrieved_categories]

        expanded_clauses = list(retrieved_clauses)
        existing_ids = set(c["id"] for c in expanded_clauses)

        # If important categories are missing, perform secondary targeted query
        if missing_categories:
            topic = analysis.get("topic", "")
            for missing_cat in missing_categories:
                # Target clauses in this category for this specific document
                query = db.query(DocumentClause).filter(
                    DocumentClause.document_id == document_id,
                    DocumentClause.category == missing_cat
                )
                
                # If topic exists, search for topic keywords in that category
                if topic and topic != "general_health_policy":
                    keywords = [topic.replace("_", " ")]
                    if topic == "maternity":
                        keywords.extend(["pregnancy", "childbirth", "delivery", "newborn"])
                    elif topic == "pre_existing_disease":
                        keywords.extend(["pre-existing", "ped", "chronic"])
                    elif topic == "cataract":
                        keywords.extend(["eye", "lens"])
                    
                    found_target = []
                    for kw in keywords:
                        hits = query.filter(DocumentClause.clean_text.ilike(f"%{kw}%")).limit(2).all()
                        found_target.extend(hits)
                    candidates = found_target
                else:
                    candidates = query.limit(2).all()

                for c in candidates:
                    if c.id not in existing_ids:
                        expanded_clauses.append({
                            "id": c.id,
                            "document_id": c.document_id,
                            "page": c.page_number,
                            "section": c.section_name or "Policy Clause",
                            "clause_number": c.clause_number,
                            "category": c.category,
                            "confidence": c.classification_confidence or 0.85,
                            "text": c.original_text,
                            "clean_text": c.clean_text,
                            "hybrid_score": 0.65,
                            "rerank_score": 0.65,
                            "supplemental": True
                        })
                        existing_ids.add(c.id)

        # Recalculate completeness
        updated_categories = set(c.get("category") for c in expanded_clauses if c.get("category"))
        final_missing = [cat for cat in required_categories if cat not in updated_categories]
        total_req = len(required_categories)
        covered_req = total_req - len(final_missing)
        completeness_score = round(covered_req / total_req, 2) if total_req > 0 else 1.0

        # Check if insufficient evidence:
        # If top scores are very low or 0 clauses retrieved, flag as insufficient
        is_insufficient = False
        if not expanded_clauses:
            is_insufficient = True
        else:
            top_score = max((c.get("hybrid_score", 0.0) for c in expanded_clauses), default=0.0)
            if top_score < 0.12 and not any(analysis.get("topic", "") in c["text"].lower() for c in expanded_clauses):
                is_insufficient = True

        return expanded_clauses, completeness_score, final_missing, is_insufficient
