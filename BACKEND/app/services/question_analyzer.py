import re
from typing import Dict, Any, List

class QuestionAnalyzer:
    """
    Advanced Insurance Question Analyzer & Synonym Expansion Engine.
    Detects language (English / Hindi / Hinglish), intent, target topics,
    extracts named condition/disease entities, generates domain synonym expansions,
    and calculates dynamic retrieval category boosts.
    """

    TOPIC_SYNONYMS = {
        "maternity": [
            "maternity", "pregnancy", "childbirth", "newborn", "delivery", "cesarean", "c-section", "maternity benefit"
        ],
        "cataract": [
            "cataract", "eye surgery", "lens", "cataract operation", "ophthalmology", "intraocular lens"
        ],
        "pre_existing_disease": [
            "pre-existing", "ped", "existing disease", "chronic", "diabetes", "hypertension", "blood pressure", "pre existing condition"
        ],
        "room_rent": [
            "room rent", "icu", "suite", "hospital room", "room rent capping", "proportionate deduction", "single private room"
        ],
        "waiting_period": [
            "waiting period", "wait time", "initial waiting", "cooling period", "30 days", "24 months", "36 months", "48 months"
        ],
        "exclusions": [
            "exclusion", "exclusions", "not covered", "excluded", "permanent exclusion", "non-payable", "uncovered"
        ],
        "claim_procedure": [
            "claim", "reimbursement", "cashless", "documents required", "tpa", "intimation", "claim settlement", "discharge summary"
        ],
        "ayush": [
            "ayush", "ayurveda", "homeopathy", "unani", "siddha", "yoga", "alternative treatment"
        ],
        "day_care": [
            "day care", "daycare", "dialysis", "chemotherapy", "radiotherapy", "less than 24 hours"
        ],
        "hospitalization_conditions": [
            "hospitalization", "in-patient", "hospitalized", "minimum 24 hours", "admission", "admitted", "hospital stay"
        ],
        "donor_expenses": [
            "organ donor", "donor", "transplant", "harvesting"
        ],
        "ambulance": [
            "ambulance", "road ambulance", "air ambulance", "emergency transport"
        ],
        "restore_benefit": [
            "restore", "restoration", "recharge", "cumulative bonus", "no claim bonus", "refill"
        ],
        "sub_limits": [
            "sub-limit", "financial limit", "maximum cap", "co-pay", "copayment", "deductible", "limit"
        ],
        "eligibility": [
            "eligibility", "age limit", "entry age", "dependent", "renewal age", "who is covered"
        ]
    }

    HINGLISH_KEYWORDS = [
        "kya", "hai", "kitna", "kitni", "hoga", "hogi", "nahi", "milta", "milega", "batao",
        "kaise", "chahiye", "kab", "kisko", "shamil", "bina", "kharche", "bimar", "bimari"
    ]

    @classmethod
    def detect_language(cls, text: str) -> str:
        """
        Detects whether user query is English, Hindi (Devanagari), or Hinglish.
        """
        if re.search(r"[\u0900-\u097F]", text):
            return "hindi"

        lower = text.lower()
        words = set(re.findall(r"\b[a-z]+\b", lower))
        hinglish_matches = words.intersection(cls.HINGLISH_KEYWORDS)
        if len(hinglish_matches) >= 1:
            return "hinglish"

        return "english"

    @classmethod
    def extract_specific_subject(cls, text: str) -> str:
        """
        Extracts specific disease or condition entity mentioned in the query.
        e.g. 'Does the policy cover Zika virus treatment?' -> 'Zika virus'
        """
        lower = text.lower()
        patterns = [
            r"(?:cover(?:age)?|covered|treatment\s+(?:for|of)|benefits?\s+for|expenses?\s+for)\s+([a-zA-Z\s]{3,28}?)(?:\s+(?:treatment|disease|illness|operation|surgery|in\s+this|under\s+this|\?|$))",
            r"(?:mention|state|talk\s+about)\s+(?:a\s+|an\s+)?([a-zA-Z\s]{3,28}?)(?:\s+(?:disease|illness|condition|treatment|\?|$))",
            r"(?:is|does\s+the\s+policy\s+cover)\s+([a-zA-Z\s]{3,28}?)(?:\s+covered|\?|$)"
        ]
        for pat in patterns:
            m = re.search(pat, lower)
            if m:
                extracted = m.group(1).strip()
                # filter out generic words
                if extracted not in ["this", "the", "any", "all", "what", "how", "policy", "my", "health"]:
                    return extracted
        return ""

    @classmethod
    def analyze(cls, question: str) -> Dict[str, Any]:
        text = question.strip()
        lower_q = text.lower()
        language = cls.detect_language(text)

        # 1. Identify Topic & Synonyms
        detected_topics = []
        synonym_additions = []

        for topic, terms in cls.TOPIC_SYNONYMS.items():
            for term in terms:
                if re.search(rf"\b{re.escape(term)}\b", lower_q):
                    detected_topics.append(topic)
                    synonym_additions.extend(terms[:4])
                    break

        specific_entity = cls.extract_specific_subject(text)
        is_unrecognized_specific = False

        if detected_topics:
            primary_topic = detected_topics[0]
        elif specific_entity:
            primary_topic = specific_entity.replace(" ", "_")
            is_unrecognized_specific = True
        else:
            primary_topic = "general_health_policy"

        # 2. Identify Intent & Required Categories
        is_comprehensive = bool(re.search(r"\b(?:list\s+all|all\s+exclusions|every|complete\s+list|all\s+waiting\s+periods|detailed\s+list)\b", lower_q))
        
        category_boosts = {
            "Coverage": 0.0,
            "Exclusion": 0.0,
            "Waiting Period": 0.0,
            "Condition": 0.0,
            "Claim Requirement": 0.0,
            "General": 0.0
        }

        # Intent Archetypes:
        if re.search(r"\b(?:is\s+.+\s+covered|does\s+(?:the\s+)?policy\s+cover|coverage\s+for|are\s+.+\s+covered|kya\s+.+\s+(?:cover|milta)\b|cover\s+hai\b)\b", lower_q):
            intent = "coverage_inquiry"
            required_categories = ["Coverage", "Waiting Period", "Exclusion", "Condition"]
            category_boosts["Coverage"] = 0.40
            category_boosts["Waiting Period"] = 0.25
            category_boosts["Exclusion"] = 0.25
            category_boosts["Condition"] = 0.10

        elif re.search(r"\b(?:waiting\s+period|how\s+long\s+to\s+wait|wait\s+time|cooling\s+period|kitna\s+wait|kab\s+milega)\b", lower_q):
            intent = "waiting_period_inquiry"
            required_categories = ["Waiting Period", "Condition"]
            category_boosts["Waiting Period"] = 0.70
            category_boosts["Condition"] = 0.30

        elif re.search(r"\b(?:exclusion|not\s+covered|what\s+is\s+excluded|exclusions?\s+related|nahi\s+milega|shamil\s+nahi)\b", lower_q):
            intent = "exclusion_inquiry"
            required_categories = ["Exclusion", "Condition"]
            category_boosts["Exclusion"] = 0.75
            category_boosts["Condition"] = 0.25

        elif re.search(r"\b(?:documents?\s+required|how\s+to\s+claim|claim\s+process|file\s+a\s+claim|reimbursement|cashless|claim\s+kaise)\b", lower_q):
            intent = "claim_inquiry"
            required_categories = ["Claim Requirement", "Condition"]
            category_boosts["Claim Requirement"] = 0.80
            category_boosts["Condition"] = 0.20

        elif re.search(r"\b(?:limit|sub-limit|cap|maximum\s+amount|co-pay|deductible|room\s+rent\s+limit|kitna\s+limit)\b", lower_q):
            intent = "limit_inquiry"
            required_categories = ["Condition", "Coverage"]
            category_boosts["Condition"] = 0.60
            category_boosts["Coverage"] = 0.40

        elif re.search(r"\b(?:conditions?\s+for\s+hospitalization|24\s+hours|admit|admission\s+rules?|hospitalization\s+criteria)\b", lower_q):
            intent = "hospitalization_conditions"
            required_categories = ["Coverage", "Condition"]
            category_boosts["Coverage"] = 0.60
            category_boosts["Condition"] = 0.40

        elif re.search(r"\b(?:what\s+does\s+(?:this\s+)?policy\s+cover|benefits\s+of\s+(?:this\s+)?policy|overall\s+coverage)\b", lower_q):
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

        unique_synonyms = list(dict.fromkeys(synonym_additions))
        expanded_query = f"{text} " + " ".join(unique_synonyms[:6]) if unique_synonyms else text

        return {
            "original_question": text,
            "expanded_query": expanded_query.strip(),
            "language": language,
            "topic": primary_topic,
            "specific_entity": specific_entity,
            "is_unrecognized_specific": is_unrecognized_specific,
            "all_topics": detected_topics,
            "intent": intent,
            "is_comprehensive": is_comprehensive,
            "required_categories": required_categories,
            "category_boosts": category_boosts
        }
