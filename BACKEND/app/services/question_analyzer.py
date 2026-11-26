import re
from typing import Dict, Any, List, Optional


class QuestionAnalyzer:
    """
    Generalized Domain-Agnostic Insurance Question Analyzer & Follow-Up Contextualizer.
    Handles Health, Motor, Life/Term, Travel, Personal Accident, and Corporate policies.
    Detects:
    - Language (English / Hindi / Hinglish)
    - Question response style (yes_no_verification, list_overview, numeric_limit_timeline,
      comparison_conditional, general_explanation)
    - Backwards-compatible retrieval intent & category boosts
    - Multi-turn follow-up resolution using recent conversation turns
    - Distinctive subject entities/tokens for strict out-of-document checking
    """

    TOPIC_SYNONYMS: Dict[str, List[str]] = {
        "maternity": [
            "maternity", "pregnancy", "childbirth", "newborn", "new born", "delivery",
            "cesarean", "caesarean", "c-section", "vaccination", "obstetric"
        ],
        "cataract": [
            "cataract", "eye surgery", "intraocular lens", "ophthalmology", "per eye"
        ],
        "pre_existing_disease": [
            "pre-existing", "pre existing", "ped", "existing disease", "chronic",
            "diabetes", "hypertension", "asthma"
        ],
        "room_rent": [
            "room rent", "icu", "intensive care", "single private", "twin sharing",
            "room category", "proportionate deduction", "nursing"
        ],
        "waiting_period": [
            "waiting period", "wait time", "initial waiting", "30 days", "24 months",
            "36 months", "48 months", "survival period", "cooling period", "buy back"
        ],
        "exclusions": [
            "exclusion", "exclusions", "not covered", "excluded", "permanent exclusion",
            "non-payable", "non-medical", "shall not be liable"
        ],
        "claim_procedure": [
            "claim", "reimbursement", "cashless", "documents required", "tpa",
            "intimation", "pre-authorization", "discharge summary", "surveyor", "fir", "death certificate"
        ],
        "ayush": [
            "ayush", "ayurveda", "homeopathy", "unani", "siddha", "yoga", "naturopathy"
        ],
        "day_care": [
            "day care", "daycare", "dialysis", "chemotherapy", "radiotherapy", "less than 24 hours"
        ],
        "hospitalization_conditions": [
            "hospitalization", "hospitalisation", "in-patient", "24 hours", "24 consecutive",
            "admission", "domiciliary", "home care"
        ],
        "donor_expenses": [
            "organ donor", "donor", "transplant", "harvesting"
        ],
        "ambulance": [
            "ambulance", "road ambulance", "air ambulance", "emergency transport"
        ],
        "restore_benefit": [
            "restore", "restoration", "recharge", "cumulative bonus", "no claim bonus", "ncb"
        ],
        "sub_limits": [
            "sub-limit", "sublimit", "limit", "cap", "maximum liability", "co-pay", "copay",
            "co-payment", "deductible", "excess", "sum insured", "sum assured", "idv", "hospital cash"
        ],
        "discounts": [
            "discount", "long-term discount", "wellness discount", "online discount",
            "claim experience discount", "tenure", "renewal discount", "wellness points"
        ],
        "eligibility": [
            "eligibility", "eligible", "entry age", "age limit", "dependent", "children",
            "renewal age", "bank account", "driving license", "who can apply"
        ],
        "modern_treatments": [
            "modern treatment", "robotic", "stem cell", "immunotherapy", "oral chemotherapy",
            "balloon sinoplasty", "deep brain", "hifu"
        ],
        "outpatient_dental": [
            "outpatient", "out-patient", "opd", "dental", "ophthalmic", "consultation", "bariatric"
        ],
        "accidental_disability": [
            "accidental death", "permanent total disablement", "permanent partial disablement",
            "disablement", "loss of limb", "loss of eye", "pmsby"
        ],
        "motor_policy": [
            "idv", "insured declared value", "own damage", "third party", "zero depreciation",
            "roadside assistance", "ncb", "no claim bonus", "theft", "engine protect"
        ],
        "life_term_policy": [
            "sum assured", "death benefit", "maturity benefit", "nominee", "surrender value",
            "paid-up", "suicide clause", "policy term", "rider", "critical illness"
        ],
        "travel_policy": [
            "baggage", "trip cancellation", "trip delay", "flight delay", "passport loss",
            "medical evacuation", "repatriation", "schengen", "overseas"
        ],
        "renewal_grace": [
            "grace period", "free look", "renewal", "cancellation", "termination",
            "portability", "moratorium", "instalment"
        ],
    }

    HINGLISH_KEYWORDS = {
        "kya", "hai", "hain", "kaunse", "kaun", "kitna", "kitni", "kitne", "hoga", "hogi",
        "nahi", "milta", "milti", "milega", "batao", "bataiye", "kaise", "chahiye", "kab",
        "kisko", "shamil", "bina", "kharche", "bimar", "bimari", "mein", "ke", "liye", "pe",
        "par", "aur", "ya", "koi", "iske", "iska", "iski", "jaankari", "daant", "ilaj"
    }

    HINDI_TO_ENGLISH_BRIDGE: Dict[str, str] = {
        # Hinglish terms
        "daant": "dental", "danton": "dental", "daanto": "dental",
        "bimari": "illness disease", "bimariyon": "diseases",
        "ilaj": "treatment", "kharche": "expenses", "kharcha": "expenses",
        "dastavez": "documents", "kaagaz": "documents", "kagaz": "documents",
        "chahiye": "required", "milega": "covered payable", "milta": "covered",
        "shamil": "covered included", "bina": "without",
        "shart": "condition", "shartein": "conditions", "niyam": "rules conditions",
        "seemayein": "limits", "seema": "limit cap",
        "intezar": "waiting period", "pratiksha": "waiting period",
        "prasav": "delivery maternity", "matritva": "maternity",
        "durghatna": "accident accidental", "mrityu": "death",
        "aspatal": "hospital hospitalization", "kamra": "room rent",
        "aayu": "age", "umra": "age eligibility", "patrata": "eligibility",
        "chhoot": "discount", "nuksan": "loss damage", "bahar": "excluded exclusion",
        # Devanagari terms
        "क्लेम": "claim", "दस्तावेज": "documents", "कागजात": "documents",
        "दांत": "dental", "दांतों": "dental", "इलाज": "treatment", "खर्च": "expenses",
        "बीमारी": "disease illness", "प्रतीक्षा": "waiting period",
        "मातृत्व": "maternity delivery", "अस्पताल": "hospital hospitalization",
        "दुर्घटना": "accident", "मृत्यु": "death", "कमरा": "room rent",
        "बहिष्करण": "exclusion not covered", "शर्तें": "conditions", "सीमा": "limit sub-limit",
        "छूट": "discount", "आयु": "age eligibility", "पात्रता": "eligibility",
        "मोतियाबिंद": "cataract", "बोनस": "bonus", "बीमा": "insurance policy",
        "कवर": "cover coverage", "नियम": "rules terms", "मदद": "help support",
    }

    @classmethod
    def _bridge_hindi_to_english(cls, text: str) -> str:
        """
        Translates common Hindi (Devanagari) and Hinglish insurance words into
        English retrieval tokens so BM25 & MiniLM retrieve the exact PDF clauses cleanly.
        """
        extra_terms: List[str] = []
        lower = text.lower()
        for src, eng in cls.HINDI_TO_ENGLISH_BRIDGE.items():
            if src in lower or src in text:
                extra_terms.extend(eng.split())
        if not extra_terms:
            return text
        dedup = list(dict.fromkeys(extra_terms))
        return f"{text} " + " ".join(dedup)

    GENERIC_QUERY_WORDS = {
        "policy", "policies", "insurance", "document", "pdf", "uploaded", "active", "plan",
        "cover", "covered", "coverage", "benefit", "benefits", "expense", "expenses",
        "treatment", "treatments", "procedure", "procedures", "condition", "conditions",
        "term", "terms", "clause", "clauses", "limit", "limits", "waiting", "period",
        "periods", "exclusion", "exclusions", "excluded", "include", "included",
        "claim", "claims", "required", "document", "documents", "eligible", "eligibility",
        "details", "information", "explain", "tell", "list", "show", "give", "mention",
        "does", "will", "would", "could", "should", "have", "what", "which", "when",
        "where", "whom", "whose", "this", "that", "these", "those", "there", "here",
        "about", "under", "with", "from", "into", "between", "difference", "much",
        "many", "apply", "applies", "applicable", "payable", "available", "standard",
        "general", "specific", "medical", "hospital", "health", "person", "insured",
        "policyholder", "company", "insurer", "year", "years", "month", "months", "day", "days",
        "scheme", "yojana", "pmsby", "star", "sbig", "equicover", "comprehensive", "alpha", "careshield",
        "kya", "hai", "hain", "mein", "ka", "ke", "ki", "ko", "se", "aur", "par", "nahi", "haan",
        "milta", "milti", "milega", "hota", "hoti", "chahiye", "kaunse", "kitna", "kitni", "batao",
    }

    @classmethod
    def detect_language(cls, text: str) -> str:
        if re.search(r"[\u0900-\u097F]", text):
            return "hindi"
        words = set(re.findall(r"\b[a-z]+\b", text.lower()))
        if words.intersection(cls.HINGLISH_KEYWORDS):
            return "hinglish"
        return "english"

    @classmethod
    def _resolve_followup(
        cls,
        question: str,
        conversation_context: Optional[List[Dict[str, str]]],
    ) -> str:
        """
        Resolves anaphoric follow-ups (e.g., 'What about its waiting period?' -> combines prior user topic)
        so retrieval searches for the actual subject instead of bare pronouns.
        """
        if not conversation_context:
            return question

        q_low = question.lower()
        has_pronoun = bool(re.search(r"\b(?:it|its|this|that|they|their|them|above|same)\b", q_low))
        short_followup = len(question.split()) <= 7 and (has_pronoun or q_low.startswith(("and ", "what about", "how about")))

        if not (has_pronoun or short_followup):
            return question

        # Find most recent previous user message
        prev_user_qs = [m["content"] for m in conversation_context if m.get("role") == "user" and m.get("content")]
        if not prev_user_qs:
            return question
        last_q = prev_user_qs[-1].strip()
        if not last_q or last_q.lower() == q_low:
            return question

        # Extract meaningful anchor tokens from the prior user question
        prior_tokens = [
            w for w in re.findall(r"[a-zA-Z0-9\-]{3,}", last_q)
            if w.lower() not in {"what", "does", "this", "policy", "cover", "under", "about", "how", "much", "there", "are"}
        ]
        if not prior_tokens:
            return question
        anchor = " ".join(prior_tokens[:6])
        return f"{question} (regarding {anchor})"

    @classmethod
    def extract_specific_subject(cls, text: str) -> str:
        """
        Extracts the specific queried disease/benefit/item/peril phrase cleanly
        regardless of length or insurance domain.
        """
        lower = text.lower().strip().rstrip("?.!")
        patterns = [
            r"(?:cover(?:age)?|covered|pay(?:able)?\s+for|reimburse(?:ment)?\s+for|treatment\s+(?:for|of)|benefits?\s+for|expenses?\s+(?:for|of)|eligibility\s+for|eligible\s+(?:for|to))\s+([a-zA-Z0-9\s\-/]{3,65}?)(?:\s+(?:if|when|in\s+this|under\s+this|in\s+case|for\s+₹)|\s*$)",
            r"(?:mention(?:s|ed)?|state|talk\s+about|details?\s+(?:about|on|for)|say\s+about)\s+(?:a\s+|an\s+|the\s+)?([a-zA-Z0-9\s\-/]{3,65}?)(?:\s+(?:in\s+this|under\s+this)|\s*$)",
            r"^(?:is|are|does\s+(?:the\s+|this\s+)?[a-z0-9\s]{0,20}(?:policy|scheme)\s+(?:cover|include))\s+([a-zA-Z0-9\s\-/]{3,65}?)(?:\s+(?:covered|included|excluded|payable|allowed)|\s*$)",
        ]
        for pat in patterns:
            m = re.search(pat, lower)
            if m:
                extracted = m.group(1).strip()
                # Strip leading/trailing articles & Hinglish filler tokens
                extracted = re.sub(r"^(?:the|a|an|any|all|this|my|such|is|mein|ka|ke|ki)\s+", "", extracted).strip()
                extracted = re.sub(r"\s+(?:hai|hain|hota|hoti|kya|mein)$", "", extracted).strip()
                if (
                    extracted
                    and extracted not in cls.GENERIC_QUERY_WORDS
                    and extracted not in cls.HINGLISH_KEYWORDS
                    and len(extracted) >= 3
                ):
                    return extracted
        return ""

    @classmethod
    def extract_distinctive_tokens(cls, text: str, specific_subject: str = "") -> List[str]:
        """
        Extracts non-generic content nouns/words from the question and specific subject
        to detect out-of-scope queries reliably (e.g. 'space', 'tourism', 'bitcoin').
        """
        target = specific_subject or text
        words = re.findall(r"[a-zA-Z]{3,}", target.lower())
        extra_stops = {"for", "and", "the", "with", "from", "into", "that", "this", "are", "was", "were", "has", "have"}
        tokens = [w for w in words if w not in cls.GENERIC_QUERY_WORDS and w not in extra_stops]
        # Preserve order, deduplicate
        return list(dict.fromkeys(tokens))

    @classmethod
    def _detect_response_style(cls, lower_q: str) -> str:
        """
        Classifies question into 1 of 5 user-facing response archetypes:
        yes_no_verification, comparison_conditional, numeric_limit_timeline,
        list_overview, general_explanation.
        """
        if re.search(
            r"\b(?:what\s+(?:are|is)\s+(?:all\s+|the\s+)?(?:treatments|expenses|covered|benefits|features|exclusions|waiting\s+periods|"
            r"documents|conditions|modern\s+treatments|limitations)|what\s+(?:treatments|expenses|benefits|features)\s+(?:and\s+[a-z]+\s+)?(?:are|is)\s+covered|"
            r"what\s+does\s+(?:this|the)\s+policy\s+cover|list\s+(?:all|the)|overview\s+of)\b",
            lower_q,
        ):
            return "list_overview"

        if re.search(
            r"^(?:is|are|can|will|does|do|am|would|could)\b|"
            r"\b(?:eligible\??|included\??|excluded\??|allow(?:ed)?\??|payable\??|kya\s+.+\s+(?:cover|milta|milega))\b",
            lower_q,
        ):
            if not re.search(r"\b(?:difference\s+between|compare|what\s+happens\s+if|what|which|how|who|whom|whose|when|where)\b", lower_q):
                return "yes_no_verification"

        if re.search(
            r"\b(?:difference\s+between|compare|comparison|versus|vs\.?|what\s+happens\s+if|in\s+case\s+i|"
            r"2-?year\s+and\s+3-?year|2\s+year\s+and\s+3\s+year|before\s+\d+\s+vs|above\s+\d+|between\s+.+\s+and)\b",
            lower_q,
        ):
            return "comparison_conditional"

        if re.search(
            r"\b(?:how\s+much|how\s+long|how\s+many|what\s+is\s+the\s+(?:waiting\s+period|limit|sub-?limit|cap|"
            r"co-?pay|deductible|excess|discount|bonus|age\s+limit|entry\s+age|sum\s+insured|sum\s+assured|"
            r"grace\s+period|free\s+look|room\s+rent|tenure|amount|percentage)|maximum|kitna|kitni|kab)\b",
            lower_q,
        ):
            return "numeric_limit_timeline"

        return "general_explanation"

    @classmethod
    def analyze(
        cls,
        question: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        raw_text = question.strip()
        language = cls.detect_language(raw_text)
        bridged_q = cls._bridge_hindi_to_english(raw_text) if language in ("hindi", "hinglish") else raw_text
        contextualized_q = cls._resolve_followup(bridged_q, conversation_context)
        lower_q = contextualized_q.lower()
        response_style = cls._detect_response_style(raw_text.lower())

        # 1. Identify Topics & Synonyms
        detected_topics: List[str] = []
        synonym_additions: List[str] = []

        for topic, terms in cls.TOPIC_SYNONYMS.items():
            for term in terms:
                if re.search(rf"\b{re.escape(term)}\b", lower_q):
                    detected_topics.append(topic)
                    synonym_additions.extend(terms[:4])
                    break

        specific_entity = cls.extract_specific_subject(contextualized_q)
        distinctive_tokens = cls.extract_distinctive_tokens(bridged_q if language in ("hindi", "hinglish") else raw_text, specific_entity)
        is_unrecognized_specific = False

        if detected_topics:
            primary_topic = detected_topics[0]
        elif specific_entity:
            primary_topic = specific_entity.replace(" ", "_")[:60]
            is_unrecognized_specific = True
        else:
            primary_topic = "general_policy"

        # 2. Identify Retrieval Intent & Dynamic Category Boosts
        is_comprehensive = bool(
            response_style in ("list_overview", "comparison_conditional")
            or re.search(r"\b(?:list\s+all|all\s+exclusions|every|complete\s+list|all\s+waiting\s+periods|detailed)\b", lower_q)
        )

        category_boosts = {
            "Coverage": 0.0,
            "Exclusion": 0.0,
            "Waiting Period": 0.0,
            "Condition": 0.0,
            "Claim Requirement": 0.0,
            "General": 0.0,
        }

        if re.search(r"\b(?:waiting\s+period|how\s+long\s+to\s+wait|wait\s+time|cooling\s+period|survival\s+period|kitna\s+wait|kab\s+milega)\b", lower_q):
            intent = "waiting_period_inquiry"
            required_categories = ["Waiting Period", "Condition"]
            category_boosts["Waiting Period"] = 0.70
            category_boosts["Condition"] = 0.30

        elif re.search(r"\b(?:exclusion|not\s+covered|what\s+is\s+excluded|exclusions?\s+related|nahi\s+milega|shamil\s+nahi)\b", lower_q):
            intent = "exclusion_inquiry"
            required_categories = ["Exclusion", "Condition"]
            category_boosts["Exclusion"] = 0.75
            category_boosts["Condition"] = 0.25

        elif re.search(r"\b(?:documents?\s+(?:required|needed)|how\s+to\s+claim|claim\s+process|file\s+a\s+claim|reimbursement|cashless|intimation|ombudsman|claim\s+kaise)\b", lower_q):
            intent = "claim_inquiry"
            required_categories = ["Claim Requirement", "Condition"]
            category_boosts["Claim Requirement"] = 0.80
            category_boosts["Condition"] = 0.20

        elif re.search(r"\b(?:is\s+.+\s+covered|does\s+(?:the\s+|this\s+)?policy\s+cover|coverage\s+for|are\s+.+\s+covered|am\s+i\s+eligible|kya\s+.+\s+(?:cover|milta)|cover\s+hai)\b", lower_q):
            intent = "coverage_inquiry"
            required_categories = ["Coverage", "Waiting Period", "Exclusion", "Condition"]
            category_boosts["Coverage"] = 0.40
            category_boosts["Waiting Period"] = 0.25
            category_boosts["Exclusion"] = 0.25
            category_boosts["Condition"] = 0.10

        elif re.search(r"\b(?:limit|sub-?limit|cap|maximum\s+amount|co-?pay|deductible|excess|discount|room\s+rent|sum\s+insured|sum\s+assured|idv|kitna\s+limit)\b", lower_q):
            intent = "limit_inquiry"
            required_categories = ["Condition", "Coverage"]
            category_boosts["Condition"] = 0.60
            category_boosts["Coverage"] = 0.40

        elif re.search(r"\b(?:conditions?\s+for\s+hospitalization|24\s+hours|admit|admission\s+rules?|hospitalization\s+criteria)\b", lower_q):
            intent = "hospitalization_conditions"
            required_categories = ["Coverage", "Condition"]
            category_boosts["Coverage"] = 0.60
            category_boosts["Condition"] = 0.40

        elif re.search(r"\b(?:what\s+does\s+(?:this|the)\s+policy\s+cover|benefits?\s+of\s+(?:this|the)\s+policy|overall\s+coverage|key\s+features)\b", lower_q):
            intent = "overview_coverage"
            required_categories = ["Coverage", "Condition"]
            category_boosts["Coverage"] = 0.70
            category_boosts["Condition"] = 0.30

        else:
            intent = "general_qa"
            required_categories = ["Coverage", "Condition", "General"]
            category_boosts["Coverage"] = 0.40
            category_boosts["Condition"] = 0.30
            category_boosts["General"] = 0.30

        # Keep expanded query concise so synonyms enhance without diluting exact nouns
        unique_synonyms = [s for s in dict.fromkeys(synonym_additions) if s.lower() not in lower_q]
        expanded_query = f"{contextualized_q} " + " ".join(unique_synonyms[:5]) if unique_synonyms else contextualized_q

        return {
            "original_question": raw_text,
            "contextualized_question": contextualized_q,
            "expanded_query": expanded_query.strip(),
            "language": language,
            "response_style": response_style,
            "topic": primary_topic,
            "specific_entity": specific_entity,
            "distinctive_tokens": distinctive_tokens,
            "is_unrecognized_specific": is_unrecognized_specific,
            "all_topics": detected_topics,
            "intent": intent,
            "is_comprehensive": is_comprehensive,
            "required_categories": required_categories,
            "category_boosts": category_boosts,
        }
