import re
from typing import Dict, Any, List

class QuestionAnalyzer:
    """
    Analyzes user queries to determine topic, intent, required policy categories,
    and retrieval strategy.
    """

    TOPIC_PATTERNS = {
        "maternity": [r"\bmaternity\b", r"\bpregnancy\b", r"\bchildbirth\b", r"\bnewborn\b", r"\bdelivery\b", r"\bcesarean\b"],
        "cataract": [r"\bcataract\b", r"\beye\s+surgery\b", r"\blens\b"],
        "pre_existing_disease": [r"\bpre-existing\b", r"\bped\b", r"\bexisting\s+disease\b", r"\bchronic\b", r"\bdiabetes\b", r"\bhypertension\b"],
        "room_rent": [r"\broom\s+rent\b", r"\bicu\b", r"\bsuite\b", r"\bhospital\s+room\b"],
        "waiting_period": [r"\bwaiting\s+period\b", r"\bhow\s+long\s+(?:to|before)\s+cover\b", r"\binitial\s+wait\b", r"\bgrace\s+period\b"],
        "exclusions": [r"\bexclusion(?:s)?\b", r"\bnot\s+covered\b", r"\bwhat\s+is\s+excluded\b", r"\bpermanent\s+exclusion\b"],
        "claim_procedure": [r"\bclaim\b", r"\breimburse\b", r"\bcashless\b", r"\bdocuments?\s+required\b", r"\btpa\b", r"\bintimation\b", r"\bfile\s+a\s+claim\b"],
        "ayush": [r"\bayush\b", r"\bayurveda\b", r"\bhomeopathy\b", r"\bunani\b", r"\bsiddha\b"],
        "day_care": [r"\bday\s+care\b", r"\bdialysis\b", r"\bchemotherapy\b", r"\bradiotherapy\b"],
        "donor_expenses": [r"\borgan\s+donor\b", r"\bdonor\b", r"\btransplant\b"],
        "ambulance": [r"\bambulance\b", r"\broad\s+ambulance\b", r"\bair\s+ambulance\b"],
        "restore_benefit": [r"\brestore\b", r"\brestoration\b", r"\brecharge\b", r"\bcumulative\s+bonus\b"],
        "sub_limits": [r"\bsub-limit\b", r"\bfinancial\s+limit\b", r"\bmaximum\s+cap\b", r"\bco-pay\b", r"\bdeductible\b"],
        "eligibility": [r"\beligibility\b", r"\bage\s+limit\b", r"\bentry\s+age\b", r"\bdependents?\b", r"\bwho\s+can\s+be\s+covered\b"]
    }

    @classmethod
    def analyze(cls, question: str) -> Dict[str, Any]:
        text = question.strip()
        lower_q = text.lower()

        # 1. Identify Topic
        detected_topics = []
        for topic, patterns in cls.TOPIC_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, lower_q):
                    detected_topics.append(topic)
                    break

        primary_topic = detected_topics[0] if detected_topics else "general_health_policy"

        # 2. Identify Intent & Required Categories
        is_comprehensive = bool(re.search(r"\b(?:list\s+all|all\s+exclusions|every|complete\s+list|detailed)\b", lower_q))
        
        required_categories = []
        category_boosts = {
            "Coverage": 0.0,
            "Exclusion": 0.0,
            "Waiting Period": 0.0,
            "Condition": 0.0,
            "Claim Requirement": 0.0,
            "General": 0.0
        }

        # Check for specific intent archetypes:
        if re.search(r"\b(?:is\s+.+\s+covered|does\s+(?:the\s+)?policy\s+cover|coverage\s+for|are\s+.+\s+covered)\b", lower_q):
            intent = "coverage_inquiry"
            # For "Is X covered?": Must inspect Coverage, Waiting Period, Exclusion, and relevant Conditions!
            required_categories = ["Coverage", "Waiting Period", "Exclusion", "Condition"]
            category_boosts["Coverage"] = 0.35
            category_boosts["Waiting Period"] = 0.25
            category_boosts["Exclusion"] = 0.25
            category_boosts["Condition"] = 0.15

        elif re.search(r"\b(?:waiting\s+period|how\s+long\s+to\s+wait|wait\s+time|cooling\s+period)\b", lower_q):
            intent = "waiting_period_inquiry"
            required_categories = ["Waiting Period", "Condition"]
            category_boosts["Waiting Period"] = 0.70
            category_boosts["Condition"] = 0.30

        elif re.search(r"\b(?:exclusion|not\s+covered|what\s+is\s+excluded|exclusions?\s+related)\b", lower_q):
            intent = "exclusion_inquiry"
            required_categories = ["Exclusion", "Condition"]
            category_boosts["Exclusion"] = 0.75
            category_boosts["Condition"] = 0.25

        elif re.search(r"\b(?:documents?\s+required|how\s+to\s+claim|claim\s+process|file\s+a\s+claim|reimbursement|cashless)\b", lower_q):
            intent = "claim_inquiry"
            required_categories = ["Claim Requirement", "Condition"]
            category_boosts["Claim Requirement"] = 0.80
            category_boosts["Condition"] = 0.20

        elif re.search(r"\b(?:limit|sub-limit|cap|maximum\s+amount|co-pay|deductible)\b", lower_q):
            intent = "limit_inquiry"
            required_categories = ["Condition", "Coverage"]
            category_boosts["Condition"] = 0.60
            category_boosts["Coverage"] = 0.40

        else:
            intent = "general_qa"
            required_categories = ["Coverage", "Condition", "General"]
            category_boosts["Coverage"] = 0.40
            category_boosts["Condition"] = 0.30
            category_boosts["General"] = 0.30

        return {
            "original_question": text,
            "topic": primary_topic,
            "all_topics": detected_topics,
            "intent": intent,
            "is_comprehensive": is_comprehensive,
            "required_categories": required_categories,
            "category_boosts": category_boosts
        }
