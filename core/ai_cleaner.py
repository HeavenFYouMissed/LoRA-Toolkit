"""
AI Text Cleaner — uses Ollama (or compatible API) to clean training data.

Supports multiple content types with specialised prompts:
  • general   — catch-all for unknown content
  • code      — programming / source code
  • forum     — forum posts, Q&A, social media
  • technical — PDFs, research papers, docs
  • transcript — YouTube transcripts, audio dumps

Each "regenerate" bumps the attempt counter to produce a stricter prompt.
"""
import json
import urllib.request
import urllib.error

# ─── Defaults ──────────────────────────────────────────────────────

DEFAULT_MODEL = "qwen3-vl:4b-instruct"
DEFAULT_API_URL = "http://localhost:11434"
MAX_INPUT_CHARS = 24_000  # truncate monster files (increased for cloud models)

# ─── Groq Cloud ────────────────────────────────────────────────────

GROQ_API_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "llama-3.1-70b-versatile"
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]

# ─── xAI Grok (Super Grok) ────────────────────────────────────────

GROK_API_URL = "https://api.x.ai/v1"
GROK_DEFAULT_MODEL = "grok-3-mini"
GROK_MODELS = [
    "grok-3",
    "grok-3-fast",
    "grok-3-mini",
    "grok-3-mini-fast",
    "grok-2",
]

# ─── Prompt Library ────────────────────────────────────────────────

_BASE_RULES = """\
You are an expert knowledge extractor and note-taker for LoRA / fine-tuning training datasets.
Your job is to read raw, messy text and produce comprehensive, well-organized notes
that capture EVERY piece of useful information. Think like a meticulous student
attending a lecture — write detailed notes on how everything works.
Output ONLY the extracted notes — no explanations, no markdown fences,
no "Here is the cleaned version:" preambles."""

_PROMPTS = {
    "general": """\
{base}

Extract all useful knowledge from the following raw text and write detailed notes:
1. Identify every concept, technique, fact, and actionable piece of information.
2. Organize into clear sections with descriptive headings.
3. Write in complete sentences — explain things so a reader can learn from your notes alone.
4. Remove all junk: ads, navigation, footers, boilerplate, page numbers, TOC listings.
5. Do NOT just list chapter titles or headings — extract the ACTUAL content beneath them.
6. Preserve factual accuracy — do NOT invent information.
7. If the input contains mostly junk (TOC, page numbers, headers only), extract whatever
   real content exists and note what topics the source covers.

Raw input:
\"\"\"
{text}
\"\"\"

Detailed notes:""",

    "code": """\
{base}

Extract and organize the following source code / technical snippet:
1. Remove surrounding junk (HTML, nav, ads, page chrome, page numbers).
2. Fix indentation and formatting to be idiomatic.
3. Add brief inline comments explaining what each section does.
4. Remove dead code, debug prints, and TODO placeholders.
5. If there are explanations mixed with code, preserve them as comments or separate notes.
6. Do NOT change logic or algorithms — preserve correctness.

Raw input:
\"\"\"
{text}
\"\"\"

Cleaned code with notes:""",

    "forum": """\
{base}

Extract all useful knowledge from this forum / Q&A / social media discussion:
1. Strip quotes of previous replies, signatures, timestamps, avatars, page numbers.
2. Remove "Thanks!", "+1", reaction text, and off-topic chatter.
3. Extract the core question and ALL substantive answers/solutions.
4. Write clear, detailed notes covering every technique, command, and explanation shared.
5. Preserve any code blocks, command examples, and file paths exactly.
6. If multiple solutions are discussed, organize them as separate approaches.

Raw input:
\"\"\"
{text}
\"\"\"

Detailed notes:""",

    "technical": """\
{base}

You are reading a technical document, guide, research paper, or PDF extraction.
Your job is to be the most thorough note-taker imaginable — like a strict professor
who demands that every important detail is captured.

CRITICAL RULES:
1. IGNORE all table-of-contents entries, page numbers, headers, footers, watermarks,
   and navigation text. These are JUNK — do NOT reproduce them.
2. Extract ALL actual knowledge: explanations, procedures, commands, code examples,
   techniques, concepts, definitions, warnings, tips, and step-by-step instructions.
3. Write detailed, structured notes organized by topic with descriptive headings.
4. Explain each concept thoroughly — your notes should be a complete study guide.
5. Preserve ALL code examples, commands, file paths, register names, and technical values exactly.
6. Fix OCR artefacts (broken words, ligature issues, bad line breaks).
7. If the input is mostly TOC/headers/page numbers with little real content,
   extract whatever real content exists and state what topics the full document covers.
8. Do NOT just list section names — extract what each section TEACHES.

Raw input:
\"\"\"
{text}
\"\"\"

Comprehensive study notes:""",

    "transcript": """\
{base}

Extract all useful knowledge from this audio / video transcript:
1. Remove filler words (uh, um, like, you know) and stutters.
2. Fix sentence boundaries and punctuation.
3. Organize by topic — each time the subject changes, start a new section with a heading.
4. Write clear notes that capture EVERYTHING useful that was said.
5. Attribute speakers if names appear; otherwise use "Speaker 1", etc.
6. Preserve technical terms, proper nouns, code, and commands verbatim.
7. Don't just summarize — capture the full detail of explanations and instructions.

Raw input:
\"\"\"
{text}
\"\"\"

Detailed notes:""",
}

_STRICT_SUFFIX = """

⚠ This is attempt {attempt}. Previous extraction was NOT thorough enough.
Be more aggressive and detailed:
- Extract DEEPER — find every technique, command, concept, and procedure.
- Remove ALL remaining junk (TOC entries, page numbers, headers, navigation).
- Write more detailed explanations — your notes should teach, not just list.
- Organize better with clear headings and logical flow.
- If you see section titles without content, say what the section is about.
- Do NOT output table-of-contents lines, page numbers, or chapter listings.
"""


# ─── Public API ────────────────────────────────────────────────────

def detect_content_type(text: str) -> str:
    """Heuristic to guess the best cleaning prompt for *text*."""
    lower = text[:3000].lower()

    # Code detection
    code_signals = [
        "def ", "class ", "import ", "function ", "const ", "let ",
        "var ", "#include", "public static", "void ", "return ",
        "if __name__", "printf(", "System.out", "console.log",
    ]
    if sum(1 for s in code_signals if s in lower) >= 2:
        return "code"

    # Forum / social
    forum_signals = [
        "posted by", "reply", "thread", "quote:", "thanks!",
        "joined:", "reputation:", "+1", "avatar", "moderator",
        "senior member", "op ", "[quote", "originally posted",
    ]
    if sum(1 for s in forum_signals if s in lower) >= 2:
        return "forum"

    # Transcript
    transcript_signals = [
        "um ", "uh ", " like ", "you know", "speaker ",
        "[music]", "[applause]", ">> ", ">>> ",
    ]
    if sum(1 for s in transcript_signals if s in lower) >= 2:
        return "transcript"

    # Technical / PDF
    tech_signals = [
        "abstract", "references", "figure ", "table ",
        "et al.", "doi:", "isbn", "©", "proceedings",
        "journal of", "arxiv",
    ]
    if sum(1 for s in tech_signals if s in lower) >= 2:
        return "technical"

    return "general"


def clean_text(
    raw_text: str,
    content_type: str = "auto",
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
    attempt: int = 1,
    custom_instruction: str = "",
    on_token=None,
    provider: str = "local",
    groq_api_key: str = "",
    groq_model: str = GROQ_DEFAULT_MODEL,
    grok_api_key: str = "",
    grok_model: str = GROK_DEFAULT_MODEL,
) -> dict:
    """
    Clean *raw_text* via Ollama (local) or Groq (cloud).

    Returns dict:
        success: bool
        cleaned: str          — cleaned text (or original on error)
        explanation: str      — human-readable summary
        content_type: str     — detected / used type
        stats: dict           — char/word counts before & after
    """
    if not raw_text or not raw_text.strip():
        return {
            "success": False,
            "cleaned": raw_text,
            "explanation": "Input is empty — nothing to clean.",
            "content_type": "general",
            "stats": {},
        }

    # Auto-detect content type
    if content_type == "auto":
        content_type = detect_content_type(raw_text)

    # Build the prompt
    template = _PROMPTS.get(content_type, _PROMPTS["general"])
    truncated = raw_text[:MAX_INPUT_CHARS]
    prompt = template.format(base=_BASE_RULES, text=truncated)

    if custom_instruction:
        prompt += f"\n\nAdditional instruction: {custom_instruction}\n"

    if attempt > 1:
        prompt += _STRICT_SUFFIX.format(attempt=attempt)

    # Call AI backend (Ollama local, Groq cloud, or xAI Grok)
    try:
        if provider == "grok" and grok_api_key:
            cleaned = grok_generate(
                prompt, model=grok_model, api_key=grok_api_key, on_token=on_token,
            )
        elif provider == "groq" and groq_api_key:
            cleaned = groq_generate(
                prompt, model=groq_model, api_key=groq_api_key, on_token=on_token,
            )
        else:
            cleaned = _ollama_generate(prompt, model, api_url, on_token=on_token)
    except ConnectionError as e:
        return {
            "success": False,
            "cleaned": raw_text,
            "explanation": f"Cannot reach Ollama at {api_url} — is it running?\n{e}",
            "content_type": content_type,
            "stats": {},
        }
    except Exception as e:
        return {
            "success": False,
            "cleaned": raw_text,
            "explanation": f"AI error: {e}",
            "content_type": content_type,
            "stats": {},
        }

    # Stats
    orig_words = len(raw_text.split())
    clean_words = len(cleaned.split())
    stats = {
        "original_chars": len(raw_text),
        "cleaned_chars": len(cleaned),
        "original_words": orig_words,
        "cleaned_words": clean_words,
        "reduction_pct": round(
            (1 - clean_words / max(orig_words, 1)) * 100, 1
        ),
    }

    explanation = (
        f"Attempt {attempt} • {content_type} mode • "
        f"{stats['original_words']:,} → {stats['cleaned_words']:,} words "
        f"({stats['reduction_pct']:+.1f}%)"
    )

    return {
        "success": True,
        "cleaned": cleaned,
        "explanation": explanation,
        "content_type": content_type,
        "stats": stats,
    }


def list_models(api_url: str = DEFAULT_API_URL) -> list[str]:
    """Return model names available in the local Ollama instance."""
    try:
        url = f"{api_url.rstrip('/')}/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        return sorted(m["name"] for m in data.get("models", []))
    except Exception:
        return []


def is_ollama_running(api_url: str = DEFAULT_API_URL) -> bool:
    """Quick health check."""
    try:
        url = f"{api_url.rstrip('/')}/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def preload_model(model: str = DEFAULT_MODEL, api_url: str = DEFAULT_API_URL):
    """Load the model into VRAM without generating text.

    Avoids the 5-20 s cold-start delay on the first real request.
    Also sets keep_alive=30m so the model stays warm between entries.
    Silently ignores errors — this is purely a warm-up hint.
    """
    try:
        url = f"{api_url.rstrip('/')}/api/generate"
        payload = json.dumps({
            "model": model,
            "prompt": "",
            "stream": False,
            "keep_alive": "30m",
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass


def pull_model(
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
    on_progress=None,
) -> dict:
    """Pull (download) a model via Ollama's /api/pull endpoint.

    *on_progress*: optional callback ``fn(status_str)`` called with
                   progress lines like "pulling abc123... 45%".

    Returns dict:
        success: bool
        error:   str (empty on success)
    """
    url = f"{api_url.rstrip('/')}/api/pull"
    payload = json.dumps({
        "name": model,
        "stream": on_progress is not None,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            if on_progress is None:
                data = json.loads(resp.read().decode())
                status = data.get("status", "")
                if "error" in status.lower():
                    return {"success": False, "error": status}
                return {"success": True, "error": ""}
            # Streaming progress
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                status = obj.get("status", "")
                if on_progress and status:
                    on_progress(status)
                if obj.get("error"):
                    return {"success": False, "error": obj["error"]}
            return {"success": True, "error": ""}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Cannot reach Ollama: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def chat(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
    on_token=None,
    num_ctx: int | None = None,
) -> dict:
    """
    Multi-turn chat with Ollama via /api/chat.

    *messages* is a list of {"role": "system"|"user"|"assistant", "content": "..."}.
    *on_token*: optional callback ``fn(str)`` invoked for each streamed token.
    *num_ctx*: context window size.  When ``None`` it's auto-calculated from
              the total message content (word_count * 1.5 + 2048 headroom).
              This is critical — Ollama defaults to 2048 which silently
              truncates long system prompts (like those with file context).

    Returns dict:
        success: bool
        reply:   str
        error:   str (empty on success)
    """
    url = f"{api_url.rstrip('/')}/api/chat"
    stream = on_token is not None

    # Auto-size the context window so the model can actually see all content
    if num_ctx is None:
        total_words = sum(len(m["content"].split()) for m in messages)
        # ~1.3 tokens/word + 2048 headroom for response
        num_ctx = min(32768, max(4096, int(total_words * 1.5) + 2048))

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": stream,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 4096,
            "num_ctx": num_ctx,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            if not stream:
                data = json.loads(resp.read().decode())
                reply = data.get("message", {}).get("content", "").strip()
                return {"success": True, "reply": reply, "error": ""}
            # Streaming mode — read NDJSON line by line
            chunks = []
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = obj.get("message", {}).get("content", "")
                if token:
                    chunks.append(token)
                    on_token(token)
                if obj.get("done", False):
                    break
            return {"success": True, "reply": "".join(chunks).strip(), "error": ""}
    except urllib.error.URLError as e:
        return {"success": False, "reply": "", "error": f"Cannot reach Ollama: {e}"}
    except Exception as e:
        return {"success": False, "reply": "", "error": str(e)}


# ─── Internal ──────────────────────────────────────────────────────

def _ollama_generate(
    prompt: str,
    model: str,
    api_url: str,
    max_tokens: int | None = None,
    on_token=None,
) -> str:
    """Raw HTTP call to Ollama /api/generate.

    When *on_token* is provided, streams tokens one-by-one via the
    callback so the UI can display text as it arrives.  Otherwise
    waits for the full response (simpler but feels slower).

    *max_tokens* caps the response length.  When ``None`` the default
    (dynamic, based on input word count) is used — this avoids the
    model rambling for 4 096 tokens on a short input and dramatically
    speeds up cleaning.
    """
    url = f"{api_url.rstrip('/')}/api/generate"

    # Dynamic token budget: output shouldn't exceed input + 20 % headroom,
    # with a floor of 512 and a ceiling of 4096.
    if max_tokens is None:
        input_words = len(prompt.split())
        max_tokens = min(4096, max(512, int(input_words * 1.2)))

    stream = on_token is not None

    # Auto-size context window: input + output budget + headroom
    input_tokens_est = int(len(prompt.split()) * 1.3)
    num_ctx = min(32768, max(4096, input_tokens_est + max_tokens + 512))

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": max_tokens,
            "num_ctx": num_ctx,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            if not stream:
                data = json.loads(resp.read().decode())
                return data.get("response", "").strip()
            # Streaming mode — read NDJSON line by line
            chunks = []
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = obj.get("response", "")
                if token:
                    chunks.append(token)
                    on_token(token)
                if obj.get("done", False):
                    break
            return "".join(chunks).strip()
    except urllib.error.URLError as e:
        raise ConnectionError(str(e)) from e


# ─── Groq Cloud Backend ───────────────────────────────────────────

def groq_chat(
    messages: list[dict],
    model: str = GROQ_DEFAULT_MODEL,
    api_key: str = "",
    on_token=None,
) -> dict:
    """
    Multi-turn chat via Groq's OpenAI-compatible /chat/completions endpoint.

    Uses pure HTTP — no pip dependency.  Supports streaming via SSE.

    Returns dict:  {success, reply, error}
    """
    if not api_key:
        return {"success": False, "reply": "", "error": "Groq API key not set — add it in Settings."}

    url = f"{GROQ_API_URL}/chat/completions"
    stream = on_token is not None

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if not stream:
                data = json.loads(resp.read().decode())
                reply = data["choices"][0]["message"]["content"].strip()
                return {"success": True, "reply": reply, "error": ""}
            # SSE streaming — lines prefixed with "data: "
            chunks = []
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                payload_str = line[6:]  # strip "data: "
                if payload_str == "[DONE]":
                    break
                try:
                    obj = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                delta = obj.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    chunks.append(token)
                    on_token(token)
            return {"success": True, "reply": "".join(chunks).strip(), "error": ""}
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()
            err_data = json.loads(body)
            msg = err_data.get("error", {}).get("message", body[:200])
        except Exception:
            msg = body[:200] or str(e)
        return {"success": False, "reply": "", "error": f"Groq API error ({e.code}): {msg}"}
    except urllib.error.URLError as e:
        return {"success": False, "reply": "", "error": f"Cannot reach Groq: {e}"}
    except Exception as e:
        return {"success": False, "reply": "", "error": str(e)}


def groq_generate(
    prompt: str,
    model: str = GROQ_DEFAULT_MODEL,
    api_key: str = "",
    on_token=None,
) -> str:
    """Single-prompt generation via Groq (for cleaning).

    Wraps the prompt as a user message and calls groq_chat.
    Returns the cleaned text string, or raises on error.
    """
    messages = [{"role": "user", "content": prompt}]
    result = groq_chat(messages, model=model, api_key=api_key, on_token=on_token)
    if result["success"]:
        return result["reply"]
    raise ConnectionError(result["error"])


def groq_list_models(api_key: str = "") -> list[str]:
    """Fetch available models from Groq API.  Falls back to static list."""
    if not api_key:
        return list(GROQ_MODELS)
    try:
        url = f"{GROQ_API_URL}/models"
        req = urllib.request.Request(
            url, method="GET",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        names = sorted(m["id"] for m in data.get("data", []) if m.get("active", True))
        return names if names else list(GROQ_MODELS)
    except Exception:
        return list(GROQ_MODELS)


# ─── xAI Grok Backend ─────────────────────────────────────────────

def grok_chat(
    messages: list[dict],
    model: str = GROK_DEFAULT_MODEL,
    api_key: str = "",
    on_token=None,
) -> dict:
    """
    Multi-turn chat via xAI's OpenAI-compatible /chat/completions endpoint.

    Uses pure HTTP — no pip dependency.  Supports streaming via SSE.

    Returns dict:  {success, reply, error}
    """
    if not api_key:
        return {"success": False, "reply": "", "error": "xAI Grok API key not set — add it in Settings."}

    url = f"{GROK_API_URL}/chat/completions"
    stream = on_token is not None

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if not stream:
                data = json.loads(resp.read().decode())
                reply = data["choices"][0]["message"]["content"].strip()
                return {"success": True, "reply": reply, "error": ""}
            # SSE streaming — lines prefixed with "data: "
            chunks = []
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                payload_str = line[6:]  # strip "data: "
                if payload_str == "[DONE]":
                    break
                try:
                    obj = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                delta = obj.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    chunks.append(token)
                    on_token(token)
            return {"success": True, "reply": "".join(chunks).strip(), "error": ""}
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()
            err_data = json.loads(body)
            msg = err_data.get("error", {}).get("message", body[:200])
        except Exception:
            msg = body[:200] or str(e)
        return {"success": False, "reply": "", "error": f"xAI Grok API error ({e.code}): {msg}"}
    except urllib.error.URLError as e:
        return {"success": False, "reply": "", "error": f"Cannot reach xAI: {e}"}
    except Exception as e:
        return {"success": False, "reply": "", "error": str(e)}


def grok_generate(
    prompt: str,
    model: str = GROK_DEFAULT_MODEL,
    api_key: str = "",
    on_token=None,
) -> str:
    """Single-prompt generation via xAI Grok (for cleaning).

    Wraps the prompt as a user message and calls grok_chat.
    Returns the cleaned text string, or raises on error.
    """
    messages = [{"role": "user", "content": prompt}]
    result = grok_chat(messages, model=model, api_key=api_key, on_token=on_token)
    if result["success"]:
        return result["reply"]
    raise ConnectionError(result["error"])


def grok_list_models(api_key: str = "") -> list[str]:
    """Fetch available models from xAI API.  Falls back to static list."""
    if not api_key:
        return list(GROK_MODELS)
    try:
        url = f"{GROK_API_URL}/models"
        req = urllib.request.Request(
            url, method="GET",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        names = sorted(m["id"] for m in data.get("data", []))
        return names if names else list(GROK_MODELS)
    except Exception:
        return list(GROK_MODELS)
