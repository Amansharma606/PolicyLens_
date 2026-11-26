import os
import re
import json
import time
import atexit
import socket
import threading
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Iterator
import httpx

from app.core.config import settings
from app.core.logging import logger
from app.services.answer_validator import AnswerValidator


SYSTEM_PROMPT = """You are PolicyLens, a document-grounded insurance assistant.
Answer ONLY from the Policy Excerpts with accurate facts, numbers, waiting periods, exclusions, and inline *(Page X)* citations. Match the requested language strictly (English, Hindi in Devanagari, or conversational Hinglish in Roman script). Never output only page numbers, ellipses, or rigid headers. If unmentioned, say the PDF does not mention it."""


class LLMService:
    """
    Fast Streaming Multi-Provider Grounded Synthesis Engine.
    Provider priority:
    1. Cloud API (Groq / Gemini / OpenAI / OpenRouter) if API key configured in .env (< 1s TTFT)
    2. Local Ollama (/api/chat stream) if running on OLLAMA_BASE_URL
    3. Local bundled llama-server.exe with Qwen2.5-1.5B-Instruct GGUF (-t 6, -c 2048, ~1.5-2.5s TTFT)
    4. Socket-free llama-completion.exe fallback (for sandboxed environments)
    5. Direct factual sentence synthesizer (zero-page-stub safeguard; never prints "Refer to Page X")
    """

    _BASE_DIR = Path(__file__).resolve().parent.parent.parent
    _LLAMA_DIR = _BASE_DIR / "data" / "llama_cpp"
    _SERVER_EXE = _LLAMA_DIR / "llama-server.exe"
    _COMPLETION_EXE = _LLAMA_DIR / "llama-completion.exe"
    _SERVER_PORT = int(os.getenv("LLAMA_SERVER_PORT", "11435"))

    _server_proc: Optional[subprocess.Popen] = None
    _server_disabled: bool = False
    _server_lock = threading.Lock()
    _gguf_path_cache: Optional[str] = None

    _ollama_available: Optional[bool] = None
    _ollama_model_resolved: Optional[str] = None
    _ollama_checked_at: float = 0.0

    @classmethod
    def _has_cloud_api_key(cls) -> bool:
        return any([
            bool((settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")).strip()),
            bool((settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")).strip()),
            bool((settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")).strip()),
            bool((settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")).strip()),
        ])

    @classmethod
    def warmup(cls) -> None:
        """
        Pre-warms local LLM only when needed (no cloud key and no running Ollama).
        """
        if cls._has_cloud_api_key():
            logger.info("LLM warmup: Cloud API key configured in .env; fast cloud streaming enabled.")
            return
        if cls._probe_ollama():
            logger.info(f"LLM warmup: Local Ollama detected (model={cls._ollama_model_resolved}).")
            return
        cls._ensure_llama_server()

    @classmethod
    def _find_local_gguf(cls) -> Optional[Path]:
        if cls._gguf_path_cache and Path(cls._gguf_path_cache).exists():
            return Path(cls._gguf_path_cache)

        search_roots = [
            cls._BASE_DIR / "data" / "models",
            Path.home() / ".cache" / "huggingface" / "hub",
        ]
        candidates: List[Path] = []
        for root in search_roots:
            if root.exists():
                for p in root.rglob("*.gguf"):
                    if p.is_file() and p.stat().st_size > 50 * 1024 * 1024:
                        candidates.append(p)

        if not candidates:
            return None

        candidates.sort(
            key=lambda p: (
                0 if "qwen2.5" in p.name.lower() and "instruct" in p.name.lower() else 1,
                0 if "1.5b" in p.name.lower() else (1 if "3b" in p.name.lower() else 2),
                p.stat().st_size,
            )
        )
        cls._gguf_path_cache = str(candidates[0])
        return candidates[0]

    @classmethod
    def _shutdown_llama_server(cls):
        proc = cls._server_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        cls._server_proc = None

    @classmethod
    def _ensure_llama_server(cls) -> Optional[str]:
        if cls._server_disabled or not cls._SERVER_EXE.exists():
            return None
        gguf = cls._find_local_gguf()
        if not gguf:
            return None

        base_url = f"http://127.0.0.1:{cls._SERVER_PORT}"
        with cls._server_lock:
            if cls._server_disabled:
                return None

            try:
                r = httpx.get(f"{base_url}/health", timeout=0.6)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    return base_url
            except PermissionError:
                cls._server_disabled = True
                return None
            except Exception as e:
                if "10013" in str(e) or "forbidden" in str(e).lower():
                    cls._server_disabled = True
                    return None

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.5)
                    sock.bind(("127.0.0.1", 0))
            except Exception as sock_err:
                logger.info(f"Local TCP socket restricted ({sock_err}); using socket-free local fallback.")
                cls._server_disabled = True
                return None

            if cls._server_proc is not None and cls._server_proc.poll() is not None:
                cls._server_proc = None

            if cls._server_proc is None:
                n_threads = str(min(6, max(4, (os.cpu_count() or 8) // 2)))
                cmd = [
                    str(cls._SERVER_EXE),
                    "-m", str(gguf),
                    "--host", "127.0.0.1",
                    "--port", str(cls._SERVER_PORT),
                    "-c", "2048",
                    "-t", n_threads,
                    "--no-webui",
                ]
                logger.info(f"Starting local llama-server with {gguf.name} on port {cls._SERVER_PORT} (threads={n_threads})...")
                try:
                    cls._server_proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    atexit.register(cls._shutdown_llama_server)
                except Exception as e:
                    logger.warning(f"Failed to spawn llama-server: {e}")
                    cls._server_disabled = True
                    return None

            for _ in range(80):
                if cls._server_proc.poll() is not None:
                    cls._server_disabled = True
                    cls._server_proc = None
                    return None
                try:
                    r = httpx.get(f"{base_url}/health", timeout=0.6)
                    if r.status_code == 200 and r.json().get("status") == "ok":
                        logger.info("Local llama-server ready.")
                        return base_url
                except Exception as e:
                    if "10013" in str(e):
                        cls._server_disabled = True
                        cls._shutdown_llama_server()
                        return None
                time.sleep(0.2)

            return None

    @classmethod
    def _clean_llm_output(cls, text: str) -> str:
        if not text:
            return ""
        return text.replace("[end of text]", "").replace("<|im_end|>", "").strip()

    @classmethod
    def _probe_ollama(cls) -> bool:
        now = time.time()
        if cls._ollama_available is False and (now - cls._ollama_checked_at) < 45.0:
            return False
        base = settings.OLLAMA_BASE_URL.rstrip("/")
        try:
            if cls._ollama_available is None or (now - cls._ollama_checked_at) >= 45.0:
                cls._ollama_checked_at = now
                probe = httpx.get(f"{base}/api/tags", timeout=0.8)
                models = probe.json().get("models", []) if probe.status_code == 200 else []
                names = [m.get("name", "") for m in models if m.get("name")]
                if names:
                    pref = settings.OLLAMA_MODEL
                    matched = next((n for n in names if n == pref or n.startswith(pref.split(":")[0])), None)
                    cls._ollama_model_resolved = matched or names[0]
                    cls._ollama_available = True
                else:
                    cls._ollama_available = False
        except Exception:
            cls._ollama_available = False
            cls._ollama_checked_at = now
        return bool(cls._ollama_available)

    @classmethod
    def _stream_openai_compat(
        cls,
        url: str,
        api_key: str,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        extra_headers: Optional[Dict[str, str]] = None,
        timeout: float = 35.0,
    ) -> Optional[Iterator[str]]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)

        def _gen() -> Iterator[str]:
            try:
                with httpx.stream(
                    "POST",
                    url,
                    headers=headers,
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "top_p": 0.9,
                        "repeat_penalty": 1.18,
                        "cache_prompt": True,
                        "stream": True,
                    },
                    timeout=timeout,
                ) as resp:
                    if resp.status_code != 200:
                        logger.warning(f"Streaming completion HTTP {resp.status_code} from {url}")
                        return
                    for raw_line in resp.iter_lines():
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            obj = json.loads(payload)
                            delta = obj["choices"][0].get("delta", {}).get("content", "")
                            if delta:
                                delta = delta.replace("[end of text]", "").replace("<|im_end|>", "")
                                if delta:
                                    yield delta
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"Stream error ({url}): {e}")

        return _gen()

    @classmethod
    def _stream_cloud_provider(
        cls,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Iterator[str]]:
        groq_key = (settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")).strip()
        if groq_key:
            return cls._stream_openai_compat(
                url="https://api.groq.com/openai/v1/chat/completions",
                api_key=groq_key,
                model=settings.GROQ_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=25.0,
            )

        openai_key = (settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")).strip()
        if openai_key:
            return cls._stream_openai_compat(
                url="https://api.openai.com/v1/chat/completions",
                api_key=openai_key,
                model=settings.OPENAI_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=30.0,
            )

        or_key = (settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")).strip()
        if or_key:
            return cls._stream_openai_compat(
                url="https://openrouter.ai/api/v1/chat/completions",
                api_key=or_key,
                model=settings.OPENROUTER_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=30.0,
            )

        gemini_key = (settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")).strip()
        if gemini_key:
            def _gemini_stream() -> Iterator[str]:
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=gemini_key)
                    sys_msg = "\n".join(m["content"] for m in messages if m["role"] == "system")
                    usr_msg = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
                    model = genai.GenerativeModel(model_name=settings.GEMINI_MODEL, system_instruction=sys_msg)
                    for chunk in model.generate_content(usr_msg, stream=True):
                        txt = getattr(chunk, "text", None)
                        if txt:
                            yield txt
                except Exception as e:
                    logger.warning(f"Gemini streaming error: {e}")

            return _gemini_stream()

        return None

    @classmethod
    def _stream_ollama(cls, messages: List[Dict[str, str]], max_tokens: int, temperature: float) -> Optional[Iterator[str]]:
        if not cls._probe_ollama():
            return None
        base = settings.OLLAMA_BASE_URL.rstrip("/")
        model_name = cls._ollama_model_resolved or settings.OLLAMA_MODEL

        def _gen() -> Iterator[str]:
            try:
                with httpx.stream(
                    "POST",
                    f"{base}/api/chat",
                    json={
                        "model": model_name,
                        "messages": messages,
                        "stream": True,
                        "options": {"temperature": temperature, "num_predict": max_tokens},
                    },
                    timeout=45.0,
                ) as resp:
                    if resp.status_code != 200:
                        return
                    for raw_line in resp.iter_lines():
                        if not raw_line:
                            continue
                        try:
                            obj = json.loads(raw_line)
                            delta = obj.get("message", {}).get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"Ollama streaming error: {e}")

        return _gen()

    @classmethod
    def _stream_llama_server(
        cls,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Iterator[str]]:
        base_url = cls._ensure_llama_server()
        if not base_url:
            return None
        return cls._stream_openai_compat(
            url=f"{base_url}/v1/chat/completions",
            api_key="",
            model="local-qwen",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=60.0,
        )

    @classmethod
    def _call_llama_stdio(cls, messages: List[Dict[str, str]], max_tokens: int, temperature: float) -> Optional[str]:
        if not cls._COMPLETION_EXE.exists():
            return None
        gguf = cls._find_local_gguf()
        if not gguf:
            return None

        parts = [f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>" for m in messages]
        parts.append("<|im_start|>assistant\n")
        chatml = "\n".join(parts)

        n_threads = str(min(6, max(4, (os.cpu_count() or 8) // 2)))
        try:
            proc = subprocess.run(
                [
                    str(cls._COMPLETION_EXE),
                    "-m", str(gguf),
                    "-p", chatml,
                    "-n", str(max_tokens),
                    "--temp", str(temperature),
                    "-c", "2048",
                    "-t", n_threads,
                    "--no-display-prompt",
                    "-no-cnv",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return cls._clean_llm_output(proc.stdout)
        except Exception as e:
            logger.warning(f"llama-completion stdio error: {e}")
        return None

    @classmethod
    def invoke_llm(cls, messages: List[Dict[str, str]], max_tokens: int = 240, temperature: float = 0.1) -> Optional[str]:
        # 1. Try Cloud API stream/call first if configured
        cloud_stream = cls._stream_cloud_provider(messages, max_tokens=max_tokens, temperature=temperature)
        if cloud_stream is not None:
            collected = "".join(cloud_stream).strip()
            if collected:
                return cls._clean_llm_output(collected)

        # 2. Try Local Ollama
        ollama_stream = cls._stream_ollama(messages, max_tokens=max_tokens, temperature=temperature)
        if ollama_stream is not None:
            collected = "".join(ollama_stream).strip()
            if collected:
                return cls._clean_llm_output(collected)

        # 3. Try Local bundled llama-server
        base_url = cls._ensure_llama_server()
        if base_url:
            try:
                resp = httpx.post(
                    f"{base_url}/v1/chat/completions",
                    json={"messages": messages, "max_tokens": max_tokens, "temperature": temperature, "top_p": 0.9, "repeat_penalty": 1.18, "cache_prompt": True},
                    timeout=60.0,
                )
                if resp.status_code == 200:
                    return cls._clean_llm_output(resp.json()["choices"][0]["message"]["content"])
            except Exception as e:
                logger.warning(f"llama-server error: {e}")
                if "10013" in str(e):
                    cls._server_disabled = True

        # 4. Socket-free local llama-completion fallback
        res = cls._call_llama_stdio(messages, max_tokens=max_tokens, temperature=temperature)
        if res:
            return res

        return None

    @classmethod
    def _intent_instruction(cls, analysis: Dict[str, Any]) -> str:
        intent = analysis.get("response_style") or analysis.get("intent", "general_explanation")
        language = analysis.get("language", "english")

        if language == "hindi":
            return (
                "Instruction: Respond completely in natural Hindi (Devanagari script). Explain exact rules, limits, and exceptions from the excerpts with *(Page X)* citations.\n"
            )
        if language == "hinglish":
            return (
                "Instruction: Respond ONLY in conversational Hinglish (Roman Hindi mixed with English insurance terms — NEVER pure English sentences; use natural Hindi connectors like 'is policy mein', 'cover hota hai', 'nahi milega', 'lekin', 'ke liye'). "
                "Watch 'excluded unless' clauses carefully: if a clause excludes treatment UNLESS hospitalization is due to an accident, state clearly that routine treatment is excluded and ONLY accidental/hospitalized cases qualify. Give exact limits/conditions in 2-3 complete sentences ending with *(Page X)*.\n"
            )

        if intent in ("yes_no_verification", "coverage_inquiry"):
            return "Instruction: Open with a clear direct verdict ('Yes,' if covered or 'No,' if excluded — never say 'Yes, there is no'), paying close attention to any 'unless' exception, followed by limits and exceptions with *(Page X)*.\n"
        if intent in ("list_overview", "exclusion_inquiry", "claim_inquiry", "overview_coverage"):
            return "Instruction: Open with a 1-sentence intro plus concrete covered/excluded items in bullets with *(Page X)*.\n"
        if intent in ("numeric_limit_timeline", "waiting_period_inquiry", "limit_inquiry"):
            return "Instruction: State exact rupee limits, percentages, or waiting durations clearly with *(Page X)*.\n"
        return "Instruction: Answer in 2-3 clear plain-English sentences with exact facts and *(Page X)*.\n"

    @classmethod
    def _clean_qa_markdown(cls, raw_answer: str, citations: List[Dict[str, Any]], analysis: Dict[str, Any]) -> str:
        txt = cls._clean_llm_output(raw_answer)

        # Remove accidental rigid headers or excerpt tags
        txt = re.sub(r"(?im)^(?:#{1,4}\s*|\*\*)?(?:Direct Answer|Simple Explanation)(?:\*\*)?\s*:?\s*\n*", "", txt)
        txt = re.sub(
            r"(?im)^(?:#{1,4}\s*|\*\*)?(?:Key Conditions\s*(?:&|and)\s*Fine Print|Important Conditions)(?:\*\*)?\s*:?\s*",
            "",
            txt,
        )
        txt = re.sub(r"(?im)^[\*\[]\s*(?:Page\s+\d+\s*(?:\||,\s*Section:)|Source\s+\d+\s*[—-])[^\]\*\n]+[\*\]]\s*:?\s*\n*", "", txt)
        txt = re.sub(r"(?im)^\[(?:Excluded\s*/\s*Not\s*Covered|POLICY\s+EXCLUSION[^\]]*)\]\s*", "", txt)
        txt = re.sub(r"(?im)\n*(?:#{1,4}\s*|\*\*)?(?:Source Citations?|Evidence from Your Policy)(?:\*\*)?\s*:?[\s\S]*$", "", txt)
        txt = re.sub(r"(?is)\n*(?:is there anything else[^.!?\n]*\??|let me know if[^.!?\n]*\.?|feel free to ask[^.!?\n]*\.?)\s*$", "", txt)

        # Fix accidental self-contradicting opening like "Yes, there is no..."
        txt = re.sub(
            r"^(?:yes,?\s+(?=there\s+is\s+no|there\s+are\s+no|it\s+is\s+not|this\s+policy\s+does\s+not|no\s+explicit|no\s+coverage))",
            "No, ",
            txt,
            flags=re.IGNORECASE,
        )

        # Normalize standalone page mentions cleanly into *(Page X)*
        txt = re.sub(r"(?<!\*)\((Pages?\s+\d+(?:[\s,&\-]+\d+)*)\)(?!\*)", r"*(\1)*", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt).strip()

        # Trim incomplete trailing fragment if max_tokens cut mid-sentence without terminal punctuation
        if txt and not re.search(r"[.!?*\)]$", txt):
            last_end = max(txt.rfind("."), txt.rfind("!"), txt.rfind("?"), txt.rfind(")*"))
            if last_end > int(len(txt) * 0.45):
                cut_pt = last_end + (2 if txt[last_end:last_end + 2] == ")*" else 1)
                txt = txt[:cut_pt].strip()

        if any(ph in txt.lower() for ph in ("does not contain information about", "does not mention details about", "koi jaankari nahi", "जानकारी नहीं दी गई")):
            if not re.search(r"\b(?:yes\b|haan\b|हाँ|no\b|nahi\b|नहीं|excluded|covered|hospitali[sz]ation|accident)\b", txt.lower()):
                return AnswerValidator._generate_refusal(analysis)

        if citations and not re.search(r"\*\(Pages?\s+\d+", txt, re.IGNORECASE):
            pages = sorted(list(dict.fromkeys(c["page"] for c in citations[:3] if c.get("page"))))
            if pages:
                p_label = f"Page {pages[0]}" if len(pages) == 1 else f"Pages {', '.join(str(p) for p in pages)}"
                txt = f"{txt.rstrip()} *({p_label})*"

        return txt

    @classmethod
    def _extract_focused_snippet(cls, raw_text: str, q_tokens: List[str], char_cap: int) -> str:
        """
        Focuses long policy clauses around sentences matching queried tokens (e.g. 'dental',
        'pre-existing', '36 months') so key limits/exclusions are never truncated out.
        """
        clause_body = " ".join((raw_text or "").split())
        if len(clause_body) <= char_cap:
            return clause_body

        sents = [s.strip() for s in re.split(r"(?<=[.?!;])\s+", clause_body) if s.strip()]
        if len(sents) <= 1 or not q_tokens:
            cut = clause_body[:char_cap]
            sent_end = max(cut.rfind(". "), cut.rfind("; "))
            return cut[:sent_end + 1] if sent_end > int(char_cap * 0.5) else cut.rsplit(" ", 1)[0] + "."

        # Pick first sentence matching any query token plus adjacent context
        scored = []
        for idx, s in enumerate(sents):
            sl = s.lower()
            hits = sum(1 for tok in q_tokens if tok in sl)
            scored.append((hits, idx, s))
        best_hits = max(h for h, _, _ in scored)
        if best_hits == 0:
            cut = clause_body[:char_cap]
            sent_end = max(cut.rfind(". "), cut.rfind("; "))
            return cut[:sent_end + 1] if sent_end > int(char_cap * 0.5) else cut.rsplit(" ", 1)[0] + "."

        selected_idxs = set()
        # Keep lead sentence if short (for clause heading) + top matching sentences
        if len(sents[0]) < 120:
            selected_idxs.add(0)
        for hits, idx, _ in sorted(scored, key=lambda x: (-x[0], x[1])):
            if hits > 0:
                selected_idxs.add(idx)
                if idx + 1 < len(sents):
                    selected_idxs.add(idx + 1)

        out_parts = []
        total_len = 0
        for idx in sorted(selected_idxs):
            seg = sents[idx]
            if out_parts and total_len + len(seg) + 1 > char_cap:
                continue
            if not out_parts and len(seg) > char_cap:
                seg = seg[:char_cap].rsplit(" ", 1)[0] + "."
            out_parts.append(seg)
            total_len += len(seg) + 1
        return " ".join(out_parts)

    @classmethod
    def _build_qa_prompt(
        cls,
        question: str,
        citations: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        fast_remote = cls._has_cloud_api_key() or cls._probe_ollama()
        max_chunks = 7 if fast_remote else (5 if analysis.get("is_comprehensive") else 4)
        char_cap = 750 if fast_remote else 420

        q_tokens = list(dict.fromkeys(
            (analysis.get("distinctive_tokens") or [])
            + re.findall(r"[a-z]{4,}", (analysis.get("contextualized_question") or question).lower())
        ))
        q_tokens = [t for t in q_tokens if t not in {"what", "does", "this", "policy", "cover", "coverage", "with", "that"}]

        evidence_lines = []
        for idx, c in enumerate(citations[:max_chunks]):
            clause_body = cls._extract_focused_snippet(c["text"], q_tokens, char_cap)
            sec = c.get("section") or ""
            cat = c.get("category") or "General"
            status_prefix = ""
            if (cat == "Exclusion" or "exclusion" in sec.lower()) and not re.search(
                r"\b(?:excluded|not\s+covered|shall\s+not\s+(?:be\s+liable|cover)|does\s+not\s+cover|no\s+benefit|not\s+admissible)\b",
                clause_body.lower(),
            ):
                if re.search(r"\bunless\b|\bexcept\b", clause_body.lower()):
                    status_prefix = "[POLICY EXCLUSION — NOT COVERED EXCEPT under stated condition:] "
                else:
                    status_prefix = "[POLICY EXCLUSION — NOT COVERED:] "
            sec_tag = f" | {sec}" if sec and sec not in ("Policy Terms", "Policy Clause", "General Terms") else ""
            evidence_lines.append(f"[Page {c['page']}{sec_tag}]\n{status_prefix}{clause_body}")
        evidence_prompt = "\n\n".join(evidence_lines)

        history_text = ""
        if conversation_context:
            recent = conversation_context[-4:]
            hist_parts = [f"{m['role'].capitalize()}: {m['content'][:160]}" for m in recent]
            history_text = "Recent Conversation:\n" + "\n".join(hist_parts) + "\n\n"

        intent_rule = cls._intent_instruction(analysis)
        lang = analysis.get("language", "english")
        sys_prompt = SYSTEM_PROMPT
        if lang == "hinglish":
            sys_prompt = (
                "Aap PolicyLens AI hain. Policy Excerpts padhkar jawab SIRF conversational Hinglish "
                "(Roman Hindi words jaise 'is policy mein', 'cover hota hai', 'cover nahi hota', 'lekin', 'sirf' + English insurance terms) mein dein — "
                "pure English sentences bilkul mat likhein.\n"
                "Bhasha style examples (tathya SIRF Policy Excerpts se lein, examples copy na karein):\n"
                "- 'Nahi, samanya [Item A] is policy mein cover nahi hota hai, sirf [Condition B] ki sthiti mein cover milta hai. *(Page N)*'\n"
                "- 'Haan, [Item A] is policy mein cover hota hai, lekin [Excluded Sub-item B] aur [Limit C] lagu nahi/hote hain. *(Page N)*'\n"
                "Dhyan dein: agar clause kehta hai 'Excluded unless B', toh samanya treatment COVER NAHI hai, sirf B par cover hai."
            )
            closing = (
                "Hinglish Jawab (SIRF Hinglish Roman Hindi+English mein likhein, pure English nahi, ending with *(Page X)*):"
            )
        elif lang == "hindi":
            closing = "Hindi Answer (write ONLY in Devanagari Hindi strictly from the Policy Excerpts above):"
        else:
            closing = "Write a clear, complete factual answer grounded strictly in the Policy Excerpts above (never output only page numbers or ellipses):"

        user_prompt = (
            f"{history_text}"
            f"{intent_rule}\n"
            f"Policy Excerpts:\n{evidence_prompt}\n\n"
            f"User Question: {question}\n\n"
            f"{closing}"
        )

        return [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]

    @classmethod
    def _prepare_citations(
        cls,
        retrieved_clauses: List[Dict[str, Any]],
        analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        q_tokens: List[str] = []
        if analysis:
            q_tokens = list(analysis.get("distinctive_tokens") or [])
            if not q_tokens:
                q_tokens = re.findall(r"[a-z]{4,}", (analysis.get("expanded_query") or "").lower())

        peak_prob = max((float(c.get("rerank_prob", c.get("rerank_score", 0.5))) for c in retrieved_clauses), default=0.0)
        is_comp = bool(analysis and analysis.get("is_comprehensive"))

        candidates_filtered: List[Dict[str, Any]] = []
        for c in retrieved_clauses[:10]:
            text_snippet = (c.get("text") or "").strip()
            if not text_snippet:
                continue
            compact = " ".join(text_snippet.split())
            if len(compact) < 180 and compact.endswith(":"):
                continue
            prob = float(c.get("rerank_prob", c.get("rerank_score", 0.5)))
            low_t = compact.lower()
            has_q_overlap = any(tok in low_t for tok in q_tokens) if q_tokens else False
            if peak_prob >= 0.45 and prob < 0.05 and not has_q_overlap and not is_comp:
                continue
            candidates_filtered.append(c)

        if not candidates_filtered:
            candidates_filtered = [c for c in retrieved_clauses[:6] if (c.get("text") or "").strip()]

        if analysis and analysis.get("intent") == "exclusion_inquiry":
            excl_only = [
                c for c in candidates_filtered
                if c.get("category") == "Exclusion" or "exclusion" in (c.get("section") or "").lower()
            ]
            if excl_only:
                candidates_filtered = excl_only

        citations: List[Dict[str, Any]] = []
        seen_texts = set()
        for c in candidates_filtered[:8]:
            text_snippet = (c.get("text") or "").strip()
            if not text_snippet or text_snippet in seen_texts:
                continue
            seen_texts.add(text_snippet)
            rel_score = float(c.get("rerank_score", c.get("hybrid_score", 0.75)))
            citations.append({
                "page": c["page"],
                "section": c.get("section") or "Policy Terms",
                "clause_number": c.get("clause_number"),
                "category": c.get("category", "General"),
                "relevance_score": min(0.99, max(0.05, round(rel_score, 2))),
                "text": text_snippet,
            })
        return citations

    @classmethod
    def _synthesize_direct_fact_answer(
        cls,
        question: str,
        citations: List[Dict[str, Any]],
        analysis: Dict[str, Any],
    ) -> str:
        """
        High-signal complete-sentence factual answer built directly from retrieved policy text
        when no LLM responds or if LLM emits an incomplete/page-only stub. Never returns only page numbers.
        """
        intent = analysis.get("response_style") or analysis.get("intent", "general_explanation")
        language = analysis.get("language", "english")
        q_terms = set(re.findall(r"[a-z0-9]{3,}", (analysis.get("contextualized_question") or question).lower())) - {
            "what", "does", "this", "policy", "cover", "are", "the", "for", "with", "under", "about", "how", "much", "kya", "hai", "mein"
        }

        picked: List[Tuple[str, int]] = []
        for c in citations[:6]:
            pg = c["page"]
            raw_t = " ".join((c.get("text") or "").split())
            if not raw_t:
                continue
            sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+", raw_t) if len(s.strip()) >= 25]
            if not sents and len(raw_t) >= 25:
                sents = [raw_t]
            for s in sents:
                s = re.sub(r"^\[[^\]]+\]\s*", "", s).strip()
                if not s.endswith((".", "!", "?")):
                    s += "."
                if sum(1 for t in q_terms if t in s.lower()) > 0 or len(picked) < 2:
                    if not any(existing[:60].lower() == s[:60].lower() for existing, _ in picked):
                        picked.append((s, pg))
                if len(picked) >= 4:
                    break
            if len(picked) >= 4:
                break

        if not picked:
            return AnswerValidator._generate_refusal(analysis)

        lead_s, lead_pg = picked[0]
        all_txt_low = " ".join(s.lower() for s, _ in picked)
        is_excl = any(w in all_txt_low for w in ("not covered", "excluded", "shall not be liable", "no benefit"))
        is_cond = any(w in all_txt_low for w in ("subject to", "waiting period", "unless", "maximum", "up to", "%"))

        if intent in ("yes_no_verification", "coverage_inquiry"):
            if language == "hinglish":
                if is_excl:
                    prefix = "Nahi, is policy ke rules ke mutabik yeh expense covered nahi hai (excluded hai), jab tak koi specific exception lagu na ho:"
                elif is_cond:
                    prefix = "Haan, yeh benefit covered hai, lekin policy ki conditions aur limits ke saath:"
                else:
                    prefix = "Haan, is policy mein yeh coverage shamil hai:"
            elif language == "hindi":
                if is_excl:
                    prefix = "नहीं, पॉलिसी की शर्तों के अनुसार यह खर्च कवर नहीं है (जब तक विशेष अपवाद लागू न हो):"
                else:
                    prefix = "हाँ, इस पॉलिसी में संबंधित लाभ निम्नलिखित शर्तों के साथ कवर है:"
            else:
                if is_excl:
                    prefix = "**No**, according to the policy terms this item is excluded unless a stated exception applies:"
                elif is_cond:
                    prefix = "**Yes, it is covered**, subject to the stated policy conditions and limits:"
                else:
                    prefix = "**Yes, this is covered** under the policy terms:"
            bullets = [f"- {s} *(Page {pg})*" for s, pg in picked[:4]]
            return f"{prefix}\n\n" + "\n".join(bullets)

        intro = (
            "Is policy ke mutabik mukhya jankari aur niyam niche diye gaye hain:"
            if language == "hinglish"
            else ("पॉलिसी के अनुसार मुख्य विवरण निम्नलिखित हैं:" if language == "hindi" else f"{lead_s} *(Page {lead_pg})*")
        )
        rest_items = picked[:4] if language in ("hindi", "hinglish") else picked[1:4]
        bullets = [f"- {s} *(Page {pg})*" for s, pg in rest_items]
        return f"{intro}\n\n" + "\n".join(bullets) if bullets else intro

    @classmethod
    def stream_grounded_answer(
        cls,
        question: str,
        retrieved_clauses: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        conversation_context: Optional[List[Dict[str, str]]] = None,
        is_insufficient: bool = False,
    ) -> Iterator[Dict[str, Any]]:
        """
        Streams tokens in real time via active Cloud/Ollama/llama-server LLM,
        automatically repairing any broken page-only fragment into full factual explanations.
        """
        if is_insufficient or not retrieved_clauses:
            refusal = AnswerValidator._generate_refusal(analysis)
            words = re.findall(r"\S+\s*|\n+", refusal)
            for i in range(0, len(words), 3):
                yield {"type": "token", "token": "".join(words[i:i + 3])}
                time.sleep(0.01)
            yield {"type": "final", "answer": refusal, "status": "insufficient_evidence", "citations": []}
            return

        citations = cls._prepare_citations(retrieved_clauses, analysis=analysis)
        messages = cls._build_qa_prompt(question, citations, analysis, conversation_context)

        max_pred = 280 if (cls._has_cloud_api_key() or cls._probe_ollama()) else 140
        stream_iter = (
            cls._stream_cloud_provider(messages, max_tokens=max_pred, temperature=0.1)
            or cls._stream_ollama(messages, max_tokens=max_pred, temperature=0.1)
            or cls._stream_llama_server(messages, max_tokens=max_pred, temperature=0.1)
        )

        if stream_iter is not None:
            raw_chunks: List[str] = []
            prefix_checked = False
            buffer = ""
            for tok in stream_iter:
                raw_chunks.append(tok)
                if not prefix_checked:
                    buffer += tok
                    if len(buffer) >= 36 or "\n" in buffer:
                        cleaned_head = re.sub(
                            r"(?im)^(?:#{1,4}\s*|\*\*)?(?:Direct Answer|Simple Explanation)(?:\*\*)?\s*:?\s*\n*",
                            "",
                            buffer,
                        )
                        prefix_checked = True
                        if cleaned_head:
                            yield {"type": "token", "token": cleaned_head}
                else:
                    yield {"type": "token", "token": tok}

            if not prefix_checked and buffer:
                cleaned_head = re.sub(
                    r"(?im)^(?:#{1,4}\s*|\*\*)?(?:Direct Answer|Simple Explanation)(?:\*\*)?\s*:?\s*\n*",
                    "",
                    buffer,
                )
                if cleaned_head:
                    yield {"type": "token", "token": cleaned_head}

            raw_full = "".join(raw_chunks)
            if raw_full.strip():
                clean_ans = cls._clean_qa_markdown(raw_full, citations, analysis)
                if AnswerValidator.is_page_only_or_incomplete(clean_ans):
                    logger.warning(f"Rejected incomplete/page-only LLM stream output ({clean_ans!r}); repairing from excerpts.")
                    clean_ans = cls._synthesize_direct_fact_answer(question, citations, analysis)

                validation = AnswerValidator.validate(clean_ans, citations, analysis)
                final_cites = validation.get("citations", citations) if validation["status"] == "answered" else []
                yield {
                    "type": "final",
                    "answer": clean_ans,
                    "status": validation["status"],
                    "citations": final_cites,
                }
                return

        # Non-stream LLM / clause synthesizer fallback (never prints page-only output)
        llm_raw = cls.invoke_llm(messages, max_tokens=220, temperature=0.1)
        if llm_raw:
            final_text = cls._clean_qa_markdown(llm_raw, citations, analysis)
            if AnswerValidator.is_page_only_or_incomplete(final_text):
                final_text = cls._synthesize_direct_fact_answer(question, citations, analysis)
        else:
            final_text = cls._synthesize_direct_fact_answer(question, citations, analysis)

        validation = AnswerValidator.validate(final_text, citations, analysis)
        final_status = validation["status"]
        final_cites = citations if final_status == "answered" else []
        words = re.findall(r"\S+\s*|\n+", final_text)
        for i in range(0, len(words), 4):
            yield {"type": "token", "token": "".join(words[i:i + 4])}
            time.sleep(0.008)
        yield {
            "type": "final",
            "answer": final_text,
            "status": final_status,
            "citations": final_cites,
        }

    @classmethod
    def generate_grounded_answer(
        cls,
        question: str,
        retrieved_clauses: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        conversation_context: Optional[List[Dict[str, str]]] = None,
        is_insufficient: bool = False,
    ) -> Dict[str, Any]:
        if is_insufficient or not retrieved_clauses:
            return {
                "answer": AnswerValidator._generate_refusal(analysis),
                "status": "insufficient_evidence",
                "citations": [],
            }

        citations = cls._prepare_citations(retrieved_clauses, analysis=analysis)
        messages = cls._build_qa_prompt(question, citations, analysis, conversation_context)
        llm_raw = cls.invoke_llm(messages, max_tokens=220, temperature=0.1)

        if llm_raw:
            clean_ans = cls._clean_qa_markdown(llm_raw, citations, analysis)
            if AnswerValidator.is_page_only_or_incomplete(clean_ans):
                logger.warning(f"Rejected incomplete/page-only LLM output ({clean_ans!r}); repairing from excerpts.")
                clean_ans = cls._synthesize_direct_fact_answer(question, citations, analysis)
            validation = AnswerValidator.validate(clean_ans, citations, analysis)
            final_cites = validation.get("citations", citations) if validation["status"] == "answered" else []
            return {"answer": clean_ans, "status": validation["status"], "citations": final_cites}

        fallback_ans = cls._synthesize_direct_fact_answer(question, citations, analysis)
        validation = AnswerValidator.validate(fallback_ans, citations, analysis)
        return {
            "answer": fallback_ans,
            "status": validation["status"],
            "citations": citations if validation["status"] == "answered" else [],
        }

    @classmethod
    def _sanitize_plain_bullet(cls, raw_bullet: str) -> str:
        pt = raw_bullet.strip()
        pt = pt.replace("**", "").replace("*", "").replace("`", "")
        # Strip raw bracket section markers and table Column N: noise
        pt = re.sub(r"\[[^\]]{2,80}\]\s*", "", pt)
        pt = re.sub(r"\bColumn\s+\d+\s*:\s*", "", pt, flags=re.IGNORECASE)
        pt = re.sub(r"\s*;\s*(?=[A-Z0-9])", " — ", pt)
        # Strip leading list markers (a), iv., 12., 4.1, bullets)
        pt = re.sub(r"^(?:[-•*]|\d+(?:\.\d+)*\.?|\(?[ivxlcdm]+\)|\(?[a-z]\))\s+", "", pt, flags=re.IGNORECASE)
        pt = pt.strip(" \"'")
        pt = re.sub(
            r"^(?:Policy Overview|Coverage|Exclusion|Exclusions|Waiting Period|Waiting Periods|"
            r"Financial Limits|Limits|Conditions|Claim Process|Definitions|Eligibility)\s*:\s*",
            "",
            pt,
            flags=re.IGNORECASE,
        )
        # Collapse exact duplicated "Topic: Topic" prefix
        pt = re.sub(r"^([A-Za-z][A-Za-z\s/\-]{3,40}):\s*\1\b:?\s*", r"\1: ", pt)
        pt = re.sub(r"\s*\.{2,}$", ".", pt)
        pt = re.sub(r"\s+", " ", pt).strip()
        if pt and not re.search(r"[.!?)]$", pt):
            pt += "."
        return pt

    @classmethod
    def _deduplicate_bullets(cls, bullets: List[str]) -> List[str]:
        kept: List[str] = []
        kept_sets: List[set] = []
        for b in bullets:
            words = set(re.findall(r"[a-z0-9]{3,}", b.lower())) - {"page", "policy", "insured", "person"}
            if not words:
                continue
            is_dup = False
            for ks in kept_sets:
                union = len(words | ks)
                if union > 0 and (len(words & ks) / union) >= 0.65:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(b)
                kept_sets.append(words)
        return kept

    @classmethod
    def _deterministic_dimension_bullets(cls, selected_clauses: List[Any]) -> Tuple[str, List[str]]:
        """
        Instant clean complete-sentence plain-English bullets from verified clauses.
        """
        if not selected_clauses:
            return "Not specified in this policy document.", []

        raw_bullets: List[str] = []
        pages: List[int] = []
        for c in selected_clauses[:4]:
            pg = getattr(c, "page_number", 1)
            txt = " ".join((getattr(c, "clean_text", None) or getattr(c, "original_text", "")).split())
            # Strip raw bracket tags before sentence splitting so single-letter markers don't split cleanly
            txt_clean = re.sub(r"\[[^\]]{2,80}\]\s*", "", txt)
            sents = re.split(r"(?<=[a-zA-Z0-9\)]{2}[.?!])\s+", txt_clean)
            chosen = []
            total_len = 0
            for s in sents:
                s = s.strip()
                if len(s) < 15:
                    continue
                if chosen and total_len + len(s) > 250:
                    break
                chosen.append(s)
                total_len += len(s) + 1
                if len(chosen) >= 2:
                    break
            pt = cls._sanitize_plain_bullet(" ".join(chosen) if chosen else txt_clean)
            core_check = re.sub(r"\s*\(Pages?\s+[\d,\s]+\)\.?", "", pt).strip()
            if core_check and not core_check.endswith(":") and len(re.findall(r"[a-zA-Z0-9]{2,}", core_check)) >= 5:
                if not re.search(r"\(Pages?\s+\d+", pt, re.IGNORECASE):
                    pt = pt.rstrip(".") + f" (Page {pg})."
                raw_bullets.append(pt)
                pages.append(pg)

        bullets = cls._deduplicate_bullets(raw_bullets)[:3]
        if not bullets:
            return "Not specified in this policy document.", []

        pages_str = ", ".join(f"Page {p}" for p in sorted(set(pages)))
        first_core = re.sub(r"\s*\(Pages?\s+[\d,\s]+\)\.?", "", bullets[0]).strip()
        sents = [s.strip() for s in re.split(r"(?<=[a-zA-Z0-9\)]{2}[.?!])\s+", first_core) if len(s.strip()) >= 12]
        first_sent = sents[0] if sents else first_core
        if len(first_sent) > 220:
            first_sent = first_sent[:220].rsplit(" ", 1)[0].rstrip(".,;:") + "."
        summary = f"{first_sent.rstrip('.')} ({pages_str})."
        return summary, bullets

    @classmethod
    def synthesize_all_dimensions_once(
        cls,
        dims_clauses: Dict[str, Dict[str, Any]],
        filename: str,
    ) -> Dict[str, Tuple[str, List[str]]]:
        """
        Rewrites ALL found policy dimensions cleanly:
        - Uses ONE single fast batch LLM call when a fast remote/Ollama backend is configured.
        - Uses instant cleaned complete-sentence synthesis (< 50ms) on local CPU so lazy tab load never stalls.
        """
        results: Dict[str, Tuple[str, List[str]]] = {}
        active_items = [(k, v) for k, v in dims_clauses.items() if v.get("clauses")]
        if not active_items:
            return results

        # Precompute clean deterministic bullets first (zero latency safety net)
        for k, info in active_items:
            summary, bullets = cls._deterministic_dimension_bullets(info["clauses"])
            if bullets:
                results[k] = (summary, bullets)

        if not (cls._has_cloud_api_key() or cls._probe_ollama()):
            return results

        # Only spend 1 fast remote/Ollama batch LLM call polishing non-empty narrative dimensions
        llm_targets = [(k, info) for k, info in active_items if k != "definitions" and k in results]
        if not llm_targets:
            return results

        block_lines = []
        for k, info in llm_targets:
            c0 = info["clauses"][0]
            pg = getattr(c0, "page_number", 1)
            snip = " ".join((getattr(c0, "clean_text", None) or getattr(c0, "original_text", "")).split())[:220]
            block_lines.append(f'"{k}" (Page {pg}): {snip}')

        sys_msg = (
            "Summarize each policy dimension key into 1-2 short plain-English sentences ending with (Page X). "
            "Output ONLY valid JSON object mapping each key to a list of strings. No asterisks or ellipses."
        )
        usr_msg = f"Document: {filename}\n" + "\n".join(block_lines) + "\nReturn JSON:"

        raw = cls.invoke_llm(
            [{"role": "system", "content": sys_msg}, {"role": "user", "content": usr_msg}],
            max_tokens=450,
            temperature=0.1,
        )
        if raw:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, dict):
                        for k, info in llm_targets:
                            val = parsed.get(k)
                            if isinstance(val, list):
                                cleaned_list = []
                                pages_k = [getattr(c, "page_number", 1) for c in info["clauses"]]
                                for item in val:
                                    b = cls._sanitize_plain_bullet(str(item))
                                    core_c = re.sub(r"\s*\(Pages?\s+[\d,\s]+\)\.?", "", b).strip()
                                    if core_c and not core_c.endswith(":") and len(re.findall(r"[a-zA-Z0-9]{2,}", core_c)) >= 5:
                                        if not re.search(r"\(Pages?\s+\d+", b, re.IGNORECASE):
                                            b = b.rstrip(".") + f" (Page {pages_k[0]})."
                                        cleaned_list.append(b)
                                cleaned_list = cls._deduplicate_bullets(cleaned_list)[:3]
                                if cleaned_list:
                                    # Keep rich deterministic 2nd/3rd clauses if LLM only returned 1
                                    det_sum, det_bullets = results[k]
                                    merged = cls._deduplicate_bullets(cleaned_list + det_bullets)[:3]
                                    first_core = re.sub(r"\s*\(Pages?\s+[\d,\s]+\)\.?", "", merged[0]).strip()
                                    sents = [s.strip() for s in re.split(r"(?<=[a-zA-Z0-9\)]{2}[.?!])\s+", first_core) if len(s.strip()) >= 12]
                                    first_sent = sents[0] if sents else first_core
                                    pages_str = ", ".join(f"Page {p}" for p in sorted(set(pages_k)))
                                    results[k] = (f"{first_sent.rstrip('.')} ({pages_str}).", merged)
                except Exception as parse_err:
                    logger.debug(f"Single-call 10-dim JSON parse skipped: {parse_err}")

        return results

    @classmethod
    def synthesize_dimension_findings(
        cls,
        dim_key: str,
        dim_title: str,
        selected_clauses: List[Any],
        filename: str,
    ) -> Tuple[str, List[str]]:
        return cls._deterministic_dimension_bullets(selected_clauses)
