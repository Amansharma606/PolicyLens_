import re
from typing import Dict, Any, Tuple
from app.core.logging import logger

class ClauseClassifier:
    """
    Health Insurance Policy Clause Classifier.
    Categorizes clauses into 5 primary policy dimensions:
    - Coverage: Treatments, hospitalization, surgeries, day-care procedures, room rent
    - Exclusion: Uncovered expenses, permanent exclusions, cosmetic, intentional self-harm
    - Waiting Period: Initial 30-day, pre-existing disease (PED), maternity wait times (e.g. 24/36/48 months)
    - Condition: Policy renewal, cancellation, disclosures, geographical limits, sub-limits
    - Claim Requirement: Intimation timelines, required bills, discharge summaries, cashless network procedures
    """

    CATEGORIES = [
        "Coverage",
        "Exclusion",
        "Waiting Period",
        "Condition",
        "Claim Requirement",
        "General"
    ]

    WAITING_PERIOD_PATTERNS = [
        re.compile(r"\bwaiting\s+period\b", re.IGNORECASE),
        re.compile(r"\b(?:30|60|90)\s*days?\s+waiting\b", re.IGNORECASE),
        re.compile(r"\b(?:12|24|36|48)\s*months?\s+waiting\b", re.IGNORECASE),
        re.compile(r"\bpre-existing\s+disease(?:s)?\s+(?:waiting|wait|exclusion)\b", re.IGNORECASE),
        re.compile(r"\bfirst\s+thirty\s+days\b", re.IGNORECASE),
        re.compile(r"\bmaternity\s+waiting\s+period\b", re.IGNORECASE),
        re.compile(r"\bspecific\s+(?:illness|disease|treatment)\s+waiting\s+period\b", re.IGNORECASE),
    ]

    EXCLUSION_PATTERNS = [
        re.compile(r"\b(?:strictly\s+excluded|shall\s+not\s+be\s+liable|not\s+covered|permanently\s+excluded|exclusions?)\b", re.IGNORECASE),
        re.compile(r"\bpermanent\s+exclusions?\b", re.IGNORECASE),
        re.compile(r"\bnon-payable\s+items?\b", re.IGNORECASE),
        re.compile(r"\bcosmetic\s+(?:surgery|treatment)\b", re.IGNORECASE),
        re.compile(r"\bintentional\s+self-inflicted\s+injury\b", re.IGNORECASE),
        re.compile(r"\bwar,\s+invasion|nuclear\b", re.IGNORECASE),
        re.compile(r"\bunproven\s+or\s+experimental\s+treatments?\b", re.IGNORECASE),
        re.compile(r"\bweight\s+loss|bariatric|dental|optometry\b", re.IGNORECASE),
        re.compile(r"\bno\s+benefit\s+shall\s+be\s+payable\b", re.IGNORECASE),
    ]

    CLAIM_PATTERNS = [
        re.compile(r"\bclaim\s+(?:procedure|process|submission|settlement|intimation)\b", re.IGNORECASE),
        re.compile(r"\bdocuments?\s+required\s+(?:for|to)\s+claim\b", re.IGNORECASE),
        re.compile(r"\bdischarge\s+summary|original\s+bills?|prescriptions?|diagnostic\s+reports?\b", re.IGNORECASE),
        re.compile(r"\bcashless\s+facility|network\s+hospital(?:s)?\b", re.IGNORECASE),
        re.compile(r"\breimbursement\s+claim\b", re.IGNORECASE),
        re.compile(r"\bintimation\s+within\s+\d+\s+(?:hours|days)\b", re.IGNORECASE),
        re.compile(r"\btpa|third\s+party\s+administrator\b", re.IGNORECASE),
    ]

    COVERAGE_PATTERNS = [
        re.compile(r"\b(?:in-patient|hospitalization|day\s+care|pre-hospitalization|post-hospitalization)\s+expenses?\b", re.IGNORECASE),
        re.compile(r"\bcovered\s+(?:expenses?|treatments?|benefits?)\b", re.IGNORECASE),
        re.compile(r"\bicu\s+charges|room\s+rent|nursing\s+expenses?\b", re.IGNORECASE),
        re.compile(r"\bsum\s+insured|cumulative\s+bonus|restore\s+benefit|road\s+ambulance\b", re.IGNORECASE),
        re.compile(r"\bmedical\s+practitioner\s+fees|surgeon|anesthetist\b", re.IGNORECASE),
        re.compile(r"\bdomiciliary\s+hospitalization\b", re.IGNORECASE),
        re.compile(r"\bayush\s+treatment\b", re.IGNORECASE),
    ]

    CONDITION_PATTERNS = [
        re.compile(r"\b(?:terms\s+and\s+conditions?|general\s+conditions?)\b", re.IGNORECASE),
        re.compile(r"\brenewal|cancellation|grace\s+period|free\s+look\s+period\b", re.IGNORECASE),
        re.compile(r"\bdisclosure\s+of\s+information|material\s+facts?|fraud\b", re.IGNORECASE),
        re.compile(r"\bco-payment|deductible|sub-limit(?:s)?\b", re.IGNORECASE),
        re.compile(r"\bgeographical\s+limits?|jurisdiction\b", re.IGNORECASE),
        re.compile(r"\barbitration|grievance\s+redressal|ombudsman\b", re.IGNORECASE),
    ]

    @classmethod
    def classify(cls, text: str, section_name: str = "") -> Tuple[str, float]:
        text_lower = text.lower()
        sec_lower = section_name.lower()

        scores = {
            "Waiting Period": 0.0,
            "Exclusion": 0.0,
            "Claim Requirement": 0.0,
            "Coverage": 0.0,
            "Condition": 0.0,
        }

        # 1. Strong clause text pattern matches (weight: 0.50 per hit)
        for p in cls.EXCLUSION_PATTERNS:
            if p.search(text_lower):
                scores["Exclusion"] += 0.50

        for p in cls.WAITING_PERIOD_PATTERNS:
            if p.search(text_lower):
                scores["Waiting Period"] += 0.45

        for p in cls.CLAIM_PATTERNS:
            if p.search(text_lower):
                scores["Claim Requirement"] += 0.45

        for p in cls.COVERAGE_PATTERNS:
            if p.search(text_lower):
                scores["Coverage"] += 0.40

        for p in cls.CONDITION_PATTERNS:
            if p.search(text_lower):
                scores["Condition"] += 0.35

        # 2. Section context bonus (weight: 0.20)
        if "exclusion" in sec_lower:
            scores["Exclusion"] += 0.25
        elif "waiting" in sec_lower:
            scores["Waiting Period"] += 0.25
        elif "claim" in sec_lower:
            scores["Claim Requirement"] += 0.25
        elif "benefit" in sec_lower or "coverage" in sec_lower:
            scores["Coverage"] += 0.20
        elif "condition" in sec_lower:
            scores["Condition"] += 0.20

        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]

        if best_score < 0.20:
            return "General", 0.50

        confidence = min(0.98, max(0.55, round(0.50 + (best_score * 0.4), 2)))
        return best_category, confidence

    @classmethod
    def train_on_dataset(cls, dataset_path: str):
        logger.info(f"ClauseClassifier fine-tuning pipeline prepared for dataset at {dataset_path}.")
        raise NotImplementedError("No annotated dataset found in repository. Using calibrated baseline domain classifier.")
