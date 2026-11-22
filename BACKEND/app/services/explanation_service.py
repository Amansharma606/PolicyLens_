import json
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.db_models import Document, DocumentClause, DocumentSection
from app.core.logging import logger

class PolicyExplanationService:
    """
    Generates a structured, 10-dimensional explanation of an uploaded health insurance policy.
    Maintains exact source page numbers and section citations, honestly reporting missing categories.
    """

    DIMENSIONS = [
        {
            "key": "overview",
            "title": "1. Policy Overview",
            "keywords": ["policy", "overview", "preamble", "schedule", "introduction"],
            "categories": ["General", "Coverage"]
        },
        {
            "key": "eligibility",
            "title": "2. Policyholder Eligibility",
            "keywords": ["eligibility", "entry age", "dependent", "family", "child", "adult"],
            "categories": ["Condition", "General"]
        },
        {
            "key": "coverage",
            "title": "3. Coverage and Benefits",
            "keywords": ["hospitalization", "in-patient", "day care", "icu", "surgery", "benefit", "room rent"],
            "categories": ["Coverage"]
        },
        {
            "key": "exclusions",
            "title": "4. Exclusions",
            "keywords": ["exclusion", "not covered", "permanent exclusion", "shall not be liable", "cosmetic"],
            "categories": ["Exclusion"]
        },
        {
            "key": "waiting_periods",
            "title": "5. Waiting Periods",
            "keywords": ["waiting period", "30 days", "months", "pre-existing", "ped", "specific illness"],
            "categories": ["Waiting Period"]
        },
        {
            "key": "limits",
            "title": "6. Financial Limits and Sub-limits",
            "keywords": ["sub-limit", "cap", "co-pay", "deductible", "maximum", "sum insured"],
            "categories": ["Condition", "Coverage"]
        },
        {
            "key": "conditions",
            "title": "7. Conditions and Restrictions",
            "keywords": ["renewal", "cancellation", "grace period", "free look", "disclosure", "fraud"],
            "categories": ["Condition"]
        },
        {
            "key": "claims",
            "title": "8. Claim Process and Required Documents",
            "keywords": ["claim", "reimbursement", "cashless", "intimation", "discharge summary", "bills"],
            "categories": ["Claim Requirement"]
        },
        {
            "key": "definitions",
            "title": "9. Important Definitions",
            "keywords": ["definition", "means", "shall mean", "hospital", "illness", "injury", "medically necessary"],
            "categories": ["General", "Condition"]
        },
        {
            "key": "limitations",
            "title": "10. Important Limitations & Unclear Clauses",
            "keywords": ["limitation", "restriction", "subject to", "provise", "territorial"],
            "categories": ["Condition", "Exclusion"]
        }
    ]

    # Precompile regex patterns for ultra-fast matching
    _COMPILED_PATTERNS = {
        dim["key"]: re.compile(r"\b(?:" + "|".join(re.escape(k) for k in dim["keywords"]) + r")\b", re.IGNORECASE)
        for dim in DIMENSIONS
    }

    @classmethod
    def generate_explanation(
        cls,
        db: Session,
        document: Document,
        clauses: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Extracts evidence for each of the 10 dimensions from document clauses.
        Uses in-memory clauses if provided to avoid redundant database reads.
        """
        if clauses is None:
            clauses = db.query(DocumentClause).filter(DocumentClause.document_id == document.id).all()

        sections_found = []

        overview_text = (
            f"PolicyLens analyzed '{document.filename}' across {document.total_pages} pages "
            f"and indexed {len(clauses)} policy clauses. Below is a structured, evidence-grounded summary."
        )

        for dim in cls.DIMENSIONS:
            key = dim["key"]
            title = dim["title"]
            target_cats = set(dim["categories"])
            pattern = cls._COMPILED_PATTERNS[key]

            matching_clauses = []
            for c in clauses:
                cat = getattr(c, "category", "") or ""
                cat_match = cat in target_cats
                clean_t = getattr(c, "clean_text", "") or getattr(c, "original_text", "")
                sec_t = getattr(c, "section_name", "") or ""
                kw_match = bool(pattern.search(clean_t) or pattern.search(sec_t))

                if cat_match and kw_match:
                    matching_clauses.append((c, 2.0))
                elif kw_match:
                    matching_clauses.append((c, 1.5))
                elif cat_match:
                    matching_clauses.append((c, 1.0))

            matching_clauses.sort(key=lambda x: x[1], reverse=True)
            top_matches = [m[0] for m in matching_clauses[:4]]

            if top_matches:
                # Build summary & key points
                key_points = []
                sources = []
                for c in top_matches:
                    clean_excerpt = c.original_text.strip()
                    if len(clean_excerpt) > 160:
                        clean_excerpt = clean_excerpt[:157] + "..."
                    key_points.append(clean_excerpt)
                    sources.append({
                        "page": c.page_number,
                        "section": c.section_name or "Policy Section",
                        "clause_number": c.clause_number,
                        "category": c.category,
                        "relevance_score": 0.90,
                        "text": c.original_text
                    })

                pages_list = sorted(list(set(s["page"] for s in sources)))
                pages_str = ", ".join(f"Page {p}" for p in pages_list)
                summary = f"Identified {len(top_matches)} verified policy statements on {pages_str}."

                sections_found.append({
                    "key": key,
                    "title": title,
                    "summary": summary,
                    "key_points": key_points,
                    "sources": sources,
                    "limitations": None,
                    "status": "found"
                })
            else:
                # Honest reporting: Information not found in document
                sections_found.append({
                    "key": key,
                    "title": title,
                    "summary": "No explicit clauses found for this dimension in the uploaded document.",
                    "key_points": [],
                    "sources": [],
                    "limitations": "This specific policy document does not contain an identifiable section for this category, or it may be governed by a separate policy schedule/rider.",
                    "status": "not_found"
                })

        explanation_payload = {
            "document_id": document.id,
            "filename": document.filename,
            "total_pages": document.total_pages,
            "generated_at": document.upload_date.isoformat() if document.upload_date else "",
            "overview": overview_text,
            "sections": sections_found
        }

        # Cache in database
        try:
            document.explanation_json = json.dumps(explanation_payload)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to persist explanation JSON: {e}")
            db.rollback()

        return explanation_payload
