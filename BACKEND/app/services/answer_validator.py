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

        if lang == "hindi":
            return (
                f"### Direct Answer\n"
                f"अपलोड किए गए पॉलिसी दस्तावेज़ में **{topic_name}** के संबंध में पर्याप्त जानकारी नहीं मिली।\n\n"
                f"### Simple Explanation\n"
                f"इस पॉलिसी के अनुक्रमित अनुभागों में इस विशिष्ट बीमारी, इलाज या नियम का स्पष्ट उल्लेख नहीं है।\n\n"
                f"### Important Conditions\n"
                f"- पॉलिसी के मुख्य नियमों में इस विषय पर कोई स्पष्ट कवरेज या प्रतीक्षा अवधि दर्ज नहीं है।\n"
                f"- कृपया अपने पॉलिसी शेड्यूल या अतिरिक्त राइडर की जांच करें कि क्या यह अलग से शामिल है।\n\n"
                f"### Evidence from Your Policy\n"
                f"इस विषय से संबंधित कोई प्रमाणित खंड (clause) अपलोड किए गए दस्तावेज़ में नहीं पाया गया।"
            )
        elif lang == "hinglish":
            return (
                f"### Direct Answer\n"
                f"Main aapke uploaded policy document mein **{topic_name}** ke baare mein paryapt jaankari nahi dhoondh saka.\n\n"
                f"### Simple Explanation\n"
                f"Is policy ke indexed sections mein is vishay ka spasht ullekh nahi mila, isliye bina pramaan ke iski pushti nahi ki ja sakti.\n\n"
                f"### Important Conditions\n"
                f"- Upload kiye gaye document mein is vishay par koi nirdharit coverage ya waiting period darj nahi hai.\n"
                f"- Kripya apni policy schedule ya additional riders ki jaanch karein ki kya yah alag se cover kiya gaya hai.\n\n"
                f"### Evidence from Your Policy\n"
                f"Is vishay se sambandhit koi clause ya pramaan active policy document mein nahi mila."
            )

        return (
            f"### Direct Answer\n"
            f"I could not find sufficient information about **{topic_name}** in the uploaded policy document.\n\n"
            f"### Simple Explanation\n"
            f"The uploaded policy text does not explicitly outline provisions, waiting periods, or benefit calculations for this specific inquiry.\n\n"
            f"### Important Conditions\n"
            f"- The indexed sections do not provide sufficient evidentiary ground to confirm or deny coverage for this term.\n"
            f"- Please refer to your specific Policy Schedule or optional rider endorsements to verify whether additional coverage applies.\n\n"
            f"### Evidence from Your Policy\n"
            f"No supporting clauses or specific terms matching this inquiry were identified in the active document."
        )
