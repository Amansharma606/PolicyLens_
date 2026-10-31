from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.models.db_models import DocumentClause
from app.core.logging import logger

class CompletenessChecker:
    """
    Validates whether the retrieved evidence covers all required policy dimensions
    (Coverage, Waiting Period, Exclusion, Condition, Claim Requirement).
    Executes secondary category-targeted retrieval when critical evidence is missing,
    and enforces strict insufficiency checking for unmentioned conditions or diseases.
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
        # 1. First check if user queried a specific entity/disease not mentioned in the policy
        specific_entity = analysis.get("specific_entity", "")
        is_unrecognized = analysis.get("is_unrecognized_specific", False)

        if is_unrecognized or specific_entity:
            entity_words = [w.lower() for w in specific_entity.split() if len(w) > 2]
            if entity_words:
                # Query whether ANY clause in this document contains these entity words
                has_entity_in_doc = False
                for ew in entity_words:
                    cnt = db.query(DocumentClause).filter(
                        DocumentClause.document_id == document_id,
                        DocumentClause.clean_text.ilike(f"%{ew}%")
                    ).count()
                    if cnt > 0:
                        has_entity_in_doc = True
                        break

                if not has_entity_in_doc:
                    logger.info(f"Specific queried entity '{specific_entity}' is not found anywhere in document {document_id}. Flagging as insufficient evidence.")
                    return [], 0.0, [], True

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
                query = db.query(DocumentClause).filter(
                    DocumentClause.document_id == document_id,
                    DocumentClause.category == missing_cat
                )

                if topic and topic != "general_health_policy":
                    keywords = [topic.replace("_", " ")]
                    if topic == "maternity":
                        keywords.extend(["pregnancy", "childbirth", "delivery", "newborn", "cesarean"])
                    elif topic == "pre_existing_disease":
                        keywords.extend(["pre-existing", "ped", "chronic", "diabetes", "hypertension"])
                    elif topic == "cataract":
                        keywords.extend(["eye", "lens", "cataract"])
                    elif topic == "room_rent":
                        keywords.extend(["room rent", "icu", "capping", "deduction"])
                    elif topic == "claim_procedure":
                        keywords.extend(["cashless", "reimbursement", "intimation", "tpa", "bill"])

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

        is_insufficient = False
        if not expanded_clauses:
            is_insufficient = True
        else:
            top_score = max((c.get("rerank_score", c.get("hybrid_score", 0.0)) for c in expanded_clauses), default=0.0)
            topic_raw = analysis.get("topic", "")
            if top_score < 0.15 and topic_raw != "general_health_policy":
                topic_words = set(topic_raw.lower().split("_"))
                has_topic_match = any(
                    any(w in c["text"].lower() for w in topic_words)
                    for c in expanded_clauses
                )
                if not has_topic_match:
                    is_insufficient = True

        return expanded_clauses, completeness_score, final_missing, is_insufficient
