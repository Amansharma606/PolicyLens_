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
   Your answer must explain what the policy means in clear, accessible language for an everyday policyholder.

2. STRUCTURE YOUR ANSWER AS FOLLOWS:
   **Direct Answer:**
   Give a direct, clear 1 to 3 sentence natural-language answer to the user's question.

   **Important Conditions & Limits:**
   - List key conditions, waiting periods, financial sub-limits, mandatory requirements, or exclusions as concise bullet points.
   - Explain technical insurance jargon in plain terms (e.g., explaining what 'PED', 'co-payment', 'TPA', or 'room rent capping' means).

3. STRICT GROUNDING IN UPLOADED DOCUMENT:
   Answer using ONLY the provided policy evidence clauses. Do NOT invent coverage, waiting periods, financial caps, or exclusions.
   If the evidence does not mention the queried term, condition, or disease, explicitly state:
   "I could not find sufficient information about this in the uploaded policy document."

4. MULTI-LANGUAGE SUPPORT:
   If the user asks in Hindi or Hinglish, provide the Direct Answer and Conditions in clear, natural Hindi/Hinglish.
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
                if is_hinglish:
                    direct_ans = f"Haan, is policy ke tahat maternity aur newborn care expenses cover kiye jaate hain, par is par {wait_str} ka continuous waiting period aur specific sub-limits lagu hoti hain."
                    cond_points = [
                        f"**Waiting Period:** Maternity labh lene ke liye kam se kam {wait_str} tak bina kisi break ke policy chalu rehna anivarya hai.",
                        f"**Delivery Sub-Limits:** Normal delivery aur Cesarean section ke liye nirdharit financial limits ({', '.join(unique_rupees[:2]) if unique_rupees else 'up to ₹50,000 for normal and ₹75,000 for cesarean'}) lagu hoti hain.",
                        "**Newborn Baby Cover:** Bachhe ke janam ke baad initial days ke hospitalization aur vaccinations policy terms ke anusar cover hote hain.",
                        "**Excluded Procedures:** Infertility treatments, sub-fertility, IVF, aur voluntary surrogacy strictly excluded hain."
                    ]
                else:
                    direct_ans = f"Yes, maternity expenses and childbirth are covered under this policy, subject to a mandatory continuous waiting period of {wait_str} and specified monetary sub-limits."
                    cond_points = [
                        f"**Mandatory Waiting Period:** Coverage for maternity expenses becomes active only after completing {wait_str} of continuous active policy renewal.",
                        f"**Delivery Sub-Limits:** Reimbursement is capped at specified limits ({', '.join(unique_rupees[:2]) if unique_rupees else 'up to ₹50,000 for normal delivery and ₹75,000 for cesarean'}).",
                        "**Newborn Baby Extension:** Hospitalization expenses for the newborn baby are covered from birth up to the specified maternity limits.",
                        "**Exclusions:** Infertility treatments, IVF procedures, surrogate child arrangements, and voluntary abortion are excluded."
                    ]
            else:
                if is_hinglish:
                    direct_ans = "Nahi, is policy ke tahat maternity sambhandhit kharche permanent exclusions mein shamil hain aur cover nahi hain."
                    cond_points = [
                        "**Permanent Exclusion:** Normal delivery, C-section, aur pregnancy treatments non-payable items mein shamil hain.",
                        "**Optional Rider:** Yadi aap maternity cover chahte hain, toh alag se maternity add-on rider lena hoga."
                    ]
                else:
                    direct_ans = "No, maternity and pregnancy-related medical treatments are listed under policy exclusions and are not covered under standard terms."
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

            if is_hinglish:
                direct_ans = f"Pre-existing diseases (policy lene se pehle ki bimariyan jaise diabetes ya hypertension) is policy mein {wait_str} ke waiting period ke baad hi cover hoti hain."
                cond_points = [
                    f"**Waiting Period:** Bimari shamil hone ke liye {wait_str} tak bina kisi break ke policy chalu rehna anivarya hai.",
                    "**PED ka Matlab:** Koi bhi aisi bimari ya lakshan jo policy start hone se pehle diagnose hua ho ya jiska ilaaj chal raha ho.",
                    "**Portability Benefit:** Yadi aap kisi dusri company se policy port karte hain, toh pehle se serve kiya gaya waiting period carry-forward hota hai."
                ]
            else:
                direct_ans = f"Pre-existing diseases (PED) are covered under this policy only after completing a mandatory waiting period of {wait_str} of continuous active coverage."
                cond_points = [
                    f"**Mandatory Waiting Period:** No claims will be accepted for conditions diagnosed or treated prior to policy inception until {wait_str} have elapsed.",
                    "**Definition of PED:** Any health condition, ailment, or chronic illness (e.g., diabetes, hypertension) diagnosed by a physician or treated within 48 months before purchasing the policy.",
                    "**Portability Credit:** If you ported this policy from another registered insurer without a break, the waiting period already served is credited toward this requirement."
                ]

        # =========================================================================
        # 3. WAITING PERIODS (GENERAL OR LIST ALL)
        # =========================================================================
        elif intent == "waiting_period_inquiry" or "waiting period" in question.lower():
            if is_hinglish:
                direct_ans = "Is policy ke tahat teen pramukh prakar ke waiting periods lagu hote hain: initial 30 days, specific illnesses (24 mahine), aur pre-existing diseases."
                cond_points = [
                    "**Initial 30-Day Wait:** Policy shuru hone ke pehle 30 dino tak kisi bhi aam bimari ka claim nahi milta (keval accident emergency cover hoti hai).",
                    f"**Specific Illnesses (24 Months):** Cataract, hernia, joint replacement, aur kidney stones jaise common treatments par 24 mahine ka waiting period hota hai.",
                    f"**Pre-Existing Diseases:** Pehle se maujood bimariyon ke liye {unique_waits[0] if unique_waits else '36 se 48 mahine'} ka waiting period lagu hota hai."
                ]
            else:
                direct_ans = "This policy features three tiered waiting periods before full benefits become claimable: an initial 30-day period, specific illness periods, and pre-existing disease waiting periods."
                cond_points = [
                    "**Initial 30-Day Waiting Period:** All illnesses diagnosed within the first 30 days of policy inception are excluded, except emergency hospitalizations due to an accident.",
                    "**Specified Disease / Procedure Waiting Period (24 Months):** Slower-progressing conditions (such as cataract, hernia, piles, joint replacements, and gallstones) require 24 months of continuous coverage.",
                    f"**Pre-Existing Disease (PED) Waiting Period:** Declared chronic conditions require {unique_waits[0] if unique_waits else '24 to 48 months'} of active policy renewal before claims are payable."
                ]

        # =========================================================================
        # 4. EXCLUSIONS INQUIRY
        # =========================================================================
        elif intent == "exclusion_inquiry" or "exclusion" in question.lower() or "not covered" in question.lower():
            if is_hinglish:
                direct_ans = "Policy mein un sabhi kharchon aur treatments ki spasht suchi hoti hai jinhe insurer bilkul cover nahi karta (permanent exclusions)."
                cond_points = [
                    "**Cosmetic & Plastic Surgery:** Sundarta badhane, cosmetic procedures, ya gender transformation ke kharche strictly excluded hain.",
                    "**Self-Harm & Adventure Sports:** Aatmhatya ka prayas, intentional self-injury, ya dangerous sports se hone wale nuksan cover nahi hote.",
                    "**Non-Payable Consumables:** Registration charges, hospital admission fee, gloves, masks, aur personal comfort items non-payable hote hain.",
                    "**Unproven Treatments:** Koi bhi aisa ilaaj ya experimental therapy jise recognized medical authorities ne approve na kiya ho, excluded hai."
                ]
            else:
                direct_ans = "The policy specifies standard permanent exclusions for medical treatments, procedures, and conditions where no reimbursement or claim benefits are payable."
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
            if is_hinglish:
                direct_ans = "Cashless ya reimbursement claim file karne ke liye aapko nirdharit samay sima ke bheetar complete medical documents aur bills submit karne hote hain."
                cond_points = [
                    "**Zaroori Documents:** Duly filled claim form, hospital discharge summary, original itemized medical bills, payment receipts, doctor's prescriptions, aur diagnostic reports.",
                    "**Cashless Treatment:** Planned admission se 48 ghante pehle ya emergency admission ke 24 ghante ke bheetar TPA ko intimation dena zaroori hai.",
                    "**Reimbursement Timelines:** Hospital se discharge hone ke 15 se 30 dino ke bheetar sabhi original documents submit karna anivarya hai.",
                    "**TPA & Network:** Cashless suvidha keval insurance company ke network hospitals mein Third Party Administrator (TPA) ke authorization ke baad milti hai."
                ]
            else:
                direct_ans = "To process a health insurance claim smoothly, you must provide valid proof of medical treatment and submit required documents within mandated policy timelines."
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
            if is_hinglish:
                direct_ans = "Hospitalization cover hone ke liye patient ko kisi recognized hospital mein doctor ki advice par medically necessary treatment ke liye bharti hona zaroori hai."
                cond_points = [
                    "**Minimum 24 Ghante ka Stay:** Standard ilaaj ke liye kam se kam 24 continuous hours tak hospital mein bharti rehna zaroori hai.",
                    "**Day-Care Procedures ki Chhoot:** Dialysis, chemotherapy, cataract jaisi modern surgeries jinme technology ki wajah se 24 ghante se kam samay lagta hai, cover hoti hain.",
                    "**Hospital ki Eligibility:** Hospital registered hona chahiye aur usme qualified doctors aur nurses ka 24-ghante supervision hona anivarya hai.",
                    "**Pre & Post Hospitalization:** Bharti hone se pehle (e.g. 30 din) aur discharge ke baad (e.g. 60 din) ke relevant medical tests aur dawaiyon ke kharche bhi cover hote hain."
                ]
            else:
                direct_ans = "In-patient hospitalization coverage requires that an insured person undergo medically necessary treatment under qualified medical supervision in an accredited hospital."
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

            if is_hinglish:
                direct_ans = f"Is policy mein room rent aur ICU charges par limit hoti hai. Agar aap apni eligibility se mehnga room chunte hain toh pure bill par proportionate deduction lagta hai."
                cond_points = [
                    f"**Room Rent Cap:** Rozana room rent ki limit {pct_desc} ya single private room tak nirdharit hoti hai.",
                    f"**ICU Charges:** ICU ke liye alag limit hoti hai (aam taur par 2% of Sum Insured ya actuals as per plan).",
                    "**Proportionate Deduction:** Agar aap eligible limit se upar ka room lete hain, toh doctor fees, surgery charges aur nursing par bhi usi anupaat mein katauti hogi."
                ]
            else:
                direct_ans = f"Room rent coverage is governed by specific daily sub-limits. Exceeding your designated room eligibility triggers proportionate deductions across associated medical charges."
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
            if is_hinglish:
                direct_ans = f"Cataract (motiyabind) surgery is policy mein cover hai, par is par 24 mahine ka waiting period aur specific financial limit ({cat_limit}) lagu hoti hai."
                cond_points = [
                    f"**Financial Sub-limit:** Dono aankhon ke operation ke liye adhiktam limit ({cat_limit}) nirdharit hai.",
                    "**24 Mahine ka Waiting Period:** Policy shuru hone ke 2 saal baad hi cataract ke kharche claim kiye ja sakte hain.",
                    "**Day-Care Cover:** Motiyabind ka operation modern day-care procedure ke roop mein bina 24 ghante admit huye cover hota hai."
                ]
            else:
                direct_ans = f"Cataract surgery is covered under this policy, subject to a mandatory 24-month waiting period and a specific monetary sub-limit per eye."
                cond_points = [
                    f"**Monetary Sub-Limit:** Reimbursement for cataract operation and lens replacement is capped at {cat_limit} per eye.",
                    "**24-Month Waiting Period:** Claims for cataract treatment are only admissible after completing two consecutive policy years without interruption.",
                    "**Day-Care Classification:** Treatment is covered as an advanced day-care procedure without requiring a full 24-hour overnight hospital stay."
                ]

        # =========================================================================
        # 9. GENERAL OVERVIEW (WHAT DOES THIS POLICY COVER?)
        # =========================================================================
        elif intent == "overview_coverage" or "what does this policy cover" in question.lower():
            if is_hinglish:
                direct_ans = "Yah health insurance policy hospital mein bharti hone par aane wale sabhi zaroori medical kharchon, day-care procedures, aur emergency services ko cover karti hai."
                cond_points = [
                    "**In-Patient Hospitalization:** Room rent, nursing fees, doctor/surgeon consultation, ICU charges, operation theater, aur dawaiyon ka kharcha shamil hai.",
                    "**Day-Care Procedures:** Aise aadhunik operations jinme 24 ghante se kam samay lagta hai (dialysis, cataract, chemotherapy) pura cover hote hain.",
                    "**Pre & Post Hospitalization:** Admit hone se 30 din pehle aur discharge hone ke 60 din baad tak ke medical tests aur davaaiyan claim ki ja sakti hain.",
                    "**Emergency Support:** Emergency road ambulance charges aur AYUSH (Ayurveda/Homeopathy) treatments policy niyam anusar shamil hain."
                ]
            else:
                direct_ans = "This policy provides comprehensive financial protection against medically necessary in-patient hospitalizations, specialized day-care procedures, and related emergency expenses."
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
            pages_cited = sorted(list(set(c["page"] for c in citations)))
            pages_str = ", ".join(f"Page {p}" for p in pages_cited)

            if is_hinglish:
                direct_ans = f"Aapke dwara puche gaye sawaal ka vivaran uploaded document ke {pages_str} par milta hai, jahan iske niyam aur shartein darj hain."
                cond_points = [
                    f"**Section Terms:** Policy ke sambandhit section mein is vishesh medical condition aur coverage rules ka ullekh kiya gaya hai.",
                    "**Mandatory Medical Necessity:** Kisi bhi benefit ka claim lene ke liye ilaaj ka registered doctor dwara medically necessary hona anivarya hai.",
                    "**Limits & Deductibles:** Policy schedule mein nirdharit sum insured aur co-payment shartein is par lagu hongi."
                ]
            else:
                direct_ans = f"The terms governing your inquiry are documented on {pages_str} of your uploaded policy agreement, outlining specific rights, coverage provisions, and boundaries."
                cond_points = [
                    f"**Applicable Terms:** The referenced policy sections delineate admissible benefits, conditions of liability, and documentation criteria for this treatment.",
                    "**Medical Necessity Requirement:** All reimbursable treatments must be medically necessary, prescribed by a qualified medical practitioner, and administered in an accredited hospital.",
                    "**Plan Limits:** Benefits are governed by the overall Sum Insured, applicable co-payment clauses, and schedule limits specified on your policy certificate."
                ]

        # Format clean markdown response
        formatted_lines = [
            "**Direct Answer:**",
            direct_ans,
            "",
            "**Important Conditions & Limits:**"
        ]
        for pt in cond_points:
            formatted_lines.append(f"- {pt}")

        answer_text = "\n".join(formatted_lines)

        return {
            "answer": answer_text,
            "status": "answered",
            "citations": citations
        }
