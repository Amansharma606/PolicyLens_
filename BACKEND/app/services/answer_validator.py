import re
from typing import Dict, Any, List
from app.core.logging import logger

class AnswerValidator:
    """
    Validates factual grounding, answer-evidence separation, and numerical consistency.
    """

    @classmethod
    def validate(
        cls,
        answer: str,
        citations: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        is_insufficient: bool = False
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
                "citations": []
            }

        # 1. Check whether answer is simply raw verbatim copy of evidence
        raw_evidence_texts = [c.get("text", "").strip() for c in citations if c.get("text")]
        is_verbatim = False
        for raw_t in raw_evidence_texts:
            if len(raw_t) > 60 and raw_t in answer:
                # The raw text is directly copy-pasted
                is_verbatim = True
                break

        # 2. Check numerical grounding
        # Extract numbers, currency amounts, percentages, and month/day durations from answer
        answer_quantities = re.findall(r"\b(?:\u20b9\s*[\d,]+|\d+\s*(?:months?|days?|years?|%|hours?))\b", answer, re.IGNORECASE)
        combined_evidence = " ".join(raw_evidence_texts).lower()

        unsupported_quantities = []
        for q in answer_quantities:
            norm_q = q.lower().strip()
            # Check if this exact quantity exists in the evidence
            if norm_q not in combined_evidence:
                # Check digits only
                digits = re.findall(r"\d+", norm_q)
                if digits and not any(d in combined_evidence for d in digits):
                    unsupported_quantities.append(q)

        if unsupported_quantities:
            logger.warning(f"Answer contains potentially ungrounded quantities not found in evidence: {unsupported_quantities}")

        return {
            "is_valid": True,
            "status": "answered",
            "is_verbatim": is_verbatim,
            "unsupported_quantities": unsupported_quantities
        }

    @classmethod
    def _generate_refusal(cls, analysis: Dict[str, Any]) -> str:
        topic_name = analysis.get("topic", "the queried topic").replace("_", " ").title()
        lang = analysis.get("language", "english")

        if lang in ["hindi", "hinglish"]:
            return (
                f"**Direct Answer:**\n"
                f"Main aapke uploaded policy document mein **{topic_name}** ke baare mein paryapt jaankari nahi dhoondh saka.\n\n"
                f"**Important Conditions & Limits:**\n"
                f"- Upload kiye gaye document ke kisi bhi section mein is vishay ka spasht ullekh nahi mila.\n"
                f"- Kripya apni policy schedule ya additional riders ki jaanch karein ki kya yah alag se cover kiya gaya hai."
            )

        return (
            f"**Direct Answer:**\n"
            f"I could not find sufficient information about **{topic_name}** in the uploaded policy document.\n\n"
            f"**Important Conditions & Limits:**\n"
            f"- The indexed sections of this policy do not explicitly state coverage, waiting periods, or limits for this queried item.\n"
            f"- Please refer to your specific Policy Schedule or optional rider endorsements to verify if additional coverage was opted for."
        )
