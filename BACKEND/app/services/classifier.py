import re
from typing import Dict, Any, Tuple
from app.core.logging import logger

class ClauseClassifier:
    """
    Health Insurance Policy Clause Classifier.
    Categorizes clauses into 5 primary policy dimensions:
    - Coverage: Treatments, hospitalization, day-care procedures, room rent, AYUSH, restoration
    - Exclusion: Uncovered expenses, permanent exclusions, cosmetic, intentional injury
    - Waiting Period: Initial 30-day, pre-existing disease (PED 24/36/48 mo), specific diseases (cataract, hernia), maternity wait
    - Condition: Policy renewal, cancellation, disclosures, room rent caps, sub-limits, co-payments
    - Claim Requirement: Intimation timelines, required bills, discharge summaries, cashless network/TPA procedures
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
        re.compile(r"\b(?:30|60|90)\s*days?\s+(?:waiting|wait|exclusion)\b", re.IGNORECASE),
        re.compile(r"\b(?:12|24|36|48)\s*months?\s+(?:waiting|wait|exclusion|continuous)\b", re.IGNORECASE),
        re.compile(r"\bpre-existing\s+disease(?:s)?\s+(?:waiting|wait|exclusion|covered\s+after)\b", re.IGNORECASE),
        re.compile(r"\bfirst\s+thirty\s+days\b", re.IGNORECASE),
        re.compile(r"\bmaternity\s+waiting\s+period\b", re.IGNORECASE),
        re.compile(r"\bspecific\s+(?:illness|disease|treatment)\s+(?:waiting|wait)\b", re.IGNORECASE),
        re.compile(r"\bpayable\s+only\s+after\s+\d+\s+(?:months|years|days)\b", re.IGNORECASE),
    ]

    EXCLUSION_PATTERNS = [
        re.compile(r"\b(?:strictly\s+excluded|shall\s+not\s+be\s+liable|not\s+covered|permanently\s+excluded|exclusions?)\b", re.IGNORECASE),
        re.compile(r"\bpermanent\s+exclusions?\b", re.IGNORECASE),
        re.compile(r"\bnon-payable\s+items?\b", re.IGNORECASE),
        re.compile(r"\bcosmetic\s+(?:surgery|treatment)\b", re.IGNORECASE),
        re.compile(r"\bintentional\s+self-inflicted\s+injury|suicide\b", re.IGNORECASE),
        re.compile(r"\bwar,\s+invasion|nuclear|hazardous\b", re.IGNORECASE),
        re.compile(r"\bunproven\s+or\s+experimental\s+treatments?\b", re.IGNORECASE),
        re.compile(r"\bweight\s+loss|bariatric|dental\s+treatment|optometry\b", re.IGNORECASE),
        re.compile(r"\bno\s+benefit\s+shall\s+be\s+payable\b", re.IGNORECASE),
        re.compile(r"\bshall\s+not\s+cover\b", re.IGNORECASE),
    ]

    CLAIM_PATTERNS = [
        re.compile(r"\bclaim\s+(?:procedure|process|submission|settlement|intimation)\b", re.IGNORECASE),
        re.compile(r"\bdocuments?\s+required\s+(?:for|to)\s+claim\b", re.IGNORECASE),
        re.compile(r"\bdischarge\s+summary|original\s+bills?|prescriptions?|diagnostic\s+reports?\b", re.IGNORECASE),
        re.compile(r"\bcashless\s+facility|network\s+hospital(?:s)?|pre-authorization\b", re.IGNORECASE),
        re.compile(r"\breimbursement\s+claim\b", re.IGNORECASE),
        re.compile(r"\bintimation\s+within\s+\d+\s+(?:hours|days)\b", re.IGNORECASE),
        re.compile(r"\btpa|third\s+party\s+administrator\b", re.IGNORECASE),
        re.compile(r"\bsubmit\s+claims?\s+within\s+\d+\s+days\b", re.IGNORECASE),
    ]

    COVERAGE_PATTERNS = [
        re.compile(r"\b(?:in-patient|hospitalization|day\s+care|pre-hospitalization|post-hospitalization)\s+expenses?\b", re.IGNORECASE),
        re.compile(r"\bcovered\s+(?:expenses?|treatments?|benefits?)\b", re.IGNORECASE),
        re.compile(r"\bicu\s+charges|room\s+rent|nursing\s+expenses?\b", re.IGNORECASE),
        re.compile(r"\bsum\s+insured|cumulative\s+bonus|restore\s+benefit|restoration|road\s+ambulance\b", re.IGNORECASE),
        re.compile(r"\bmedical\s+practitioner\s+fees|surgeon|anesthetist|consultation\b", re.IGNORECASE),
        re.compile(r"\bdomiciliary\s+hospitalization\b", re.IGNORECASE),
        re.compile(r"\bayush\s+treatment\b", re.IGNORECASE),
        re.compile(r"\borgan\s+donor\s+expenses?\b", re.IGNORECASE),
    ]

    CONDITION_PATTERNS = [
        re.compile(r"\b(?:terms\s+and\s+conditions?|general\s+conditions?)\b", re.IGNORECASE),
        re.compile(r"\brenewal|cancellation|grace\s+period|free\s+look\s+period\b", re.IGNORECASE),
        re.compile(r"\bdisclosure\s+of\s+information|material\s+facts?|fraud\b", re.IGNORECASE),
        re.compile(r"\bco-payment|deductible|sub-limit(?:s)?|room\s+rent\s+limit\b", re.IGNORECASE),
        re.compile(r"\bgeographical\s+limits?|jurisdiction\b", re.IGNORECASE),
        re.compile(r"\barbitration|grievance\s+redressal|ombudsman\b", re.IGNORECASE),
        re.compile(r"\bproportionate\s+deduction\b", re.IGNORECASE),
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

        # 1. Text Pattern matching
        for p in cls.EXCLUSION_PATTERNS:
            if p.search(text_lower):
                scores["Exclusion"] += 0.50

        for p in cls.WAITING_PERIOD_PATTERNS:
            if p.search(text_lower):
                scores["Waiting Period"] += 0.50

        for p in cls.CLAIM_PATTERNS:
            if p.search(text_lower):
                scores["Claim Requirement"] += 0.50

        for p in cls.COVERAGE_PATTERNS:
            if p.search(text_lower):
                scores["Coverage"] += 0.40

        for p in cls.CONDITION_PATTERNS:
            if p.search(text_lower):
                scores["Condition"] += 0.35

        # 2. Section context bonus
        if "exclusion" in sec_lower:
            scores["Exclusion"] += 0.35
        elif "waiting" in sec_lower:
            scores["Waiting Period"] += 0.35
        elif "claim" in sec_lower:
            scores["Claim Requirement"] += 0.35
        elif "benefit" in sec_lower or "coverage" in sec_lower:
            scores["Coverage"] += 0.30
        elif "condition" in sec_lower or "limit" in sec_lower:
            scores["Condition"] += 0.25

        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]

        if best_score < 0.25:
            return "General", 0.50

        confidence = min(0.98, max(0.55, round(0.50 + (best_score * 0.35), 2)))
        return best_category, confidence
