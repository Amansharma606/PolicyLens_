import json
import re
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.db_models import DocumentClause
from app.services.embeddings import EmbeddingService
from app.services.bm25_retriever import get_bm25_index
from app.core.config import settings


class HybridRetriever:
    """
    Ultra-Fast Document-Isolated Hybrid Retrieval Engine.
    Combines BM25Okapi sparse keyword scoring, TF-IDF bigram cosine similarity,
    exact distinctive-term coverage, and question-intent category boosts in < 50ms
    (with optional neural similarity only when already enabled & cached).
    """

    @classmethod
    def retrieve(
        cls,
        db: Session,
        document_id: str,
        query: str,
        analysis: Dict[str, Any],
        top_k: int = 16,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves and ranks candidate clauses strictly isolated to document_id.
        """
        db_clauses = db.query(DocumentClause).filter(DocumentClause.document_id == document_id).all()
        if not db_clauses:
            return []

        clauses_data = []
        for c in db_clauses:
            embedding = None
            if settings.USE_NEURAL_EMBEDDINGS and c.embedding_json:
                try:
                    embedding = json.loads(c.embedding_json)
                except Exception:
                    pass

            sec_name = c.section_name or "General Terms"
            clause_num = c.clause_number or ""
            cat = c.category or "General"
            clean_t = c.clean_text or c.original_text
            search_t = f"[Section: {sec_name}] [Clause: {clause_num}] [Category: {cat}] {clean_t}"

            clauses_data.append({
                "id": c.id,
                "document_id": c.document_id,
                "page": c.page_number,
                "section": sec_name,
                "clause_number": c.clause_number,
                "category": cat,
                "confidence": c.classification_confidence or 0.8,
                "text": c.original_text,
                "clean_text": clean_t,
                "search_text": search_t,
                "embedding": embedding,
            })

        expanded_query = analysis.get("expanded_query", query)
        contextual_q = analysis.get("contextualized_question", query)
        intent = analysis.get("intent", "general_qa")
        q_low = contextual_q.lower()
        distinctive_tokens = [t.lower() for t in (analysis.get("distinctive_tokens") or []) if len(t) >= 3]
        topic_syns = []
        for t in (analysis.get("all_topics") or []):
            topic_syns.append(t.replace("_", " "))

        # Optional dense similarity ONLY if explicitly enabled and already cached (never slow CPU PyTorch on upload/query)
        dense_scores: Dict[int, float] = {}
        use_dense = (
            settings.USE_NEURAL_EMBEDDINGS
            and EmbeddingService._model is not None
            and sum(1 for c in clauses_data if c["embedding"]) >= max(1, int(len(clauses_data) * 0.5))
        )
        if use_dense:
            query_embedding = EmbeddingService.encode_text(contextual_q)
            for c in clauses_data:
                if c["embedding"]:
                    sim = EmbeddingService.cosine_similarity(query_embedding, c["embedding"])
                    dense_scores[c["id"]] = max(0.0, (sim + 1.0) / 2.0)
                else:
                    dense_scores[c["id"]] = 0.0

        # Fast Hybrid Lexical Index (BM25Okapi + TF-IDF n-gram Cosine Similarity, ~30ms)
        lexical_idx = get_bm25_index(document_id, clauses_data)
        lexical_scores = lexical_idx.search_scores(expanded_query)

        category_boosts = analysis.get("category_boosts", {})
        asks_ombudsman = any(w in q_low for w in ("ombudsman", "grievance", "complaint", "escalate"))

        scored_candidates = []
        for c in clauses_data:
            cid = c["id"]
            lex = lexical_scores.get(cid, {"bm25": 0.0, "tfidf": 0.0})
            b_score = lex["bm25"]
            tf_score = lex["tfidf"]
            d_score = dense_scores.get(cid, tf_score)
            cat_score = category_boosts.get(c["category"], 0.0)

            # Exact distinctive-token stem coverage inside this clause
            t_low = c["clean_text"].lower()
            sec_low = (c["section"] or "").lower()
            tok_hits = 0
            for tok in distinctive_tokens:
                stem = tok[: max(4, len(tok) - 2)] if len(tok) >= 6 else tok
                if stem in t_low or stem in sec_low:
                    tok_hits += 1
            tok_ratio = (tok_hits / len(distinctive_tokens)) if distinctive_tokens else 0.0

            if use_dense:
                hybrid_score = (0.35 * d_score) + (0.35 * b_score) + (0.15 * tf_score) + (0.15 * cat_score)
            else:
                hybrid_score = (0.44 * b_score) + (0.34 * tf_score) + (0.14 * cat_score) + (0.08 * tok_ratio)

            # Bonus when exact query terms appear directly in section title or body
            if tok_ratio >= 0.5:
                hybrid_score += 0.14 * tok_ratio

            # Boost main Waiting Period sections when asking about waiting periods;
            # keep Exclusions from overshadowing general "What is covered?" overview queries
            if intent == "waiting_period_inquiry" and "waiting" in sec_low:
                hybrid_score += 0.14
            if analysis.get("response_style") == "list_overview" and "exclusion" not in q_low and c["category"] == "Exclusion":
                hybrid_score *= 0.55

            # Penalize structural boilerplate noise (TOC / Ombudsman) and empty stub lead-ins
            if "table of contents" in sec_low:
                hybrid_score *= 0.12
            elif ("ombudsman" in sec_low or "bimalokpal" in t_low) and not asks_ombudsman:
                hybrid_score *= 0.35

            compact_t = " ".join(c["clean_text"].split())
            if len(compact_t) < 160 and compact_t.endswith(":"):
                hybrid_score *= 0.25

            # Calibrated relevance probability [0.0..0.99] for CompletenessChecker & Citation Ranking
            cal_prob = min(0.99, max(0.0, round((0.45 * b_score) + (0.35 * tf_score) + (0.20 * tok_ratio), 4)))

            scored_candidates.append({
                **c,
                "dense_score": round(d_score, 4),
                "bm25_score": round(b_score, 4),
                "tfidf_score": round(tf_score, 4),
                "category_score": round(cat_score, 4),
                "hybrid_score": round(hybrid_score, 4),
                "rerank_score": cal_prob,
                "rerank_prob": cal_prob,
            })

        scored_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return scored_candidates[:top_k]

    @classmethod
    def fast_rerank(
        cls,
        query: str,
        candidate_clauses: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        top_k: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Zero-PyTorch fast sub-millisecond reranker combining lexical relevance,
        quantitative richness for limit/timeline queries, and section diversity.
        """
        if not candidate_clauses:
            return []

        style = analysis.get("response_style", "general_explanation")
        q_tokens = set(re.findall(r"[a-z]{3,}", (analysis.get("contextualized_question") or query).lower())) - {
            "what", "does", "this", "policy", "cover", "are", "the", "for", "with", "under", "about", "how", "much", "many"
        }

        reranked = []
        intent = analysis.get("intent", "general_qa")
        asks_definition = bool(re.search(r"\b(?:define|definition|meaning\s+of|what\s+does\s+.+\s+mean)\b", (query or "").lower()))
        asks_ped = bool(re.search(r"\b(?:pre-?existing|ped)\b", (query or "").lower()))
        dist_tokens = [t.lower() for t in (analysis.get("distinctive_tokens") or []) if len(t) >= 3]
        any_dist_hit = False
        if dist_tokens:
            for c in candidate_clauses:
                blob = f"{c.get('clean_text') or c.get('text') or ''} {c.get('section') or ''}".lower()
                if any((t[: max(4, len(t) - 2)] if len(t) >= 6 else t) in blob for t in dist_tokens):
                    any_dist_hit = True
                    break

        for idx, c in enumerate(candidate_clauses):
            txt = (c.get("clean_text") or c.get("text") or "").lower()
            sec = (c.get("section") or "").lower()
            cat = (c.get("category") or "").lower()
            base = float(c.get("hybrid_score", 0.0))

            # Reward quantitative clauses when user asks for exact limits/timelines
            quant_bonus = 0.0
            if style == "numeric_limit_timeline":
                if re.search(r"(?:₹|rs\.?|inr)\s*[\d,]+|\b\d+\s*(?:months?|days?|years?|%)\b", txt):
                    quant_bonus = 0.15

            # Boost core Pre-Existing Disease / Waiting Period clauses over tangential annexures
            specific_bonus = 0.0
            if intent == "waiting_period_inquiry":
                if asks_ped and ("pre-existing" in sec or "pre-existing" in txt or "pre existing" in txt or "excl01" in sec or "(ped)" in txt):
                    specific_bonus += 0.25
                if "waiting period" in sec:
                    specific_bonus += 0.10
                if "annexure" in sec and "waiting" not in txt:
                    specific_bonus -= 0.18

            # Keep pure glossary Definitions from outranking operative Coverage/Exclusion rules
            def_penalty = 0.0
            if not asks_definition and ("definition" in sec or re.match(r"^(?:def\.?\s*\d+|\d+\.\d+(?:\([a-z0-9]+\))?\.?\s+[A-Z][\w\s/\-()]{1,40}\s+means)\b", txt)):
                if cat not in ("exclusion", "waiting period"):
                    def_penalty = 0.22

            # Penalize off-topic neighbor chunks that contain zero distinctive query terms when matching chunks exist
            dist_penalty = 0.0
            if dist_tokens and any_dist_hit and not analysis.get("is_comprehensive"):
                blob = f"{txt} {sec}"
                if not any((t[: max(4, len(t) - 2)] if len(t) >= 6 else t) in blob for t in dist_tokens):
                    dist_penalty = 0.35

            overlap = sum(1 for t in q_tokens if t in txt or t in sec) / max(1, len(q_tokens))
            raw_rank_score = base + (0.20 * overlap) + quant_bonus + specific_bonus - def_penalty - dist_penalty

            item = dict(c)
            item["_raw_rank_score"] = raw_rank_score
            item["rerank_score"] = min(0.99, max(0.05, round(raw_rank_score, 4)))
            item["rerank_prob"] = max(float(c.get("rerank_prob", 0.0)), min(0.99, round((0.65 * overlap) + (0.35 * c.get("bm25_score", 0.0)), 4)))
            reranked.append(item)

        reranked.sort(key=lambda x: x["_raw_rank_score"], reverse=True)
        for item in reranked:
            item.pop("_raw_rank_score", None)
        return reranked[:top_k]
