import re
from typing import Dict, Any, List
from app.core.logging import logger


class AnswerValidator:
    """
    Validates factual grounding, numerical consistency, response completeness,
    and natural bilingual out-of-document abstention.
    """

    INSUFFICIENT_PHRASES = (
        "does not contain information about",
        "does not mention details about",
        "does not mention",
        "not specified in policy",
        "not specified in this policy",
        "not mentioned in the uploaded policy",
        "no information found in the uploaded policy",
        "koi jaankari nahi",
        "जानकारी नहीं दी गई",
    )

    @classmethod
    def is_page_only_or_incomplete(cls, answer: str) -> bool:
        """
        Detects broken page-only outputs (e.g. 'The waiting period for *(Pages 3, 5, 21)*',
        'Refer to Page 4', 'found on Page 7', 'Nahi, yeh policy... *(Page 15)*') so they
        can NEVER reach the user.
        """
        if not answer or not answer.strip():
            return True
        low = answer.lower().strip()

        # Check explicit page-pointer stub phrases
        if re.search(
            r"\b(?:refer\s+to\s+page|see\s+page|found\s+on\s+page|documented\s+on\s+page|mentioned\s+on\s+page|available\s+on\s+page)\b",
            low,
        ):
            core_no_ptr = re.sub(r"\*?\(Pages?\s+[\d,\s&-]+\)\*?", "", answer, flags=re.IGNORECASE).strip()
            if len(re.findall(r"[a-zA-Z0-9\u0900-\u097F]{2,}", core_no_ptr)) < 12:
                return True

        # Strip inline page citations and inspect core answer prose
        core = re.sub(r"\*?\(Pages?\s+[\d,\s&-]+\)\*?", "", answer, flags=re.IGNORECASE)
        core = re.sub(r"\bPages?\s+\d+(?:[\s,&\-]+\d+)*", "", core, flags=re.IGNORECASE).strip()

        # Check ellipsis fragmentation like "Nahi, yeh policy..."
        if "..." in core or core.rstrip().endswith(".."):
            return True

        words = re.findall(r"[a-zA-Z0-9\u0900-\u097F]{2,}", core)
        if len(words) < 6 or len(core) < 28:
            return True

        # Check dangling sentence cutoffs ending on a preposition/article
        last_word = words[-1].lower()
        if last_word in {"for", "of", "to", "in", "by", "with", "the", "a", "an", "and", "or", "is", "are", "from", "under"} and not core.rstrip().endswith("."):
            return True

        return False

    @classmethod
    def validate(
        cls,
        answer: str,
        citations: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        is_insufficient: bool = False,
    ) -> Dict[str, Any]:
        """
        Validates generated answer against retrieved citations.
        Returns validated result with status: 'answered' or 'insufficient_evidence'.
        """
        if is_insufficient or not citations:
            return {
                "is_valid": True,
                "status": "insufficient_evidence",
                "answer": cls._generate_refusal(analysis),
                "citations": [],
            }

        ans_lower = (answer or "").lower()
        # Only reclassify LLM reply as insufficient_evidence when it genuinely refuses due to absent topic
        if any(
            phrase in ans_lower
            for phrase in ("does not contain information about", "does not mention details about", "koi jaankari nahi", "जानकारी नहीं दी गई")
        ):
            if not re.search(r"\b(?:yes\b|haan\b|no\b|nahi\b|covered|excluded|hospitali[sz]ation|accident)\b", ans_lower):
                return {
                    "is_valid": True,
                    "status": "insufficient_evidence",
                    "answer": answer.strip(),
                    "citations": [],
                }

        raw_evidence_texts = [c.get("text", "").strip() for c in citations if c.get("text")]

        # Numerical grounding sanity check
        answer_quantities = re.findall(
            r"(?:₹|rs\.?|inr)\s*[\d,]+|\b\d+(?:\.\d+)?\s*(?:months?|days?|years?|%|hours?)\b",
            answer,
            re.IGNORECASE,
        )
        combined_evidence = " ".join(raw_evidence_texts).lower()
        combined_digits_flat = re.sub(r",", "", combined_evidence)

        unsupported_quantities = []
        for q in answer_quantities:
            norm_q = q.lower().strip()
            digits = re.findall(r"\d+", norm_q.replace(",", ""))
            if not digits:
                continue
            full_num = "".join(digits)
            if norm_q not in combined_evidence and full_num not in combined_digits_flat:
                if not any(f"page {d}" in ans_lower or f"clause {d}" in ans_lower for d in digits):
                    unsupported_quantities.append(q)

        if unsupported_quantities:
            logger.warning(f"Answer contains quantities not verbatim in top citations: {unsupported_quantities}")

        return {
            "is_valid": True,
            "status": "answered",
            "unsupported_quantities": unsupported_quantities,
        }

    @classmethod
    def _generate_refusal(cls, analysis: Dict[str, Any]) -> str:
        specific = (analysis.get("specific_entity") or "").strip()
        raw_topic = (analysis.get("topic") or "").replace("_", " ").strip()
        if specific:
            topic_name = specific
        elif raw_topic and raw_topic not in ("general health policy", "general policy", "general"):
            topic_name = raw_topic
        else:
            topic_name = (analysis.get("original_question") or "this topic").strip().rstrip("?.!")

        lang = analysis.get("language", "english")

        if lang == "hindi":
            return (
                f"इस पॉलिसी PDF में **{topic_name}** के बारे में कोई जानकारी नहीं दी गई है।\n\n"
                f"पॉलिसी लेंस केवल अपलोड किए गए दस्तावेज़ में मौजूद शर्तों, लाभों और सीमाओं के आधार पर उत्तर देता है। "
                f"कृपया इस विषय की पुष्टि के लिए अपने पॉलिसी शेड्यूल या किसी राइडर दस्तावेज़ की जांच करें।"
            )
        if lang == "hinglish":
            return (
                f"Is policy PDF mein **{topic_name}** ke baare mein koi jaankari nahi di gayi hai.\n\n"
                f"PolicyLens sirf aapki upload ki gayi PDF mein likhe rules, coverage aur limits ke aadhar par jawab deta hai. "
                f"Is topic ko verify karne ke liye apna Policy Schedule ya rider document check karein."
            )

        return (
            f"This uploaded policy PDF does not mention details about **{topic_name}**.\n\n"
            f"PolicyLens answers strictly using clauses written inside your uploaded document without adding external assumptions. "
            f"Please check your Policy Schedule or any separate rider endorsement to verify whether this item is covered."
        )
