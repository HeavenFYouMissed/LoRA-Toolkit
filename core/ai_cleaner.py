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

DEFAULT_MODEL = "llama3.2:3b"
DEFAULT_API_URL = "http://localhost:11434"
MAX_INPUT_CHARS = 12_000  # truncate monster files

# ─── Prompt Library ────────────────────────────────────────────────

_BASE_RULES = """\
You are an expert data cleaner for LoRA / fine-tuning training datasets.
Output ONLY the cleaned text — no explanations, no markdown fences,
no "Here is the cleaned version:" preambles."""

_PROMPTS = {
    "general": """\
{base}

Clean the following raw text:
1. Remove junk: ads, navigation, footers, duplicates, boilerplate.
2. Fix grammar, spelling, and formatting.
3. Structure into clear paragraphs; use headings or bullet points where helpful.
4. Preserve factual accuracy — do NOT invent information.
5. Keep the author's voice and intent intact.

Raw input:
\"\"\"
{text}
\"\"\"

Cleaned output:""",

    "code": """\
{base}

Clean the following raw source code / technical snippet:
1. Remove surrounding junk (HTML, nav, ads, page chrome).
2. Fix indentation and formatting to be idiomatic.
3. Add brief inline comments if the intent is unclear.
4. Remove dead code, debug prints, and TODO placeholders.
5. Do NOT change logic or algorithms — preserve correctness.

Raw input:
\"\"\"
{text}
\"\"\"

Cleaned output:""",

    "forum": """\
{base}

Clean the following forum / Q&A / social media post:
1. Strip quotes of previous replies, signatures, timestamps, avatars.
2. Remove "Thanks!", "+1", reaction text, and off-topic chatter.
3. Keep only the substantive technical / informational content.
4. Merge fragmented sentences into coherent paragraphs.
5. Preserve any code blocks or command examples exactly.

Raw input:
\"\"\"
{text}
\"\"\"

Cleaned output:""",

    "technical": """\
{base}

Clean the following technical / academic / PDF-extracted text:
1. Remove page numbers, headers, footers, watermarks, table-of-contents junk.
2. Fix OCR artefacts (broken words, ligature issues, bad line breaks).
3. Re-flow paragraphs — merge lines that were split by page width.
4. Preserve tables as readable plain text (use | or indentation).
5. Keep citations and references but clean their formatting.

Raw input:
\"\"\"
{text}
\"\"\"

Cleaned output:""",

    "transcript": """\
{base}

Clean the following audio / video transcript:
1. Remove filler words (uh, um, like, you know) and stutters.
2. Fix sentence boundaries and punctuation.
3. Break into logical paragraphs by topic shift.
4. Attribute speakers if names appear; otherwise use "Speaker 1", etc.
5. Preserve technical terms, proper nouns, and quoted code verbatim.

Raw input:
\"\"\"
{text}
\"\"\"

Cleaned output:""",
}

_STRICT_SUFFIX = """

⚠ This is attempt {attempt}. Previous cleanings were NOT strict enough.
Be more aggressive:
- Cut ALL remaining fluff, filler, and redundancy.
- Make sentences shorter and factually denser.
- Remove ANY speculation, hedging, or padding.
- If the cleaned version is longer than the original, you over-generated — trim harder.
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
) -> dict:
    """
    Clean *raw_text* via Ollama.

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

    # Call Ollama HTTP API (no pip dependency required)
    try:
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


def chat(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
) -> dict:
    """
    Multi-turn chat with Ollama via /api/chat.

    *messages* is a list of {"role": "system"|"user"|"assistant", "content": "..."}.

    Returns dict:
        success: bool
        reply:   str
        error:   str (empty on success)
    """
    url = f"{api_url.rstrip('/')}/api/chat"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 4096,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
        reply = data.get("message", {}).get("content", "").strip()
        return {"success": True, "reply": reply, "error": ""}
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
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": max_tokens,
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
