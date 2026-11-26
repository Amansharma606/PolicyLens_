import re
import threading
from typing import Dict, Any, Tuple, List, Optional
import numpy as np
from app.services.embeddings import EmbeddingService
from app.core.logging import logger


class ClauseClassifier:
    """
    Domain-Agnostic Insurance Policy Clause Classifier & 10-Dimension Mapper.
    Combines dense semantic prototype similarity (via BGE-M3 / MiniLM) with
    domain-generalized regex/structural safeguards across Health, Motor, Life/Term,
    Travel, Personal Accident, and Corporate/General insurance policies.
    """

    CATEGORIES = [
        "Coverage",
        "Exclusion",
        "Waiting Period",
        "Condition",
        "Claim Requirement",
        "General",
    ]

    # 10 Standardized Policy Explanation Dimensions (domain-agnostic)
    DIMENSIONS: List[Dict[str, Any]] = [
        {
            "key": "overview",
            "title": "1. Policy Overview",
            "prototype": (
                "Policy preamble, product name, insurer undertaking, scope of insurance contract, "
                "indemnity or fixed benefit basis, policy period, sum insured or sum assured options, "
                "policy tenure, installment options, and core key features summary."
            ),
            "categories": ["General", "Coverage"],
            "min_total_score": 0.48,
            "require_signal": False,
        },
        {
            "key": "eligibility",
            "title": "2. Policyholder Eligibility",
            "prototype": (
                "Who is eligible to buy or be covered under this insurance policy: minimum and maximum entry age "
                "for adults and dependent children, newborn coverage criteria, family floater member relationships, "
                "bank account participation rules, valid driving license eligibility, citizenship or residency criteria, "
                "and lifelong renewability eligibility."
            ),
            "categories": ["Condition", "General"],
            "min_total_score": 0.56,
            "require_signal": True,
        },
        {
            "key": "coverage",
            "title": "3. Coverage and Benefits",
            "prototype": (
                "Covered medical treatments, in-patient hospitalization, ICU, day care procedures, "
                "pre and post hospitalization, maternity delivery and newborn cover, modern treatments, "
                "ambulance, AYUSH, accidental death or permanent disability benefit, own damage, third party liability, "
                "trip cancellation, baggage loss, wellness program, and restoration of sum insured."
            ),
            "categories": ["Coverage"],
            "min_total_score": 0.50,
            "require_signal": True,
        },
        {
            "key": "exclusions",
            "title": "4. Exclusions",
            "prototype": (
                "Permanent exclusions and non-payable expenses strictly not covered by the insurer: "
                "cosmetic surgery, weight loss or bariatric exclusion, intentional self-injury or suicide, "
                "substance abuse, alcoholism, war or nuclear perils, unproven treatments, driving under influence, "
                "without valid license, rest cure, non-medical consumables, and excluded ailments."
            ),
            "categories": ["Exclusion"],
            "min_total_score": 0.52,
            "require_signal": True,
        },
        {
            "key": "waiting_periods",
            "title": "5. Waiting Periods",
            "prototype": (
                "Mandatory waiting period timelines before benefits apply: initial 30-day waiting period, "
                "specific disease or surgery 12-month or 24-month waiting period, pre-existing disease PED "
                "24-month 36-month or 48-month waiting period, maternity waiting period, survival period, "
                "or reduction and buy-back of waiting periods."
            ),
            "categories": ["Waiting Period"],
            "min_total_score": 0.55,
            "require_signal": True,
        },
        {
            "key": "limits",
            "title": "6. Financial Limits and Sub-limits",
            "prototype": (
                "Financial caps, sum insured slabs, room rent per day cap, ICU limit, disease-wise sub-limits "
                "for cataract delivery bariatric vaccination outpatient dental hospital cash, ambulance cap, "
                "co-payment percentage, compulsory or voluntary deductible, excess, proportionate deduction, "
                "no claim bonus NCB, cumulative bonus, and premium discounts."
            ),
            "categories": ["Condition", "Coverage"],
            "min_total_score": 0.53,
            "require_signal": True,
        },
        {
            "key": "conditions",
            "title": "7. Conditions and Restrictions",
            "prototype": (
                "General policy terms and conditions: policy renewal rules, grace period for premium payment, "
                "free look cancellation period, cancellation and refund terms, portability and migration rights, "
                "disclosure of material facts, fraud clause, termination of cover, moratorium period, "
                "geographical zone classification, and instalment payment terms."
            ),
            "categories": ["Condition"],
            "min_total_score": 0.52,
            "require_signal": True,
        },
        {
            "key": "claims",
            "title": "8. Claim Process and Required Documents",
            "prototype": (
                "How to file a cashless or reimbursement insurance claim, pre-authorization timeline 48 hours "
                "or 24 hours, claim intimation deadline within 15 or 30 days, TPA contact details, "
                "mandatory claim documents including claim form, discharge summary, itemized original bills, "
                "payment receipts, diagnostic reports, FIR, post mortem, disability or death certificate, "
                "and grievance redressal escalation."
            ),
            "categories": ["Claim Requirement"],
            "min_total_score": 0.52,
            "require_signal": True,
        },
        {
            "key": "definitions",
            "title": "9. Important Definitions",
            "prototype": (
                "Standard and specific policy definitions explaining key terms such as Accident, Illness, "
                "Hospital, Medical Practitioner, Medically Necessary Treatment, Pre-Existing Disease, "
                "Day Care Treatment, Grace Period, Cashless Facility, Sum Insured, IDV, Co-Payment, "
                "Cumulative Bonus, Congenital Anomaly, and Reasonable and Customary Charges."
            ),
            "categories": ["General", "Condition"],
            "min_total_score": 0.54,
            "require_signal": True,
        },
        {
            "key": "limitations",
            "title": "10. Important Limitations & Unclear Clauses",
            "prototype": (
                "Policy caveats, conditional provisos, proportionate deduction penalties, age-based co-pay restrictions, "
                "mandatory deductibles, specific disease exclusions during domiciliary or home care, "
                "schedule-dependent undisclosed limits where exact amounts refer to Policy Schedule, "
                "discretionary clauses, or pre-existing termination triggers."
            ),
            "categories": ["Condition", "Exclusion"],
            "min_total_score": 0.54,
            "require_signal": True,
        },
    ]

    # Broad domain-agnostic coarse classifier patterns
    WAITING_PERIOD_PATTERNS = [
        re.compile(r"\bwaiting\s+period(?:s)?\b", re.IGNORECASE),
        re.compile(r"\b(?:30|60|90)\s*days?\s+(?:initial\s+)?(?:waiting|wait|exclusion)\b", re.IGNORECASE),
        re.compile(r"\b(?:12|24|36|48)\s*months?\s+(?:continuous\s+)?(?:waiting|wait|coverage|exclusion)\b", re.IGNORECASE),
        re.compile(r"\bpre-existing\s+(?:disease|condition)(?:s)?\s+(?:waiting|wait|covered\s+after|shall\s+apply)\b", re.IGNORECASE),
        re.compile(r"\bfirst\s+(?:thirty|30)\s+days\b", re.IGNORECASE),
        re.compile(r"\bspecific\s+(?:illness|disease|treatment|waiting)\s+(?:waiting|period)\b", re.IGNORECASE),
        re.compile(r"\b(?:maternity|survival|elimination)\s+(?:waiting\s+)?period\b", re.IGNORECASE),
        re.compile(r"\bpayable\s+only\s+after\s+\d+\s+(?:months?|years?|days?)\b", re.IGNORECASE),
    ]

    EXCLUSION_PATTERNS = [
        re.compile(r"\b(?:strictly\s+excluded|permanently\s+excluded|shall\s+not\s+be\s+liable|not\s+covered|does\s+not\s+cover|shall\s+not\s+cover)\b", re.IGNORECASE),
        re.compile(r"\b(?:permanent|key|standard|general)\s+exclusions?\b|\bexcl\d+\b", re.IGNORECASE),
        re.compile(r"\bnon-payable\s+items?\b|\bnon-medical\s+(?:items?|expenses?)\b", re.IGNORECASE),
        re.compile(r"\bcosmetic\s+(?:or\s+plastic\s+)?(?:surgery|treatment)\b", re.IGNORECASE),
        re.compile(r"\b(?:intentional\s+self-?inflicted\s+injury|self-injury|suicide|attempt\s+to\s+suicide)\b", re.IGNORECASE),
        re.compile(r"\b(?:alcoholism|substance\s+abuse|drug\s+abuse|intoxication|under\s+the\s+influence)\b", re.IGNORECASE),
        re.compile(r"\b(?:war,?\s+invasion|nuclear\s+(?:weapon|radiation)|hazardous\s+(?:sports?|activities?))\b", re.IGNORECASE),
        re.compile(r"\bunproven\s+(?:or\s+experimental\s+)?treatments?\b|\brest\s+cure\b", re.IGNORECASE),
        re.compile(r"\bno\s+(?:benefit|claim)\s+shall\s+be\s+payable\b|\bnot\s+be\s+admissible\b", re.IGNORECASE),
        re.compile(r"\bwithout\s+(?:a\s+)?valid\s+driving\s+licen[cs]e\b", re.IGNORECASE),
    ]

    CLAIM_PATTERNS = [
        re.compile(r"\bclaim\s+(?:procedure|process|submission|settlement|intimation|notification|documents?)\b", re.IGNORECASE),
        re.compile(r"\bdocuments?\s+(?:to\s+be\s+submitted|required)\s+(?:for|to)\b", re.IGNORECASE),
        re.compile(r"\b(?:discharge\s+summary|original\s+bills?|payment\s+receipts?|prescriptions?|diagnostic\s+reports?)\b", re.IGNORECASE),
        re.compile(r"\b(?:cashless\s+facility|network\s+hospital(?:s)?|pre-?authorization)\b", re.IGNORECASE),
        re.compile(r"\breimbursement\s+(?:claim|facility|of\s+hospitalization)\b", re.IGNORECASE),
        re.compile(r"\bintimat(?:e|ion)\s+(?:within|timelines?)\b", re.IGNORECASE),
        re.compile(r"\b(?:tpa|third\s+party\s+administrator|surveyor|death\s+certificate|post\s+mortem|medico\s+legal|fir\s+copy|disability\s+certificate)\b", re.IGNORECASE),
        re.compile(r"\bgrievance\s+(?:redressal|cell|officer)|complaints?\b", re.IGNORECASE),
    ]

    COVERAGE_PATTERNS = [
        re.compile(r"\b(?:in-?patient|hospitalization|hospitalisation|day\s*care|pre-?hospitalization|post-?hospitalization|domiciliary)\b", re.IGNORECASE),
        re.compile(r"\b(?:coverage\s+(?:is\s+)?available|covered\s+(?:expenses?|treatments?|benefits?|up\s+to)|expenses?\s+covered)\b", re.IGNORECASE),
        re.compile(r"\b(?:icu\s+charges|room\s+rent|nursing\s+expenses?|medical\s+practitioner\s+fees|surgeon|anesthetist)\b", re.IGNORECASE),
        re.compile(r"\b(?:sum\s+insured|sum\s+assured|cumulative\s+bonus|restoration|restore\s+benefit|road\s+ambulance|air\s+ambulance)\b", re.IGNORECASE),
        re.compile(r"\b(?:ayush\s+treatment|organ\s+donor|modern\s+treatments?|bariatric|hospital\s+cash|daily\s+cash|health\s+check|e-opinion)\b", re.IGNORECASE),
        re.compile(r"\b(?:accidental\s+death|permanent\s+(?:total|partial)\s+disab|maternity|delivery|new\s*born|vaccination)\b", re.IGNORECASE),
        re.compile(r"\b(?:own\s+damage|third\s+party\s+liability|zero\s+depreciation|roadside\s+assistance|trip\s+cancellation|baggage\s+loss|medical\s+evacuation)\b", re.IGNORECASE),
    ]

    CONDITION_PATTERNS = [
        re.compile(r"\b(?:terms\s+and\s+conditions?|general\s+conditions?|operating\s+clause|standard\s+conditions?)\b", re.IGNORECASE),
        re.compile(r"\b(?:renewal|renewable|cancellation|grace\s+period|free\s+look\s+period|portability|migration|termination\s+of\s+cover|moratorium)\b", re.IGNORECASE),
        re.compile(r"\b(?:entry\s+age|eligib(?:le|ility)|dependent\s+children|age\s+limit|family\s+floater)\b", re.IGNORECASE),
        re.compile(r"\b(?:disclosure\s+of\s+(?:information|material\s+facts)|fraud|misrepresentation)\b", re.IGNORECASE),
        re.compile(r"\b(?:co-?payment|co-?pay|deductible|excess|sub-?limit(?:s)?|proportionate\s+deduction|discount)\b", re.IGNORECASE),
        re.compile(r"\b(?:geographical\s+limits?|territorial\s+limits?|jurisdiction|zone\s+[abc]|arbitration)\b", re.IGNORECASE),
    ]

    # Targeted regex cues for 10 Dimensions (used alongside semantic prototypes)
    DIMENSION_RULES: Dict[str, List[re.Pattern]] = {
        "overview": [
            re.compile(r"\b(?:preamble|operating\s+clause|policy\s+agreement|key\s+features|product\s+name|uin|sum\s+insured\s*\(?si\)?|policy\s+tenure|instalment\s+facility|coverage\s+basis|category\s+of\s+cover)\b", re.IGNORECASE),
            re.compile(r"\bthis\s+policy\s+(?:is\s+a\s+contract|provides|covers|is\s+specially\s+designed)\b", re.IGNORECASE),
        ],
        "eligibility": [
            re.compile(r"\b(?:entry\s+age|eligibility|eligible\s+(?:to|for|persons?)|age\s+eligibility|minimum\s+(?:entry\s+)?age|maximum\s+(?:entry\s+)?age|dependent\s+child(?:ren)?|aged\s+between\s+\d+|savings?\s+bank\s+account\s+holders?|valid\s+driving\s+licen[cs]e|proposer|who\s+can\s+(?:buy|apply|join)|enroll|renewed?\s+up\s+to\s+\d+\s+years|attains?\s+\d+\s+years)\b", re.IGNORECASE),
        ],
        "coverage": [
            re.compile(r"\b(?:in-?patient\s+treatment|hospitalization|day\s*care|modern\s+treatments?|pre\s+hospitalization|post\s+hospitalization|ambulance|organ\s+donor|domiciliary|home\s+care|ayush|delivery\s+and\s+new\s*born|vaccination|accidental\s+death|permanent\s+(?:total|partial)\s+disab|cumulative\s+bonus|automatic\s+restoration|wellness\s+program|own\s+damage|third\s+party|trip\s+cancellation|baggage)\b", re.IGNORECASE),
        ],
        "exclusions": [
            re.compile(r"\b(?:shall\s+not\s+be\s+liable|not\s+covered|strictly\s+excluded|permanently\s+excluded|permanent\s+exclusions?|key\s+exclusions?|shall\s+not\s+cover|does\s+not\s+cover|excl\d+|non-?medical\s+items?|non-?payable\s+items?|cosmetic|self-?injury|suicide|alcoholism|drug\s+or\s+substance\s+abuse|war,?\s+invasion|unproven\s+treatments?)\b", re.IGNORECASE),
        ],
        "waiting_periods": [
            re.compile(r"\b(?:waiting\s+period(?:s)?|(?:initial|specific|pre-?existing\s+disease|ped|maternity|survival)\s+wait(?:ing)?|\b(?:30|60|90)\s*days?\b.{0,25}\b(?:waiting|excluded|inception)|\b(?:12|24|36|48)\s*months?\b.{0,30}\b(?:continuous|waiting|ped|apply\s+afresh)|buy\s+back\s+of\s+pre-?existing|reduction\s+in\s+(?:specific\s+disease|ped|maternity)\s+waiting)\b", re.IGNORECASE),
        ],
        "limits": [
            re.compile(r"\b(?:sub-?limit(?:s)?|co-?pay(?:ment)?|deductible|excess|room\s+rent|icu\s+charges|proportionate\s+deduction|maximum\s+liability|company'?s\s+liability|limited\s+to|capped\s+at|discount\s+of\s+\d+|long-?term\s+discount|wellness\s+discount|per\s+day|per\s+eye|per\s+hospitali[sz]ation|per\s+policy\s+(?:year|period)|sum\s+insured\s*\(?₹|limits?\s+for\s+(?:delivery|vaccination|cataract|bariatric|hospital\s+cash|out-?patient))\b", re.IGNORECASE),
        ],
        "conditions": [
            re.compile(r"\b(?:grace\s+period|free\s+look\s+period|renewal|renewable|cancellation|termination\s+of\s+cover|portability|migration|moratorium|disclosure|fraud|misrepresentation|territorial\s+limits?|geographical|zone\s+[abc]|arbitration|instalment\s+facility|claim\s+experience\s+discount)\b", re.IGNORECASE),
        ],
        "claims": [
            re.compile(r"\b(?:claim\s+(?:process|procedure|intimation|notification|form|settlement)|cashless|reimbursement|pre-?authorization|discharge\s+summary|itemized\s+(?:hospital\s+)?bills?|diagnostic\s+reports?|payment\s+receipts?|medico\s+legal|post\s+mortem|death\s+certificate|disability\s+certificate|fir\s+copy|tpa|grievance\s+(?:redressal|officer)|complaints?)\b", re.IGNORECASE),
        ],
        "definitions": [
            re.compile(r"^(?:def\.?\s*\d+|\d+\.\d+(?:\([a-z0-9]+\))?\.?\s+[A-Z][\w\s/\-()]{1,45}\s+(?:means|shall\s+mean|refers\s+to))\b", re.IGNORECASE),
            re.compile(r"\b(?:standard\s+definitions?|specific\s+definitions?|means\s+(?:a|an|the|any|those|expenses|sudden|continuous|treatment|medical))\b", re.IGNORECASE),
        ],
        "limitations": [
            re.compile(r"\b(?:proportionate\s+deduction|co-?payment\s+of\s+\d+%|subject\s+to|provided\s+that|however,?\s+this\s+benefit\s+shall\s+not|available\s+only\s+when|not\s+applicable\s+for\s+this\s+section|specified\s+in\s+(?:the\s+)?policy\s+schedule|at\s+our\s+discretion|shall\s+terminate|notwithstanding|moratorium\s+period|pre-?hospitali[sz]ation\s+and\s+post|wait(?:ing)?\s+period\s+will\s+apply\s+afresh)\b", re.IGNORECASE),
        ],
    }

    _dim_proto_vectors: Optional[np.ndarray] = None
    _proto_model_name: Optional[str] = None
    _proto_lock = threading.Lock()

    @classmethod
    def _get_dimension_prototypes(cls) -> Optional[np.ndarray]:
        """
        Returns cached dense prototypes ONLY if neural embeddings are explicitly enabled
        and already initialized (never forces slow CPU PyTorch loading).
        """
        from app.core.config import settings
        if not settings.USE_NEURAL_EMBEDDINGS or EmbeddingService._model is None:
            return None

        active_model = EmbeddingService.get_model_name()
        if cls._dim_proto_vectors is not None and cls._proto_model_name == active_model:
            return cls._dim_proto_vectors

        with cls._proto_lock:
            active_model = EmbeddingService.get_model_name()
            if cls._dim_proto_vectors is not None and cls._proto_model_name == active_model:
                return cls._dim_proto_vectors

            try:
                proto_texts = [f"{d['title']}: {d['prototype']}" for d in cls.DIMENSIONS]
                vecs = EmbeddingService.encode_batch(proto_texts, batch_size=10)
                if vecs and len(vecs) == len(cls.DIMENSIONS):
                    mat = np.array(vecs, dtype=np.float32)
                    norms = np.linalg.norm(mat, axis=1, keepdims=True)
                    norms[norms == 0] = 1.0
                    cls._dim_proto_vectors = mat / norms
                    cls._proto_model_name = active_model
            except Exception as e:
                logger.warning(f"Could not compute dimension prototype vectors: {e}")
                cls._dim_proto_vectors = None
        return cls._dim_proto_vectors

    @classmethod
    def is_definition_clause(cls, text: str, section_name: str = "", chunk_type: str = "") -> bool:
        if chunk_type == "definition":
            return True
        sec_low = (section_name or "").lower()
        t = (text or "").strip()
        if re.match(r"^(?:def\.?\s*\d+|\d+\.\d+(?:\([a-z0-9]+\))?\.?\s+[A-Z][\w\s/\-()]{1,48}\s+(?:means|shall\s+mean|refers\s+to))\b", t):
            return True
        if ("definition" in sec_low or "definitions" in sec_low) and re.search(r"\b(?:means|shall\s+mean|refers\s+to)\b", t[:160]):
            return True
        return False

    @classmethod
    def classify(cls, text: str, section_name: str = "", chunk_type: str = "") -> Tuple[str, float]:
        """
        Coarse clause classifier mapping into standard policy categories
        (Coverage, Exclusion, Waiting Period, Condition, Claim Requirement, General)
        with improved structural guards against definition/TOC/ombudsman drift.
        """
        if chunk_type == "toc":
            return "General", 0.55
        if chunk_type == "ombudsman":
            return "Claim Requirement", 0.72
        if chunk_type == "non_medical_list":
            return "Exclusion", 0.90

        text_lower = text.lower()
        sec_lower = (section_name or "").lower()

        # Pure definitions go cleanly to General (so they don't hijack Coverage/Eligibility)
        # unless they explicitly state a policy rule/waiting period/exclusion
        is_def = cls.is_definition_clause(text, section_name, chunk_type)

        scores = {
            "Waiting Period": 0.0,
            "Exclusion": 0.0,
            "Claim Requirement": 0.0,
            "Coverage": 0.0,
            "Condition": 0.0,
        }

        for p in cls.EXCLUSION_PATTERNS:
            if p.search(text_lower):
                scores["Exclusion"] += 0.50

        for p in cls.WAITING_PERIOD_PATTERNS:
            if p.search(text_lower):
                scores["Waiting Period"] += 0.55

        for p in cls.CLAIM_PATTERNS:
            if p.search(text_lower):
                scores["Claim Requirement"] += 0.50

        for p in cls.COVERAGE_PATTERNS:
            if p.search(text_lower):
                scores["Coverage"] += 0.40

        for p in cls.CONDITION_PATTERNS:
            if p.search(text_lower):
                scores["Condition"] += 0.35

        # Section context bonuses
        if "exclusion" in sec_lower:
            scores["Exclusion"] += 0.40
        elif "waiting" in sec_lower:
            scores["Waiting Period"] += 0.40
        elif "claim" in sec_lower or "grievance" in sec_lower:
            scores["Claim Requirement"] += 0.40
        elif any(w in sec_lower for w in ("benefit", "coverage", "key features", "delivery", "modern treatment", "ambulance", "wellness", "cash")):
            scores["Coverage"] += 0.35
        elif any(w in sec_lower for w in ("condition", "limit", "eligibility", "entry age", "discount", "tenure", "grace", "termination", "co-payment")):
            scores["Condition"] += 0.35

        # Suppress Coverage/Condition false-positives on pure definitions
        if is_def:
            scores["Coverage"] *= 0.35
            scores["Condition"] *= 0.40
            if max(scores.values()) < 0.55:
                return "General", 0.85

        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]

        if best_score < 0.28:
            return "General", 0.55

        confidence = min(0.98, max(0.55, round(0.50 + (best_score * 0.35), 2)))
        return best_category, confidence

    @classmethod
    def score_clause_for_dimensions(
        cls,
        clause_text: str,
        section_name: str = "",
        category: str = "",
        page_number: int = 1,
        chunk_type: str = "clause",
        clause_embedding: Optional[List[float]] = None,
    ) -> Dict[str, Tuple[float, bool]]:
        """
        Scores a single clause across all 10 Policy Dimensions using:
        1) Pre-computed Dense Semantic Similarity against 10 dimension prototypes, and
        2) Structural & rule-based safeguards (suppressing definitions from Eligibility/Coverage,
           filtering out TOC/Ombudsman noise, and boosting numeric/limit/table chunks in Limits).
        Returns {dim_key: (score_0_to_1, has_explicit_signal)}.
        """
        t_clean = (clause_text or "").strip()
        t_low = t_clean.lower()
        sec_low = (section_name or "").lower()

        if chunk_type == "toc" or re.search(r"\btable\s+of\s+contents\b", sec_low):
            return {d["key"]: (0.0, False) for d in cls.DIMENSIONS}

        is_ombudsman = (
            chunk_type == "ombudsman"
            or "ombudsman" in sec_low
            or "bimalokpal" in t_low
            or "areas of jurisdiction" in t_low
        )
        is_def = cls.is_definition_clause(t_clean, section_name, chunk_type)
        is_non_med = chunk_type == "non_medical_list" or "non-medical" in sec_low

        # Dense semantic similarities [0..1] when neural vectors exist, else fast lexical prototype match
        proto_mat = cls._get_dimension_prototypes()
        sem_scores: Dict[str, float] = {d["key"]: 0.0 for d in cls.DIMENSIONS}
        using_neural = proto_mat is not None and bool(clause_embedding)
        if using_neural:
            vec = np.array(clause_embedding, dtype=np.float32)
            vnorm = np.linalg.norm(vec)
            if vnorm > 0:
                vec = vec / vnorm
                sims = proto_mat @ vec  # shape (10,)
                for idx, d in enumerate(cls.DIMENSIONS):
                    sem_scores[d["key"]] = float(max(0.0, min(1.0, (sims[idx] + 0.15) / 0.85)))
        else:
            clause_bag = set(re.findall(r"[a-z]{4,}", f"{t_low} {sec_low}"))
            for d in cls.DIMENSIONS:
                p_tokens = set(re.findall(r"[a-z]{4,}", d["prototype"].lower()))
                hits = len(clause_bag & p_tokens)
                sem_scores[d["key"]] = float(min(1.0, hits / 3.5)) if hits > 0 else 0.0

        results: Dict[str, Tuple[float, bool]] = {}

        for d in cls.DIMENSIONS:
            key = d["key"]
            sem = sem_scores.get(key, 0.0)
            rule_hits = 0
            for pat in cls.DIMENSION_RULES.get(key, []):
                if pat.search(t_clean) or pat.search(sec_low):
                    rule_hits += 1

            cat_match = category in set(d["categories"])
            has_signal = rule_hits > 0

            # Base hybrid score: lexical/neural semantic + rule hits + category alignment
            if using_neural:
                rule_bonus = min(0.55, rule_hits * 0.24)
                cat_bonus = 0.12 if cat_match else 0.0
                score = (0.42 * sem) + rule_bonus + cat_bonus
            else:
                rule_bonus = min(0.68, 0.34 + (rule_hits - 1) * 0.17) if rule_hits > 0 else 0.0
                cat_bonus = 0.16 if cat_match else 0.0
                score = (0.28 * sem) + rule_bonus + cat_bonus

            # Structural & domain safeguards per dimension
            if is_ombudsman:
                if key == "claims":
                    score = 0.36  # Keep lower than actual claim filing rules & document lists
                    has_signal = True
                else:
                    score = 0.0
                    has_signal = False
                results[key] = (score, has_signal)
                continue

            if is_non_med:
                if key == "exclusions":
                    score = max(score, 0.62)
                    has_signal = True
                else:
                    score *= 0.2
                    has_signal = False
                results[key] = (score, has_signal)
                continue

            if key == "overview":
                # Strongly favor early pages (1-3), preamble, key features, CIS product table
                if page_number <= 3:
                    score += 0.20
                    if "preamble" in sec_low or "overview" in sec_low or "key features" in sec_low or "table of benefits" in sec_low:
                        score += 0.22
                        has_signal = True
                elif page_number > 6 and not has_signal:
                    score *= 0.65
                if is_def:
                    score *= 0.30
                    has_signal = False

            elif key == "eligibility":
                # Strict safeguard: Definitions NEVER belong under Eligibility!
                if is_def or "definition" in sec_low or "table of benefits" in t_low[:90]:
                    score = 0.0
                    has_signal = False
                elif has_signal:
                    if re.search(r"\b\d+\s*(?:years?|days?|months?)\b", t_low):
                        score += 0.22
                    if any(w in sec_low for w in ("entry age", "eligibility", "eligible")):
                        score += 0.25
                    if not re.search(r"\b(?:entry\s+age|eligib(?:le|ility)|aged\s+between|\d+\s*(?:years?|months?|days?)|savings?\s+bank|dependent\s+child)\b", t_low):
                        score *= 0.45
                else:
                    # Without explicit eligibility signal, cannot force unrelated Condition clauses
                    score *= 0.45

            elif key == "definitions":
                if is_def:
                    score += 0.35
                    has_signal = True
                elif "definition" in sec_low:
                    score += 0.15
                else:
                    score *= 0.45

            elif key == "coverage":
                if is_def:
                    score *= 0.25
                    has_signal = False
                elif "exclusion" in sec_low:
                    score *= 0.25
                    has_signal = False
                elif re.search(r"\b(?:shall\s+not\s+be\s+liable|permanently\s+excluded)\b", t_low):
                    score *= 0.25
                    has_signal = False

            elif key == "exclusions":
                if is_def and not re.search(r"\bexcluded\b", t_low):
                    score *= 0.25
                    has_signal = False
                elif "exclusion" in sec_low:
                    score += 0.25
                    has_signal = True

            elif key == "waiting_periods":
                is_mig_port = (
                    any(w in sec_low for w in ("migration", "portability"))
                    or bool(re.search(r"\b(?:migrate|migration|portability|continuity\s+benefits?\s+in\s+waiting\s+periods?)\b", t_low))
                ) and not re.search(
                    r"\b(?:initial\s+waiting|first\s+\d+\s+days?\s+waiting|specific\s+(?:disease|illness|procedure)\s+waiting|pre-?existing\s+disease[s\s]+waiting)\b",
                    t_low,
                )
                if is_mig_port or (is_def and not re.search(r"\bwaiting\s+period\b", t_low)):
                    score *= 0.15
                    has_signal = False
                elif "waiting" in sec_low:
                    score += 0.25
                    has_signal = True

            elif key == "limits":
                if is_def and not re.search(r"\b(?:co-?pay|deductible|sub-?limit|capped|maximum)\b", t_low):
                    score *= 0.30
                    has_signal = False
                else:
                    # Strong quantitative currency/percentage signal boosts Financial Limits
                    has_num_cap = bool(re.search(r"(?:₹|rs\.?|inr)\s*[\d,]+|\b\d+\s*%", t_low, re.IGNORECASE))
                    if has_num_cap and has_signal:
                        score += 0.22
                    if chunk_type == "policy_table" and has_num_cap:
                        score += 0.18
                        has_signal = True

            elif key == "conditions":
                if is_def:
                    score *= 0.30
                    has_signal = False

            elif key == "claims":
                if is_def and not re.search(r"\b(?:claim\s+form|intimation|documents?\s+required|cashless|reimbursement)\b", t_low):
                    score *= 0.25
                    has_signal = False

            elif key == "limitations":
                if is_def:
                    score *= 0.25
                    has_signal = False
                elif re.search(r"\b(?:proportionate\s+deduction|co-?payment\s+of\s+\d+%|subject\s+to|provided\s+that|policy\s+schedule|waiting\s+period\s+will\s+apply\s+afresh|however,?\s+this\s+benefit\s+shall\s+not|available\s+only\s+when)\b", t_low):
                    score += 0.20
                    has_signal = True

            results[key] = (round(min(1.0, score), 4), has_signal)

        return results
