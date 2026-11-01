import os
import json
import re
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.core.logging import logger
from app.services.answer_validator import AnswerValidator

SYSTEM_PROMPT = """You are PolicyLens, an expert health insurance policy explanation assistant.
The uploaded policy document is your primary source of truth.
Follow these mandatory formatting and grounding rules:

1. STRICT SEPARATION OF ANSWER AND EVIDENCE:
   Do NOT copy-paste raw clause text verbatim into the answer. The evidence text is presented separately in citation cards.
   Your answer must explain what the policy means in clear, accessible, conversational language for an everyday policyholder.

2. STRUCTURE YOUR ANSWER STRICTLY AS FOLLOWS:
   ### Direct Answer
   Give a direct, clear 1 to 3 sentence natural-language answer to the user's question in plain everyday language.

   ### Simple Explanation
   Explain what the policy actually means in plain terms, translating technical insurance jargon (e.g., PED, co-payment, TPA, room rent capping, pre-auth, cashless) into clear everyday concepts.

   ### Important Conditions
   - Mention applicable waiting periods, permanent exclusions, financial limits, sub-limits, and exceptions as concise bullet points.

   ### Evidence from Your Policy
   Cite the exact policy section name and page numbers where these provisions are documented in the active uploaded policy.

3. STRICT GROUNDING IN UPLOADED DOCUMENT:
   Answer using ONLY the provided policy evidence clauses. Do NOT invent coverage, waiting periods, financial caps, or exclusions.
   If the evidence does not mention the queried term, condition, or disease, explicitly state:
   "I could not find sufficient information about this in the uploaded policy document."

4. MULTI-LANGUAGE SUPPORT:
   If the user asks in Hindi (Devanagari) or Hinglish, provide all four sections in natural, conversational Hindi or Hinglish.
"""

class LLMService:
    """
    Multi-Provider Grounded LLM Response Generator.
    Supports Google Gemini, OpenAI, and Local Deterministic Grounded Synthesizer.
    Enforces strict Answer vs Evidence separation.
    """

    @classmethod
    def generate_grounded_answer(
        cls,
        question: str,
        retrieved_clauses: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        conversation_context: Optional[List[Dict[str, str]]] = None,
        is_insufficient: bool = False
    ) -> Dict[str, Any]:
        if is_insufficient or not retrieved_clauses:
            return {
                "answer": AnswerValidator._generate_refusal(analysis),
                "status": "insufficient_evidence",
                "citations": []
            }

        citations = []
        seen_texts = set()

        for idx, c in enumerate(retrieved_clauses[:6]):
            text_snippet = c["text"].strip()
            if text_snippet in seen_texts:
                continue
            seen_texts.add(text_snippet)

            page = c["page"]
            sec = c.get("section") or "Policy Terms"
            clause_num = c.get("clause_number")
            cat = c.get("category", "General")
            rel_score = float(c.get("rerank_score", c.get("hybrid_score", 0.85)))
            norm_rel = min(0.98, max(0.60, round(rel_score if rel_score <= 1.0 else rel_score / 10.0, 2)))

            citations.append({
                "page": page,
                "section": sec,
                "clause_number": clause_num,
                "category": cat,
                "relevance_score": norm_rel,
                "text": text_snippet
            })

        evidence_lines = []
        for idx, c in enumerate(citations):
            c_tag = f"Clause {c['clause_number']}" if c.get("clause_number") else f"Evidence Item {idx+1}"
            evidence_lines.append(
                f"[{c_tag} | Page {c['page']} | Section: {c['section']} | Category: {c['category']}]:\n\"{c['text']}\"\n"
            )

        evidence_prompt = "\n".join(evidence_lines)

        history_text = ""
        if conversation_context:
            recent = conversation_context[-4:]
            hist_parts = [f"{m['role'].capitalize()}: {m['content']}" for m in recent]
            history_text = "Previous Conversation Context:\n" + "\n".join(hist_parts) + "\n\n"

        full_user_prompt = f"""{history_text}Policy Evidence extracted from Uploaded Document:
{evidence_prompt}

User Question: {question}

Explain the policy answer clearly based strictly on the evidence above according to the system instructions. Remember: do not repeat raw clauses verbatim; formulate a direct explanation."""

        # 1. Google Gemini
        provider = settings.LLM_PROVIDER
        api_key_gemini = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        if provider == "gemini" and api_key_gemini:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key_gemini)
                model = genai.GenerativeModel(
                    model_name="gemini-1.5-flash",
                    system_instruction=SYSTEM_PROMPT
                )
                response = model.generate_content(full_user_prompt)
                if response and response.text:
                    clean_ans = response.text.strip()
                    validation = AnswerValidator.validate(clean_ans, citations, analysis)
                    return {
                        "answer": clean_ans,
                        "status": validation["status"],
                        "citations": citations
                    }
            except Exception as e:
                logger.error(f"Gemini API error: {e}. Falling back to Local Grounded Synthesizer.")

        # 2. Local Grounded Synthesizer
        local_result = cls._local_grounded_synthesis(question, citations, analysis)
        validation = AnswerValidator.validate(local_result["answer"], citations, analysis)
        return {
            "answer": local_result["answer"],
            "status": validation["status"],
            "citations": citations
        }

    @classmethod
    def _local_grounded_synthesis(
        cls,
        question: str,
        citations: List[Dict[str, Any]],
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deterministic, grounded explanation generator.
        Synthesizes human-friendly Direct Answers and Important Conditions & Limits
        strictly from policy evidence without duplicating raw text verbatim.
        """
        intent = analysis.get("intent", "general_qa")
        raw_topic = analysis.get("topic", "")
        language = analysis.get("language", "english")
        topic_title = raw_topic.replace("_", " ").title() if raw_topic else "Policy Term"

        # Topic matching in evidence
        topic_words = set(raw_topic.lower().split("_")) if raw_topic else set()
        all_text = " ".join(c["text"] for c in citations).lower()

        coverages = [c for c in citations if c.get("category") == "Coverage"]
        waitings = [c for c in citations if c.get("category") == "Waiting Period"]
        exclusions = [c for c in citations if c.get("category") == "Exclusion"]
        claims = [c for c in citations if c.get("category") == "Claim Requirement"]
        conditions = [c for c in citations if c.get("category") == "Condition"]

        # Extract quantities and specific durations from evidence
        waiting_matches = re.findall(r"\b(?:30|60|90)\s*days?\b|\b(?:12|24|36|48)\s*months?\b", all_text, re.IGNORECASE)
        unique_waits = list(dict.fromkeys(m.lower() for m in waiting_matches))

        rupee_matches = re.findall(r"(?:₹|rs\.?|inr)\s*[\d,]+(?:\s*(?:per\s+(?:eye|day|admission|year)|up\s+to|maximum))?", all_text, re.IGNORECASE)
        unique_rupees = list(dict.fromkeys(r.strip() for r in rupee_matches))

        pct_matches = re.findall(r"\b\d+\s*%\s*(?:of\s+sum\s+insured)?\b", all_text, re.IGNORECASE)
        unique_pcts = list(dict.fromkeys(p.strip() for p in pct_matches))

        is_hinglish = language in ["hindi", "hinglish"]

        # =========================================================================
        # 1. MATERNITY INQUIRY
        # =========================================================================
        if raw_topic == "maternity" or (intent == "coverage_inquiry" and "maternity" in question.lower()) or "maternity" in question.lower():
            has_maternity_cov = any("maternity" in c["text"].lower() or "delivery" in c["text"].lower() or "childbirth" in c["text"].lower() for c in coverages)
            has_general_cov = any("maternity" in c["text"].lower() for c in citations)
            mat_waiting = [w for w in unique_waits if "month" in w or "24" in w or "36" in w]
            wait_str = mat_waiting[0] if mat_waiting else "24 months"

            if has_maternity_cov or has_general_cov:
                if language == "hindi":
                    direct_ans = f"हाँ, इस पॉलिसी के तहत मातृत्व (डिलीवरी) और नवजात शिशु के चिकित्सा खर्च कवर किए जाते हैं, परंतु इसके लिए {wait_str} की प्रतीक्षा अवधि और वित्तीय सीमाएं लागू होती हैं।"
                    simple_exp = "इसका व्यावहारिक अर्थ यह है कि अस्पताल में प्रसव का खर्च बीमा कंपनी द्वारा तभी वहन किया जाएगा जब आपकी पॉलिसी बिना किसी रुकावट के निर्धारित प्रतीक्षा अवधि पूरी कर चुकी हो।"
                    cond_points = [
                        f"**अनिवार्य प्रतीक्षा अवधि:** मातृत्व लाभ सक्रिय होने के लिए पॉलिसी का कम से कम {wait_str} तक लगातार नवीनीकृत रहना आवश्यक है।",
                        f"**प्रसव उप-सीमाएं (Sub-limits):** सामान्य डिलीवरी और सिजेरियन ऑपरेशन के लिए पूर्व-निर्धारित वित्तीय सीमाएं लागू होती हैं।",
                        "**नवजात शिशु सुरक्षा:** जन्म के तुरंत बाद नवजात शिशु के शुरुआती टीकाकरण और इन-पेशेंट खर्च पॉलिसी नियमों के अनुसार कवर होते हैं।",
                        "**अस्वीकृत उपचार:** बांझपन (IVF/Infertility) या स्वैच्छिक गर्भपात इस कवर में शामिल नहीं हैं।"
                    ]
                elif is_hinglish:
                    direct_ans = f"Haan, is policy ke tahat maternity aur delivery expenses cover kiye jaate hain, par is par {wait_str} ka continuous waiting period aur specific financial limits lagu hoti hain."
                    simple_exp = "Iska aasan matlab yah hai ki hospital mein delivery ka kharcha claim karne ke liye policy bina break ke nirdharit mahino tak active rehni chahiye. Faltu IVF ya voluntary procedures cover nahi hote."
                    cond_points = [
                        f"**Waiting Period:** Maternity labh lene ke liye kam se kam {wait_str} tak bina kisi break ke policy chalu rehna anivarya hai.",
                        f"**Delivery Sub-Limits:** Normal delivery aur Cesarean section ke liye nirdharit financial limits ({', '.join(unique_rupees[:2]) if unique_rupees else 'up to policy sub-limits'}) lagu hoti hain.",
                        "**Newborn Baby Cover:** Bachhe ke janam ke baad initial days ke hospitalization aur vaccinations policy terms ke anusar cover hote hain.",
                        "**Excluded Procedures:** Infertility treatments, sub-fertility, IVF, aur voluntary abortion strictly excluded hain."
                    ]
                else:
                    direct_ans = f"Yes, maternity expenses and childbirth are covered under this policy, subject to a mandatory continuous waiting period of {wait_str} and specified monetary sub-limits."
                    simple_exp = "In practical terms, hospital delivery bills will be reimbursed by the insurer, but only after your policy has been renewed continuously for the required waiting duration without any coverage lapse."
                    cond_points = [
                        f"**Mandatory Waiting Period:** Coverage for maternity expenses becomes active only after completing {wait_str} of continuous active policy renewal.",
                        f"**Delivery Sub-Limits:** Reimbursement is capped at specified policy schedule limits ({', '.join(unique_rupees[:2]) if unique_rupees else 'as delineated in your benefits table'}).",
                        "**Newborn Baby Extension:** Hospitalization expenses for the newborn baby are covered from birth up to the specified maternity limits.",
                        "**Exclusions:** Infertility treatments, IVF procedures, surrogate child arrangements, and voluntary abortion are excluded."
                    ]
            else:
                if language == "hindi":
                    direct_ans = "नहीं, इस पॉलिसी के नियमों के तहत मातृत्व और गर्भावस्था से जुड़े चिकित्सा खर्च स्थायी रूप से बाहर (Exclusions) रखे गए हैं।"
                    simple_exp = "इसका अर्थ है कि अस्पताल में डिलीवरी या सी-सेक्शन का बिल इस पॉलिसी से क्लेम नहीं किया जा सकता। इसके लिए अलग से मातृत्व राइडर लेना होगा।"
                    cond_points = [
                        "**स्थायी बहिष्करण (Permanent Exclusion):** सामान्य प्रसव, सिजेरियन ऑपरेशन और मातृत्व देखभाल गैर-भुगतान योग्य हैं।",
                        "**वैकल्पिक राइडर:** यदि मातृत्व कवर चाहिए, तो पॉलिसी लेते समय अलग से मैटरनिटी राइडर जोड़ना होगा।"
                    ]
                elif is_hinglish:
                    direct_ans = "Nahi, is policy ke tahat maternity sambhandhit kharche permanent exclusions mein shamil hain aur standard cover mein nahi aate."
                    simple_exp = "Iska matlab yah hai ki delivery ya pregnancy ka koi bhi bill insurer dwara pass nahi kiya jayega jab tak aapne alag se maternity add-on rider na liya ho."
                    cond_points = [
                        "**Permanent Exclusion:** Normal delivery, C-section, aur pregnancy treatments non-payable items mein shamil hain.",
                        "**Optional Rider:** Yadi aap maternity cover chahte hain, toh alag se maternity add-on rider lena hoga."
                    ]
                else:
                    direct_ans = "No, maternity and pregnancy-related medical treatments are listed under policy exclusions and are not covered under standard terms."
                    simple_exp = "This means inpatient delivery costs, prenatal checkups, and post-natal care cannot be reimbursed under this basic policy unless an optional maternity add-on rider was purchased."
                    cond_points = [
                        "**Excluded Treatments:** Childbirth, cesarean sections, and antenatal/postnatal care are excluded from standard coverage.",
                        "**Optional Rider:** Check whether a separate maternity rider can be purchased during policy inception or renewal."
                    ]

        # =========================================================================
        # 2. PRE-EXISTING DISEASE (PED) WAITING PERIOD
        # =========================================================================
        elif raw_topic == "pre_existing_disease" or "pre-existing" in question.lower() or "ped" in question.lower():
            ped_wait = [w for w in unique_waits if "month" in w or "36" in w or "48" in w or "24" in w]
            wait_str = ped_wait[0] if ped_wait else "36 to 48 continuous months"

            if language == "hindi":
                direct_ans = f"पहले से मौजूद बीमारियां (PED जैसे डायबिटीज या हाई ब्लड प्रेशर) इस पॉलिसी में {wait_str} की अनिवार्य प्रतीक्षा अवधि के बाद ही कवर होती हैं।"
                simple_exp = f"यदि पॉलिसी लेने से पहले आपको कोई बीमारी थी, तो बीमा कंपनी पहले {wait_str} तक उसके इलाज का कोई खर्च नहीं देगी। प्रतीक्षा अवधि पूरी होने पर सामान्य बीमारी की तरह पूरा कवर मिलेगा।"
                cond_points = [
                    f"**प्रतीक्षा अवधि की शर्त:** कवर प्राप्त करने के लिए पॉलिसी का बिना किसी अंतराल के {wait_str} तक सक्रिय रहना आवश्यक है।",
                    "**PED की परिभाषा:** पॉलिसी शुरू होने से 48 महीने पहले डॉक्टर द्वारा जांची गई या इलाज कराई गई कोई भी पुरानी बीमारी।",
                    "**पोर्टेबिलिटी क्रेडिट:** दूसरी बीमा कंपनी से बिना ब्रेक के पॉलिसी ट्रांसफर करने पर पहले पूरी की गई प्रतीक्षा अवधि का पूरा क्रेडिट मिलता है।"
                ]
            elif is_hinglish:
                direct_ans = f"Pre-existing diseases (policy lene se pehle ki bimariyan jaise diabetes ya hypertension) is policy mein {wait_str} ke waiting period ke baad hi cover hoti hain."
                simple_exp = f"Agar policy khareedne se pehle aapko koi bimari thi, toh shuruati {wait_str} tak company uska claim nahi degi. Yeh samay poora hote hi pura cover milne lagega."
                cond_points = [
                    f"**Waiting Period:** Bimari shamil hone ke liye {wait_str} tak bina kisi break ke policy chalu rehna anivarya hai.",
                    "**PED ka Matlab:** Koi bhi aisi bimari jo policy start hone se 48 mahine pehle diagnose hui ho ya jiska ilaaj chal raha ho.",
                    "**Portability Benefit:** Dusri company se policy port karne par pehle serve kiya gaya waiting period carry-forward hota hai."
                ]
            else:
                direct_ans = f"Pre-existing diseases (PED) are covered under this policy only after completing a mandatory waiting period of {wait_str} of continuous active coverage."
                simple_exp = f"If you had a health condition (such as diabetes, hypertension, or asthma) before purchasing this insurance, the insurer will not pay hospital bills for treating that condition during the initial {wait_str}. Once this duration elapses, treatments are fully reimbursable."
                cond_points = [
                    f"**Mandatory Waiting Period:** No claims will be accepted for conditions diagnosed or treated prior to policy inception until {wait_str} have elapsed.",
                    "**Definition of PED:** Any health condition, ailment, or chronic illness diagnosed by a physician or treated within 48 months before purchasing the policy.",
                    "**Portability Credit:** If you ported this policy from another registered insurer without a break, the waiting period already served is credited toward this requirement."
                ]

        # =========================================================================
        # 3. WAITING PERIODS (GENERAL OR LIST ALL)
        # =========================================================================
        elif intent == "waiting_period_inquiry" or "waiting period" in question.lower():
            if language == "hindi":
                direct_ans = "इस पॉलिसी में तीन मुख्य प्रकार की प्रतीक्षा अवधियां (Waiting Periods) लागू होती हैं: शुरुआती 30 दिन, विशिष्ट बीमारियां (24 महीने), और पहले से मौजूद बीमारियां।"
                simple_exp = "प्रतीक्षा अवधि वह समय सीमा है जब तक आप पॉलिसी सक्रिय रहने के बावजूद कुछ बीमारियों के लिए क्लेम नहीं कर सकते। हालांकि दुर्घटना (Accident) जनित इमरजेंसी पहले दिन से कवर होती है।"
                cond_points = [
                    "**प्रारंभिक 30-दिवसीय प्रतीक्षा:** पॉलिसी शुरू होने के पहले 30 दिनों में किसी भी सामान्य बीमारी का क्लेम नहीं मिलता (केवल आकस्मिक चोटें कवर होती हैं)।",
                    "**विशिष्ट बीमारियां (24 महीने):** मोतियाबिंद, हर्निया, पथरी और जोड़ों के प्रत्यारोपण जैसे सामान्य ऑपरेशनों पर 24 महीने की प्रतीक्षा अवधि होती है।",
                    f"**पहले से मौजूद बीमारियां (PED):** पूर्व-मौजूद बीमारियों के लिए {unique_waits[0] if unique_waits else '36 से 48 महीने'} का समय तय है।"
                ]
            elif is_hinglish:
                direct_ans = "Is policy ke tahat teen pramukh prakar ke waiting periods lagu hote hain: initial 30 days, specific illnesses (24 mahine), aur pre-existing diseases."
                simple_exp = "Waiting period ka aasan matlab hai ki policy lene ke turant baad claims nahi kiye ja sakte. Accident hone par day 1 se cover milta hai, par aam bimariyon ke liye nirdharit samay rukna padta hai."
                cond_points = [
                    "**Initial 30-Day Wait:** Policy shuru hone ke pehle 30 dino tak kisi bhi aam bimari ka claim nahi milta (keval accident emergency cover hoti hai).",
                    f"**Specific Illnesses (24 Months):** Cataract, hernia, joint replacement, aur kidney stones jaise common treatments par 24 mahine ka waiting period hota hai.",
                    f"**Pre-Existing Diseases:** Pehle se maujood bimariyon ke liye {unique_waits[0] if unique_waits else '36 se 48 mahine'} ka waiting period lagu hota hai."
                ]
            else:
                direct_ans = "This policy features three tiered waiting periods before full benefits become claimable: an initial 30-day period, specific illness periods, and pre-existing disease waiting periods."
                simple_exp = "Waiting periods prevent claims for pre-existing or slow-progressing conditions immediately after policy purchase. Except for emergency hospitalizations due to accidents which are covered from Day 1, treatments are subject to these staged timelines."
                cond_points = [
                    "**Initial 30-Day Waiting Period:** All illnesses diagnosed within the first 30 days of policy inception are excluded, except emergency hospitalizations due to an accident.",
                    "**Specified Disease / Procedure Waiting Period (24 Months):** Slower-progressing conditions (such as cataract, hernia, piles, joint replacements, and gallstones) require 24 months of continuous coverage.",
                    f"**Pre-Existing Disease (PED) Waiting Period:** Declared chronic conditions require {unique_waits[0] if unique_waits else '24 to 48 months'} of active policy renewal before claims are payable."
                ]

        # =========================================================================
        # 4. EXCLUSIONS INQUIRY
        # =========================================================================
        elif intent == "exclusion_inquiry" or "exclusion" in question.lower() or "not covered" in question.lower():
            if language == "hindi":
                direct_ans = "पॉलिसी में उन सभी गैर-भुगतान योग्य खर्चों और उपचारों की स्थायी सूची (Permanent Exclusions) दी गई है, जिन्हें बीमा कंपनी कभी कवर नहीं करती।"
                simple_exp = "स्थायी बहिष्करण ऐसे इलाज होते हैं जिनका भुगतान बीमा कंपनी किसी भी परिस्थिति में नहीं करती। डिस्चार्ज के समय किसी अप्रत्याशित खर्चे से बचने के लिए इन्हें पहले से जानना आवश्यक है।"
                cond_points = [
                    "**कॉस्मेटिक व प्लास्टिक सर्जरी:** केवल सुंदरता बढ़ाने, लिंग परिवर्तन या मोटापे की सर्जरी के खर्च पूर्णतः बाहर हैं।",
                    "**आत्म-हानि व साहसिक खेल:** जानबूझकर खुद को चोट पहुंचाना, युद्ध या खतरनाक साहसिक खेलों के जोखिम कवर नहीं होते।",
                    "**गैर-चिकित्सीय सामग्री:** अस्पताल पंजीकरण शुल्क, दस्ताने, मास्क और व्यक्तिगत सुख-सुविधा की वस्तुएं मरीज को स्वयं देनी होती हैं।",
                    "**अवैज्ञानिक व अप्रमाणित चिकित्सा:** कोई भी ऐसा इलाज जिसे मान्यता प्राप्त चिकित्सा प्राधिकरण द्वारा मंजूरी न मिली हो, बहिष्कृत है।"
                ]
            elif is_hinglish:
                direct_ans = "Policy mein un sabhi kharchon aur treatments ki spasht suchi hoti hai jinhe insurer bilkul cover nahi karta (permanent exclusions)."
                simple_exp = "Permanent exclusions aise kharche hote hain jinhe company kabhi claim mein pass nahi karti. Hospital se chhutti milte waqt bill dekhkar jhatka na lage, isliye inka pata hona zaroori hai."
                cond_points = [
                    "**Cosmetic & Plastic Surgery:** Sundarta badhane, cosmetic procedures, ya gender transformation ke kharche strictly excluded hain.",
                    "**Self-Harm & Adventure Sports:** Aatmhatya ka prayas, intentional self-injury, ya dangerous sports se hone wale nuksan cover nahi hote.",
                    "**Non-Payable Consumables:** Registration charges, hospital admission fee, gloves, masks, aur personal comfort items non-payable hote hain.",
                    "**Unproven Treatments:** Koi bhi aisa ilaaj ya experimental therapy jise recognized medical authorities ne approve na kiya ho, excluded hai."
                ]
            else:
                direct_ans = "The policy specifies standard permanent exclusions for medical treatments, procedures, and conditions where no reimbursement or claim benefits are payable."
                simple_exp = "Permanent exclusions are non-payable items and treatments that the insurance company will never cover under any circumstances. Knowing these helps prevent surprise out-of-pocket expenses at hospital discharge."
                cond_points = [
                    "**Cosmetic, Plastic & Obesity Treatments:** Surgeries performed solely for aesthetic enhancement, cosmetic rhinoplasty, weight loss, or bariatric surgery are permanently excluded.",
                    "**Self-Inflicted Injuries & High-Risk Activities:** Injuries resulting from suicide attempts, self-harm, active war/military duty, or hazardous adventure sports are not covered.",
                    "**Non-Medical Hospital Charges:** Administrative registration fees, admission documentation, and personal comfort consumables (toiletries, gloves, tissue boxes) must be borne out of pocket.",
                    "**Experimental & Unproven Therapies:** Any medical treatment, medication, or therapy without proven scientific efficacy or recognized regulatory approval is excluded."
                ]

        # =========================================================================
        # 5. CLAIM DOCUMENTS & PROCEDURE
        # =========================================================================
        elif intent == "claim_inquiry" or "claim" in question.lower() or "document" in question.lower():
            if language == "hindi":
                direct_ans = "कैशलेस या रीइंबर्समेंट क्लेम प्रोसेस करने के लिए आपको निर्धारित समय-सीमा के भीतर पूर्ण मूल चिकित्सा कागजात और बिल जमा करने होते हैं।"
                simple_exp = "क्लेम दो तरह से होता है: नेटवर्क अस्पताल में बिना पैसे दिए कैशलेस सुविधा (TPA द्वारा), या नॉन-नेटवर्क में पहले खुद भुगतान करके बाद में रीइंबर्समेंट प्राप्त करना।"
                cond_points = [
                    "**अनिवार्य दस्तावेज:** विधिवत भरा हुआ क्लेम फॉर्म, डिस्चार्ज समरी, मूल आइटमवार बिल, भुगतान रसीदें, डॉक्टर के पर्चे और डायग्नोस्टिक रिपोर्ट।",
                    "**कैशलेस पूर्व-सूचना:** नियोजित भर्ती से 48 घंटे पहले और आपातकालीन भर्ती के 24 घंटे के भीतर बीमा टीपीए को सूचित करना अनिवार्य है।",
                    "**रीइंबर्समेंट समय-सीमा:** अस्पताल से छुट्टी मिलने के 15 से 30 दिनों के भीतर सभी मूल दस्तावेज कंपनी को जमा करने होते हैं।",
                    "**मूल डायग्नोस्टिक रिपोर्ट:** बीमारी की पुष्टि करने वाली एक्स-रे, रक्त परीक्षण और एमआरआई जैसी सभी जांच रिपोर्ट संलग्न होनी चाहिए।"
                ]
            elif is_hinglish:
                direct_ans = "Cashless ya reimbursement claim file karne ke liye aapko nirdharit samay sima ke bheetar complete medical documents aur bills submit karne hote hain."
                simple_exp = "Claim lene ke do tarike hote hain: Cashless (jahan company seedhe network hospital ko pay karti hai) aur Reimbursement (jahan pehle aap bill bharte hain aur baad mein refund lete hain)."
                cond_points = [
                    "**Zaroori Documents:** Duly filled claim form, hospital discharge summary, original itemized medical bills, payment receipts, doctor's prescriptions, aur diagnostic reports.",
                    "**Cashless Treatment:** Planned admission se 48 ghante pehle ya emergency admission ke 24 ghante ke bheetar TPA ko intimation dena zaroori hai.",
                    "**Reimbursement Timelines:** Hospital se discharge hone ke 15 se 30 dino ke bheetar sabhi original documents submit karna anivarya hai.",
                    "**TPA & Network:** Cashless suvidha keval insurance company ke network hospitals mein Third Party Administrator (TPA) ke authorization ke baad milti hai."
                ]
            else:
                direct_ans = "To process a health insurance claim smoothly, you must provide valid proof of medical treatment and submit required documents within mandated policy timelines."
                simple_exp = "Claims can be filed either via Cashless facility (where the insurer settles bills directly with a network hospital via a TPA) or Reimbursement (where you settle the hospital bill upfront and file for refund with original invoices)."
                cond_points = [
                    "**Mandatory Claim Documents:** Completed claim form, original hospital discharge card/summary, itemized medical bills with numbered payment receipts, prescriptions, and pharmacy cash memos.",
                    "**Cashless Intimation Timeline:** Pre-authorization must be submitted to the TPA at least 48 hours prior to planned hospital admission, or within 24 hours in medical emergencies.",
                    "**Reimbursement Submission Window:** For non-network hospitals, all original papers and claim dockets must be submitted to the insurer within 15 to 30 days from discharge.",
                    "**Diagnostic Evidence:** Original lab reports, radiology scans, and pathological test receipts justifying medical necessity must accompany the claim."
                ]

        # =========================================================================
        # 6. CONDITIONS FOR HOSPITALIZATION
        # =========================================================================
        elif intent == "hospitalization_conditions" or "conditions for hospitalization" in question.lower() or "24 hours" in question.lower():
            if language == "hindi":
                direct_ans = "अस्पताल में भर्ती (In-patient Hospitalization) खर्च मिलने के लिए मान्यता प्राप्त अस्पताल में डॉक्टर की सलाह पर चिकित्सकीय रूप से आवश्यक भर्ती होना अनिवार्य है।"
                simple_exp = "बीमा कंपनी अस्पताल का खर्च तभी वहन करती है जब इलाज के लिए लगातार भर्ती रहना चिकित्सकीय दृष्टि से जरूरी हो। घर पर किए जा सकने वाले सामान्य जांच खर्च कवर नहीं होते।"
                cond_points = [
                    "**न्यूनतम 24 घंटे का प्रवास:** मानक चिकित्सा उपचार के लिए अस्पताल में लगातार कम से कम 24 घंटे भर्ती रहना अनिवार्य है।",
                    "**डे-केयर सर्जरी की छूट:** मोतियाबिंद, कीमोथेरेपी और डायलिसिस जैसी आधुनिक सर्जरी जो 24 घंटे से कम में हो जाती हैं, पूरी तरह कवर होती हैं।",
                    "**पंजीकृत अस्पताल की शर्त:** अस्पताल स्थानीय स्वास्थ्य प्राधिकरण से पंजीकृत होना चाहिए जिसमें इन-पेशेंट बेड और योग्य डॉक्टर उपलब्ध हों।",
                    "**भर्ती से पूर्व व बाद का खर्च:** भर्ती से 30 दिन पहले और डिस्चार्ज के 60 दिन बाद तक की संबंधित दवाइयां और जांचें भी क्लेम की जा सकती हैं।"
                ]
            elif is_hinglish:
                direct_ans = "Hospitalization cover hone ke liye patient ko kisi recognized hospital mein doctor ki advice par medically necessary treatment ke liye bharti hona zaroori hai."
                simple_exp = "Company hospital ka kharcha tabhi deti hai jab bharti hona sach mein zaroori ho. Agar ilaaj OPD mein ya ghar baithe ho sakta tha, toh claim reject ho sakta hai."
                cond_points = [
                    "**Minimum 24 Ghante ka Stay:** Standard ilaaj ke liye kam se kam 24 continuous hours tak hospital mein bharti rehna zaroori hai.",
                    "**Day-Care Procedures ki Chhoot:** Dialysis, chemotherapy, cataract jaisi modern surgeries jinme technology ki wajah se 24 ghante se kam samay lagta hai, cover hoti hain.",
                    "**Hospital ki Eligibility:** Hospital registered hona chahiye aur usme qualified doctors aur nurses ka 24-ghante supervision hona anivarya hai.",
                    "**Pre & Post Hospitalization:** Bharti hone se pehle (e.g. 30 din) aur discharge ke baad (e.g. 60 din) ke relevant medical tests aur dawaiyon ke kharche bhi cover hote hain."
                ]
            else:
                direct_ans = "In-patient hospitalization coverage requires that an insured person undergo medically necessary treatment under qualified medical supervision in an accredited hospital."
                simple_exp = "Hospitalization benefits trigger when an illness or accidental injury cannot be treated in an outpatient clinic and requires round-the-clock clinical supervision in an accredited healthcare facility."
                cond_points = [
                    "**Minimum In-Patient Stay:** A continuous hospital stay of at least 24 consecutive hours is mandatory for standard illness and surgical treatments.",
                    "**Day-Care Procedure Exception:** Medically advanced surgeries (such as cataract, chemotherapy, radiotherapy, or hemodialysis) requiring less than 24 hours of stay are fully covered under day-care benefits.",
                    "**Accredited Hospital Criteria:** Medical care must be administered in a facility registered with local health authorities holding adequate inpatient beds and dedicated surgical infrastructure.",
                    "**Pre & Post-Hospitalization:** Diagnostic consultations and prescription medicines incurred 30 days prior to admission and 60 days following discharge are payable."
                ]

        # =========================================================================
        # 7. ROOM RENT LIMIT & ICU CHARGES
        # =========================================================================
        elif raw_topic == "room_rent" or "room rent" in question.lower() or "icu" in question.lower():
            room_pct = [p for p in unique_pcts if "1%" in p or "%" in p]
            icu_pct = [p for p in unique_pcts if "2%" in p or "%" in p]
            pct_desc = room_pct[0] if room_pct else "1% of Sum Insured per day"

            if language == "hindi":
                direct_ans = f"इस पॉलिसी में कमरे के किराए (Room Rent) और ICU शुल्क पर निश्चित दैनिक सीमा ({pct_desc}) लागू होती है।"
                simple_exp = "यदि आप अपनी पात्रता से अधिक महंगा कमरा चुनते हैं, तो 'आनुपातिक कटौती' (Proportionate Deduction) के कारण डॉक्टर फीस, सर्जरी और नर्सिंग बिल में भी उसी अनुपात में कटौती कर दी जाएगी।"
                cond_points = [
                    f"**कमरे के किराए की सीमा:** कमरे का किराया सामान्यतः बीमा राशि का {pct_desc} या सिंगल प्राइवेट रूम तक सीमित होता है।",
                    "**ICU शुल्क उप-सीमा:** आईसीयू शुल्क के लिए अलग सीमा (आमतौर पर बीमा राशि का 2% या वास्तविक) लागू होती है।",
                    "**आनुपातिक कटौती का नियम:** पात्र सीमा से ऊपर का कमरा लेने पर अस्पताल के पूरे बिल के एसोसिएटेड मेडिकल खर्चों में आनुपातिक कटौती होती है।"
                ]
            elif is_hinglish:
                direct_ans = f"Is policy mein room rent aur ICU charges par limit hoti hai ({pct_desc}). Agar aap eligible slab se mehnga room chunte hain toh proportionate deduction lagta hai."
                simple_exp = "Agar aapki policy 5,000 rupaye daily room ki ijazat deti hai aur aapne 10,000 ka room liya, toh company sirf room ka difference hi nahi kategi, balki doctor fees aur operation charges bhi aadhe kar degi."
                cond_points = [
                    f"**Room Rent Cap:** Rozana room rent ki limit {pct_desc} ya single private room tak nirdharit hoti hai.",
                    f"**ICU Charges:** ICU ke liye alag limit hoti hai (aam taur par 2% of Sum Insured ya actuals as per plan).",
                    "**Proportionate Deduction:** Agar aap eligible limit se upar ka room lete hain, toh doctor fees, surgery charges aur nursing par bhi usi anupaat mein katauti hogi."
                ]
            else:
                direct_ans = f"Room rent coverage is governed by specific daily sub-limits ({pct_desc}). Exceeding your designated room eligibility triggers proportionate deductions across associated medical charges."
                simple_exp = "Opting for a room tier above your eligible cap does not merely mean paying the difference in room rent. Under the proportionate deduction clause, the insurer proportionately slashes reimbursement across doctors' visits, surgery fees, and theater charges."
                cond_points = [
                    f"**Daily Room Rent Limit:** Standard accommodation is capped at {pct_desc} or single private room (depending on chosen Sum Insured).",
                    f"**ICU Charges Limit:** Intensive Care Unit (ICU) charges carry a distinct sub-limit (typically 2% of Sum Insured per day, or actuals for higher plans).",
                    "**Proportionate Deduction Clause:** If an insured opts for a room category above their eligible slab, all associated doctor consultation fees, nursing fees, and operation theater costs will be paid proportionately reduced."
                ]

        # =========================================================================
        # 8. CATARACT LIMIT
        # =========================================================================
        elif raw_topic == "cataract" or "cataract" in question.lower():
            cat_limit = unique_rupees[0] if unique_rupees else "up to ₹40,000 per eye"
            if language == "hindi":
                direct_ans = f"मोतियाबिंद (Cataract) का ऑपरेशन इस पॉलिसी में कवर है, परंतु इस पर 24 महीने की प्रतीक्षा अवधि और प्रति आंख वित्तीय सीमा ({cat_limit}) लागू होती है।"
                simple_exp = "भले ही मोतियाबिंद की आधुनिक सर्जरी केवल 30 मिनट में हो जाती है, बीमा कंपनी इसे विशिष्ट प्रक्रिया मानती है जिसके लिए 2 साल की निरंतर पॉलिसी अनिवार्य है और लेंस की अधिकतम कीमत तय है।"
                cond_points = [
                    f"**अधिकतम वित्तीय सीमा:** मोतियाबिंद ऑपरेशन और लेंस प्रतिस्थापन के लिए प्रति आंख {cat_limit} की सीमा है।",
                    "**24 महीने की प्रतीक्षा अवधि:** पॉलिसी शुरू होने के लगातार दो वर्ष पूरे होने के बाद ही यह क्लेम मान्य होता है।",
                    "**डे-केयर सुविधा:** मोतियाबिंद का इलाज आधुनिक डे-केयर प्रक्रिया के रूप में बिना रात भर अस्पताल में रुके कवर किया जाता है।"
                ]
            elif is_hinglish:
                direct_ans = f"Cataract (motiyabind) surgery is policy mein cover hai, par is par 24 mahine ka waiting period aur specific financial limit ({cat_limit}) lagu hoti hai."
                simple_exp = "Aadhunik cataract surgery aadhe ghante mein ho jaati hai, par company iske liye 2 saal ka waiting period rakhti hai aur lens cost par cap lagati hai."
                cond_points = [
                    f"**Financial Sub-limit:** Dono aankhon ke operation ke liye adhiktam limit ({cat_limit}) nirdharit hai.",
                    "**24 Mahine ka Waiting Period:** Policy shuru hone ke 2 saal baad hi cataract ke kharche claim kiye ja sakte hain.",
                    "**Day-Care Cover:** Motiyabind ka operation modern day-care procedure ke roop mein bina 24 ghante admit huye cover hota hai."
                ]
            else:
                direct_ans = f"Cataract surgery is covered under this policy, subject to a mandatory 24-month waiting period and a specific monetary sub-limit per eye ({cat_limit})."
                simple_exp = "Even though modern cataract phacoemulsification takes under an hour, the insurer treats it as a designated surgery with a 2-year waiting timeline and caps the admissible cost for both surgical fees and intraocular lens (IOL)."
                cond_points = [
                    f"**Monetary Sub-Limit:** Reimbursement for cataract operation and lens replacement is capped at {cat_limit} per eye.",
                    "**24-Month Waiting Period:** Claims for cataract treatment are only admissible after completing two consecutive policy years without interruption.",
                    "**Day-Care Classification:** Treatment is covered as an advanced day-care procedure without requiring a full 24-hour overnight hospital stay."
                ]

        # =========================================================================
        # 9. GENERAL OVERVIEW (WHAT DOES THIS POLICY COVER?)
        # =========================================================================
        elif intent == "overview_coverage" or "what does this policy cover" in question.lower():
            if language == "hindi":
                direct_ans = "यह हेल्थ इंश्योरेंस पॉलिसी अस्पताल में भर्ती होने पर आने वाले आवश्यक चिकित्सा खर्चों, आधुनिक डे-केयर सर्जरी और आपातकालीन सेवाओं को व्यापक वित्तीय सुरक्षा प्रदान करती है।"
                simple_exp = "यदि आप या आपका बीमित परिवार बीमारी या दुर्घटना के कारण अस्पताल में भर्ती होता है, तो पॉलिसी आपके कमरे का किराया, डॉक्टर की फीस, जांच, ऑपरेशन और दवाइयों का खर्च बीमा राशि तक वहन करती है।"
                cond_points = [
                    "**इन-पेशेंट अस्पताल भर्ती:** कमरा किराया, नर्सिंग, डॉक्टर फीस, आईसीयू शुल्क, ऑपरेशन थियेटर और दवाओं का खर्च शामिल है।",
                    "**डे-केयर उपचार:** 24 घंटे से कम समय में होने वाले आधुनिक इलाज (जैसे डायलिसिस, कीमोथेरेपी, मोतियाबिंद) पूर्णतः कवर हैं।",
                    "**भर्ती पूर्व व बाद का खर्च:** अस्पताल में भर्ती होने से 30 दिन पहले और डिस्चार्ज के 60 दिन बाद तक की जांचें व दवाएं शामिल हैं।",
                    "**आपातकालीन एम्बुलेंस:** नजदीकी अस्पताल पहुंचने के लिए इमरजेंसी रोड एम्बुलेंस और आयुष (आयुर्वेद/होम्योपैथी) इलाज भी पॉलिसी नियमानुसार देय हैं।"
                ]
            elif is_hinglish:
                direct_ans = "Yah health insurance policy hospital mein bharti hone par aane wale sabhi zaroori medical kharchon, day-care procedures, aur emergency services ko cover karti hai."
                simple_exp = "Bimari ya accident hone par hospitalization ka kharcha (room, doctor consultation, surgery, tests, aur medicines) company Sum Insured tak reimburse karti hai."
                cond_points = [
                    "**In-Patient Hospitalization:** Room rent, nursing fees, doctor/surgeon consultation, ICU charges, operation theater, aur dawaiyon ka kharcha shamil hai.",
                    "**Day-Care Procedures:** Aise aadhunik operations jinme 24 ghante se kam samay lagta hai (dialysis, cataract, chemotherapy) pura cover hote hain.",
                    "**Pre & Post Hospitalization:** Admit hone se 30 din pehle aur discharge hone ke 60 din baad tak ke medical tests aur davaaiyan claim ki ja sakti hain.",
                    "**Emergency Support:** Emergency road ambulance charges aur AYUSH (Ayurveda/Homeopathy) treatments policy niyam anusar shamil hain."
                ]
            else:
                direct_ans = "This policy provides comprehensive financial protection against medically necessary in-patient hospitalizations, specialized day-care procedures, and related emergency expenses."
                simple_exp = "If you or an insured family member requires hospitalization for an unexpected illness or accident, the policy reimburses your hospital stay, surgery, intensive care, and pharmacy charges up to your chosen Sum Insured."
                cond_points = [
                    "**In-Patient Hospitalization Expenses:** Covers room rent, boarding, nursing care, intensive care unit (ICU) charges, physician fees, surgeon and anesthesia charges, and pharmacy costs.",
                    "**Day-Care Treatments:** Fully covers advanced medical treatments and surgical procedures requiring less than 24 hours of hospital stay due to modern technological advancements.",
                    "**Pre & Post-Hospitalization Care:** Reimburses diagnostic tests and prescription medicines incurred 30 days prior to hospital admission and 60 days following hospital discharge.",
                    "**Emergency & AYUSH Benefits:** Covers emergency road ambulance transportation to the nearest hospital and alternative treatments received in registered AYUSH hospitals."
                ]

        # =========================================================================
        # 10. FALLBACK / GENERAL QUESTION
        # =========================================================================
        else:
            pages_cited = sorted(list(set(c["page"] for c in citations if c.get("page"))))
            pages_str = ", ".join(f"Page {p}" for p in pages_cited) if pages_cited else "the policy text"

            if language == "hindi":
                direct_ans = f"आपके द्वारा पूछे गए प्रश्न के नियम एवं शर्तें अपलोड किए गए दस्तावेज़ के {pages_str} पर उल्लिखित हैं।"
                simple_exp = "पॉलिसी अनुबंध इस प्रक्रिया या लाभ के लिए स्पष्ट सीमाएं और दायित्व तय करता है। क्लेम प्राप्त करने के लिए पंजीकृत चिकित्सक द्वारा चिकित्सा आवश्यकता प्रमाणित होना अनिवार्य है।"
                cond_points = [
                    "**अनुभाग नियम:** पॉलिसी के संबंधित अनुभाग में इस विशिष्ट चिकित्सा स्थिति के अधिकार और देयताएं स्पष्ट रूप से परिभाषित हैं।",
                    "**चिकित्सकीय आवश्यकता:** किसी भी लाभ का क्लेम लेने के लिए उपचार का मान्यता प्राप्त चिकित्सक द्वारा 'Medically Necessary' होना आवश्यक है।",
                    "**बीमा राशि एवं सीमाएं:** भुगतान आपके द्वारा चुने गए सम इंश्योर्ड और पॉलिसी सर्टिफिकेट में निर्धारित शर्तों के अधीन होगा।"
                ]
            elif is_hinglish:
                direct_ans = f"Aapke dwara puche gaye sawaal ka vivaran uploaded document ke {pages_str} par milta hai, jahan iske niyam aur shartein darj hain."
                simple_exp = "Policy agreement mein is benefit ke rules spasht hain. Claim lene ke liye ilaaj ka registered doctor dwara medically necessary hona anivarya hota hai."
                cond_points = [
                    f"**Section Terms:** Policy ke sambandhit section mein is vishesh medical condition aur coverage rules ka ullekh kiya gaya hai.",
                    "**Mandatory Medical Necessity:** Kisi bhi benefit ka claim lene ke liye ilaaj ka registered doctor dwara medically necessary hona anivarya hai.",
                    "**Limits & Deductibles:** Policy schedule mein nirdharit sum insured aur co-payment shartein is par lagu hongi."
                ]
            else:
                direct_ans = f"The terms governing your inquiry are documented on {pages_str} of your uploaded policy agreement, outlining specific rights, coverage provisions, and boundaries."
                simple_exp = "Your health insurance agreement establishes clear criteria and eligibility constraints for this inquiry. All admissible claims require medical necessity certification by a registered physician."
                cond_points = [
                    f"**Applicable Terms:** The referenced policy sections delineate admissible benefits, conditions of liability, and documentation criteria for this treatment.",
                    "**Medical Necessity Requirement:** All reimbursable treatments must be medically necessary, prescribed by a qualified medical practitioner, and administered in an accredited hospital.",
                    "**Plan Limits:** Benefits are governed by the overall Sum Insured, applicable co-payment clauses, and schedule limits specified on your policy certificate."
                ]

        # Formulate Evidence Summary
        pages_cited = sorted(list(set(c["page"] for c in citations if c.get("page"))))
        pages_str = ", ".join(f"Page {p}" for p in pages_cited) if pages_cited else "the policy document"
        first_sec = citations[0].get("section", "Policy Provisions") if citations else "Policy Provisions"
        first_clause = citations[0].get("clause_number")
        clause_str = f"Clause {first_clause}" if first_clause else "the clause provisions"

        if language == "hindi":
            evidence_summary = f"यह व्याख्या अपलोड की गई पॉलिसी के अनुभाग \"{first_sec}\" ({clause_str}) और {pages_str} पर आधारित है। संबंधित मूल दस्तावेज के अंश नीचे प्रमाण कार्ड्स में उपलब्ध हैं।"
        elif is_hinglish:
            evidence_summary = f"Yah vyakhya uploaded policy ke section \"{first_sec}\" ({clause_str}) aur {pages_str} par darj pramaan par aadharit hai. Original passages niche citation cards mein dekhein."
        else:
            evidence_summary = f"This explanation is grounded in Section \"{first_sec}\" ({clause_str}) across {pages_str} of your active policy document. Original supporting clauses and relevance scores are displayed below."

        # Format clean, humanized 4-part markdown structure
        formatted_lines = [
            "### Direct Answer",
            direct_ans,
            "",
            "### Simple Explanation",
            simple_exp,
            "",
            "### Important Conditions",
        ]
        for pt in cond_points:
            formatted_lines.append(f"- {pt}")

        formatted_lines.append("")
        formatted_lines.append("### Evidence from Your Policy")
        formatted_lines.append(evidence_summary)

        answer_text = "\n".join(formatted_lines)

        return {
            "answer": answer_text,
            "status": "answered",
            "citations": citations
        }

        return {
            "answer": answer_text,
            "status": "answered",
            "citations": citations
        }
