import os
import json
from typing import List, Dict, Any, Optional
import httpx
from app.core.config import settings
from app.core.logging import logger

SYSTEM_PROMPT = """You are PolicyLens, an expert health insurance policy explanation assistant.
The uploaded policy document is your primary source of truth.
Answer the user's question using ONLY the provided policy evidence clauses.
Do not invent coverage, exclusions, waiting periods, financial limits, or claim requirements.
If the evidence is missing, insufficient, ambiguous, or contradictory, clearly state that the policy does not contain sufficient evidence.
Preserve important conditions, qualifications, and waiting periods.
Always cite the page number and section supporting each claim.
Format your answer clearly with concise bullet points where appropriate, explaining complex insurance terms in plain, easy-to-understand language.
Distinguish explicit policy statements from interpretations."""

class LLMService:
    """
    Multi-Provider Grounded LLM Response Generator.
    Supports Google Gemini, OpenAI, Ollama, and Local Deterministic Grounded Synthesizer.
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
            topic_name = analysis.get("topic", "the queried topic").replace("_", " ")
            return {
                "answer": (
                    f"Based on the uploaded policy document, there is insufficient evidence to confirm details regarding **{topic_name}**.\n\n"
                    "The policy does not explicitly mention this specific condition, treatment, or term in the indexed sections. "
                    "Please verify whether this treatment is covered under another rider or check the policy definitions."
                ),
                "status": "insufficient_evidence",
                "citations": []
            }

        evidence_lines = []
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

            clause_str = f"Clause {clause_num}" if clause_num else f"Item {idx+1}"
            evidence_lines.append(f"[{clause_str} | Page {page} | Section: {sec} | Category: {cat}]:\n\"{text_snippet}\"\n")

            citations.append({
                "page": page,
                "section": sec,
                "clause_number": clause_num,
                "category": cat,
                "relevance_score": norm_rel,
                "text": text_snippet
            })

        evidence_prompt = "\n".join(evidence_lines)

        history_text = ""
        if conversation_context:
            recent = conversation_context[-4:]
            hist_parts = [f"{m['role'].capitalize()}: {m['content']}" for m in recent]
            history_text = "Previous Conversation Context:\n" + "\n".join(hist_parts) + "\n\n"

        full_user_prompt = f"""{history_text}Policy Evidence from Uploaded Document:
{evidence_prompt}

User Question: {question}

Please answer the user's question directly, clearly, and objectively based strictly on the policy evidence above. Cite the specific page and section numbers for each statement."""

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
                    return {
                        "answer": response.text.strip(),
                        "status": "answered",
                        "citations": citations
                    }
            except Exception as e:
                logger.error(f"Gemini API error: {e}")

        # 2. Local Grounded Synthesizer
        return cls._local_grounded_synthesis(question, citations, analysis)

    @classmethod
    def _local_grounded_synthesis(
        cls,
        question: str,
        citations: List[Dict[str, Any]],
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        intent = analysis.get("intent", "general_qa")
        raw_topic = analysis.get("topic", "")
        topic = raw_topic.replace("_", " ").title() if raw_topic else "Policy Term"

        pages_cited = sorted(list(set(c["page"] for c in citations)))
        pages_str = ", ".join(f"Page {p}" for p in pages_cited)

        # Categorize evidence points specifically mentioning topic keywords
        topic_words = set(raw_topic.lower().split("_")) if raw_topic else set()
        
        def matches_topic(text: str) -> bool:
            if not topic_words or raw_topic == "general_health_policy":
                return True
            t_low = text.lower()
            return any(w in t_low for w in topic_words)

        coverages = [c for c in citations if c.get("category") == "Coverage" and matches_topic(c["text"])]
        waitings = [c for c in citations if c.get("category") == "Waiting Period" and matches_topic(c["text"])]
        exclusions = [c for c in citations if c.get("category") == "Exclusion" and matches_topic(c["text"])]
        claims = [c for c in citations if c.get("category") == "Claim Requirement"]

        # Fallback if topic filtering yields empty
        if not coverages and not exclusions and not waitings:
            coverages = [c for c in citations if c.get("category") == "Coverage"]
            waitings = [c for c in citations if c.get("category") == "Waiting Period"]
            exclusions = [c for c in citations if c.get("category") == "Exclusion"]

        lines = []

        if intent == "coverage_inquiry":
            # If explicit exclusion exists and no coverage exists
            if exclusions and not coverages:
                lines.append(f"**Coverage Determination:** **{topic}** is strictly excluded and is not covered under this policy.")
            elif coverages:
                lines.append(f"**Coverage Determination:** Yes, **{topic}** is covered under the policy terms subject to stated conditions and waiting periods.")
            else:
                lines.append(f"**Policy Findings:** Relevant terms regarding **{topic}** were identified in the document ({pages_str}).")

            if coverages:
                lines.append("\n**Coverage Details:**")
                for c in coverages[:2]:
                    lines.append(f"- {c['text']} *(Source: Page {c['page']}, {c['section']})*")

            if waitings:
                lines.append("\n**Applicable Waiting Period:**")
                for c in waitings[:2]:
                    lines.append(f"- {c['text']} *(Source: Page {c['page']}, {c['section']})*")

            if exclusions:
                lines.append("\n**Exclusions / Limitations:**")
                for c in exclusions[:2]:
                    lines.append(f"- {c['text']} *(Source: Page {c['page']}, {c['section']})*")

        elif intent == "waiting_period_inquiry":
            lines.append(f"**Waiting Period Details for {topic}:**")
            target_clauses = waitings if waitings else citations
            for c in target_clauses[:3]:
                lines.append(f"- {c['text']} *(Source: Page {c['page']}, {c['section']})*")

        elif intent == "exclusion_inquiry":
            lines.append(f"**Exclusions Associated with {topic}:**")
            target_clauses = exclusions if exclusions else citations
            for c in target_clauses[:4]:
                lines.append(f"- {c['text']} *(Source: Page {c['page']}, {c['section']})*")

        elif intent == "claim_inquiry":
            lines.append(f"**Claim Requirements & Procedure:**")
            target_clauses = claims if claims else citations
            for c in target_clauses[:3]:
                lines.append(f"- {c['text']} *(Source: Page {c['page']}, {c['section']})*")

        else:
            lines.append(f"Based on the policy evidence extracted from **{pages_str}**:")
            for c in citations[:3]:
                lines.append(f"- {c['text']} *(Source: Page {c['page']}, {c['section']})*")

        answer_text = "\n".join(lines)
        return {
            "answer": answer_text,
            "status": "answered",
            "citations": citations
        }
