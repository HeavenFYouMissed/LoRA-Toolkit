"""
Data Chat Popup — Chat with your data using local Ollama AI.

Opens a full-featured chat window with selected library entries loaded
as context.  The AI can explain, compare, summarize, and generate
training data from the attached files.

Features:
  • Loads selected entries as rich system-prompt context
  • Live streaming tokens (appears word-by-word)
  • File sidebar showing attached entries + token counts
  • Export last AI response as a new library entry
  • Export entire conversation to .txt
  • CPU-friendly — works with any Ollama model
"""
import os
import time
import threading
import customtkinter as ctk

from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES, SOURCE_ICONS
from gui.widgets import ActionButton, Tooltip
from core.database import get_entry, add_entry
from core.ai_cleaner import (
    chat, list_models, is_ollama_running, preload_model, pull_model,
    DEFAULT_MODEL,
)
from core.settings import load_settings
from core.scraper import scrape_url
from config import DATA_DIR


# ── Context budgets ─────────────────────────────────────────────
# Rough estimate: 1 word ≈ 1.3 tokens for English text.
# Most models have 8k-32k context.  We reserve ~2k for the system
# preamble + conversation turns, and split the rest among files.
_MAX_CONTEXT_WORDS = 10_000          # ~13k tokens
_RESERVE_WORDS = 1_500               # for system preamble + chat
_MAX_PER_FILE_WORDS = 4_000          # single-file cap


def _truncate(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "\n\n[... truncated ...]"


def _build_context(entries: list[dict]) -> tuple[str, list[dict]]:
    """Build a system prompt context block from *entries*.

    Returns (context_string, file_summaries) where file_summaries
    is a list of dicts with id, title, word_count, truncated info.
    """
    budget = _MAX_CONTEXT_WORDS - _RESERVE_WORDS
    per_file = min(_MAX_PER_FILE_WORDS, budget // max(len(entries), 1))

    parts: list[str] = []
    summaries: list[dict] = []

    for i, entry in enumerate(entries, 1):
        raw = entry.get("content", "")
        wc = len(raw.split())
        truncated = wc > per_file
        chunk = _truncate(raw, per_file)

        header = (
            f"──── File {i}: {entry['title']} "
            f"({entry['source_type']}, {wc:,} words) ────"
        )
        parts.append(f"{header}\n{chunk}")
        summaries.append({
            "id": entry["id"],
            "title": entry["title"],
            "source_type": entry["source_type"],
            "word_count": wc,
            "truncated": truncated,
        })

    return "\n\n".join(parts), summaries


_SYSTEM_PREAMBLE = """\
You are an expert research assistant analysing the user's data files.
You can: explain code line-by-line, compare techniques across files,
summarise content, generate Q&A training pairs, rewrite text in
different formats (Alpaca, ShareGPT, ChatML), and answer deep
questions about the attached data.

When referencing content, cite the file number/title so the user
knows which source you're drawing from.

Loaded files:
{context}
"""


class DataChatPopup(ctk.CTkToplevel):
    """Popup window: chat with selected library entries."""

    def __init__(self, parent, selected_entry_ids: list[int], app=None):
        super().__init__(parent)
        self.app = app
        self._settings = load_settings()
        self.title("💬  Chat with Data")
        self.geometry("1000x700")
        self.minsize(800, 500)
        self.attributes("-topmost", False)
        self.configure(fg_color=COLORS["bg_dark"])

        # Load entries
        self._entries = [get_entry(eid) for eid in selected_entry_ids]
        self._entries = [e for e in self._entries if e]

        context_text, self._file_summaries = _build_context(self._entries)
        self._system_prompt = _SYSTEM_PREAMBLE.format(context=context_text)

        self._messages: list[dict] = [
            {"role": "system", "content": self._system_prompt},
        ]
        self._generating = False
        self._last_reply = ""

        self._build_ui()
        self.after(200, self._check_ollama)

    # ──────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Main horizontal split: sidebar | chat
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Sidebar: attached files ──────────────────────────
        sidebar = ctk.CTkFrame(self, fg_color=COLORS["bg_sidebar"], width=250)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        sb_inner = ctk.CTkFrame(sidebar, fg_color="transparent")
        sb_inner.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            sb_inner, text="📎  Attached Files",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", pady=(0, 8))

        # File list
        file_list = ctk.CTkScrollableFrame(sb_inner, fg_color="transparent")
        file_list.pack(fill="both", expand=True, pady=(0, 8))

        total_words = 0
        for i, fs in enumerate(self._file_summaries, 1):
            row = ctk.CTkFrame(file_list, fg_color=COLORS["bg_card"], corner_radius=6)
            row.pack(fill="x", pady=2)

            icon = SOURCE_ICONS.get(fs["source_type"], "📄")
            trunc_tag = " ✂️" if fs["truncated"] else ""

            ctk.CTkLabel(
                row,
                text=f"{icon} {i}. {fs['title'][:28]}{trunc_tag}",
                font=(FONT_FAMILY, FONT_SIZES["small"]),
                text_color=COLORS["text_primary"],
                anchor="w",
            ).pack(fill="x", padx=8, pady=(5, 1))

            ctk.CTkLabel(
                row,
                text=f"{fs['word_count']:,} words  •  {fs['source_type']}",
                font=(FONT_FAMILY, FONT_SIZES["tiny"]),
                text_color=COLORS["text_muted"],
                anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 5))

            total_words += fs["word_count"]

        # Stats
        est_tokens = int(total_words * 1.3)
        ctx_window = min(32768, max(4096, int(total_words * 1.5) + 2048))
        ctk.CTkLabel(
            sb_inner,
            text=(
                f"{len(self._file_summaries)} files  •  {total_words:,} words\n"
                f"~{est_tokens:,} tokens  •  ctx window: {ctx_window:,}"
            ),
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(4, 8))

        # Model selector
        ctk.CTkLabel(
            sb_inner, text="Model:",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(0, 3))

        self.model_menu = ctk.CTkOptionMenu(
            sb_inner, values=[DEFAULT_MODEL],
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=220, height=28,
        )
        self.model_menu.pack(anchor="w", pady=(0, 8))
        Tooltip(self.model_menu, "Select Ollama model.\nLarger context models work best with many files.")

        # Connection status
        self.conn_label = ctk.CTkLabel(
            sb_inner, text="Checking Ollama...",
            font=(FONT_FAMILY, FONT_SIZES["tiny"]),
            text_color=COLORS["text_muted"],
        )
        self.conn_label.pack(anchor="w", pady=(0, 6))

        # ── Action buttons in sidebar ────────────────────────
        btn_export_reply = ActionButton(
            sb_inner, text="📥  Save Reply to Library",
            command=self._export_reply_to_library,
            style="success", width=220,
        )
        btn_export_reply.pack(pady=(0, 4))
        Tooltip(btn_export_reply,
                "Save the last AI response as a new library entry.\n"
                "Great for generated training pairs, summaries, etc.")

        btn_export_chat = ActionButton(
            sb_inner, text="💾  Export Chat to File",
            command=self._export_chat_file,
            style="secondary", width=220,
        )
        btn_export_chat.pack(pady=(0, 4))
        Tooltip(btn_export_chat, "Export the entire conversation to a .txt file.")

        btn_clear = ActionButton(
            sb_inner, text="🗑  Clear Chat",
            command=self._clear_chat,
            style="danger", width=220,
        )
        btn_clear.pack(pady=(0, 4))
        Tooltip(btn_clear, "Clear conversation history (keeps files attached).")

        # ── Right: Chat area ─────────────────────────────────
        chat_col = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        chat_col.grid(row=0, column=1, sticky="nsew")
        chat_col.grid_rowconfigure(0, weight=1)
        chat_col.grid_columnconfigure(0, weight=1)

        # Chat history
        self.chat_frame = ctk.CTkScrollableFrame(
            chat_col, fg_color=COLORS["bg_dark"],
        )
        self.chat_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # Welcome
        self._add_system_bubble(
            f"📎  {len(self._file_summaries)} file(s) loaded into context.\n\n"
            "You can ask me to:\n"
            "  • Explain code line-by-line\n"
            "  • Compare techniques across files\n"
            "  • Summarise all attached content\n"
            "  • Generate Alpaca/ShareGPT training pairs\n"
            "  • Rewrite or merge entries\n\n"
            "🌐  Type /fetch <url> to load a webpage into context.\n"
            "💡 Tip: Use 'Save Reply to Library' to capture AI output as a new entry."
        )

        # Input bar
        input_bar = ctk.CTkFrame(chat_col, fg_color=COLORS["bg_card"])
        input_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        input_inner = ctk.CTkFrame(input_bar, fg_color="transparent")
        input_inner.pack(fill="x", padx=12, pady=8)

        self.user_input = ctk.CTkTextbox(
            input_inner, height=55,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=8, wrap="word",
        )
        self.user_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.user_input.bind("<Return>", self._on_enter)
        self.user_input.bind("<Shift-Return>", lambda e: None)

        btn_col = ctk.CTkFrame(input_inner, fg_color="transparent")
        btn_col.pack(side="right")

        self.btn_send = ActionButton(
            btn_col, text="📤 Send", command=self._send_message,
            style="success", width=90,
        )
        self.btn_send.pack(pady=(0, 3))

        self.btn_stop = ActionButton(
            btn_col, text="⏹ Stop", command=self._stop,
            style="danger", width=90,
        )
        self.btn_stop.pack()
        self.btn_stop.configure(state="disabled")

        # Counter
        self.counter_label = ctk.CTkLabel(
            input_bar, text="",
            font=(FONT_FAMILY, FONT_SIZES["tiny"]),
            text_color=COLORS["text_muted"],
        )
        self.counter_label.pack(padx=12, pady=(0, 5), anchor="w")

    # ──────────────────────────────────────────────────────────────
    # Connection
    # ──────────────────────────────────────────────────────────────

    def _check_ollama(self):
        def _bg():
            ok = is_ollama_running()
            models = list_models() if ok else []
            self.after(0, lambda: self._update_conn(ok, models))
        threading.Thread(target=_bg, daemon=True).start()

    def _update_conn(self, online, models):
        if online:
            self.conn_label.configure(
                text=f"✅ Ollama connected  •  {len(models)} models",
                text_color=COLORS["accent_green"],
            )

            pref_model = self._settings.get("ollama_model", DEFAULT_MODEL)

            if models:
                self.model_menu.configure(values=models)
                cur = self.model_menu.get()
                if pref_model in models:
                    self.model_menu.set(pref_model)
                elif cur not in models:
                    self.model_menu.set(models[0])

            # Auto-pull if preferred model not found
            if pref_model not in models:
                self._auto_pull_model(pref_model)
            else:
                # Preload selected model
                threading.Thread(
                    target=lambda: preload_model(self.model_menu.get()),
                    daemon=True,
                ).start()
        else:
            self.conn_label.configure(
                text="❌ Ollama not running — start from Setup page",
                text_color=COLORS["error"],
            )

    def _auto_pull_model(self, model_name: str):
        """Auto-pull the default model in background when not found."""
        self.conn_label.configure(
            text=f"⬇️ Pulling {model_name}...",
            text_color=COLORS["warning"],
        )

        def _pull():
            def on_progress(status):
                self.after(0, lambda s=status: self.conn_label.configure(
                    text=f"Pulling {model_name}: {s}"
                ))

            result = pull_model(model_name, on_progress=on_progress)

            def _done():
                if result["success"]:
                    self.conn_label.configure(
                        text=f"✅  {model_name} ready!",
                        text_color=COLORS["accent_green"],
                    )
                    models = list_models()
                    if models:
                        self.model_menu.configure(values=models)
                        if model_name in models:
                            self.model_menu.set(model_name)
                    threading.Thread(
                        target=lambda: preload_model(model_name),
                        daemon=True,
                    ).start()
                else:
                    self.conn_label.configure(
                        text=f"⚠ Pull failed: {result['error'][:50]}",
                        text_color=COLORS["error"],
                    )
            self.after(0, _done)

        threading.Thread(target=_pull, daemon=True).start()

    # ──────────────────────────────────────────────────────────────
    # Chat bubbles
    # ──────────────────────────────────────────────────────────────

    def _add_user_bubble(self, text: str):
        wrapper = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        wrapper.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkFrame(wrapper, fg_color="transparent", width=80).pack(side="left")
        bubble = ctk.CTkFrame(wrapper, fg_color=COLORS["accent"], corner_radius=12)
        bubble.pack(side="right", padx=(0, 5))
        ctk.CTkLabel(
            bubble, text=text, font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color="#ffffff", wraplength=500, justify="left",
        ).pack(padx=12, pady=8)

    def _add_assistant_bubble_start(self):
        """Create an empty assistant bubble and return the label for streaming."""
        wrapper = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        wrapper.pack(fill="x", padx=10, pady=(2, 6))
        bubble = ctk.CTkFrame(wrapper, fg_color=COLORS["bg_card"], corner_radius=12)
        bubble.pack(side="left", padx=(5, 0))
        ctk.CTkFrame(wrapper, fg_color="transparent", width=80).pack(side="right")

        label = ctk.CTkLabel(
            bubble, text="💭  Thinking...",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_primary"],
            wraplength=500, justify="left",
        )
        label.pack(padx=12, pady=8)
        self._scroll_to_bottom()
        return label

    def _add_system_bubble(self, text: str):
        wrapper = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        wrapper.pack(fill="x", padx=20, pady=6)
        bubble = ctk.CTkFrame(wrapper, fg_color=COLORS["bg_input"], corner_radius=10)
        bubble.pack(fill="x")
        ctk.CTkLabel(
            bubble, text=text, font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"], wraplength=500, justify="left",
        ).pack(padx=14, pady=8)

    def _scroll_to_bottom(self):
        self.chat_frame.update_idletasks()
        self.chat_frame._parent_canvas.yview_moveto(1.0)

    # ──────────────────────────────────────────────────────────────
    # Sending messages
    # ──────────────────────────────────────────────────────────────

    def _on_enter(self, event):
        self._send_message()
        return "break"

    def _send_message(self):
        if self._generating:
            return

        text = self.user_input.get("1.0", "end-1c").strip()
        if not text:
            return

        # ── Handle /fetch URL command ────────────────────────
        if text.lower().startswith("/fetch "):
            url = text[7:].strip()
            if url:
                self._fetch_url(url)
                return

        if not is_ollama_running():
            self._add_system_bubble(
                "⚠️  Ollama is not running!\n"
                "Start it from the Setup page or run 'ollama serve' in a terminal."
            )
            self._scroll_to_bottom()
            return

        # Clear input + show user bubble
        self.user_input.delete("1.0", "end")
        self._add_user_bubble(text)
        self._scroll_to_bottom()

        self._messages.append({"role": "user", "content": text})

        # Create streaming assistant bubble
        self._stream_label = self._add_assistant_bubble_start()
        self._stream_chunks: list[str] = []
        self._first_token = True

        self._generating = True
        self.btn_send.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._update_counter()

        model = self.model_menu.get()
        messages_copy = list(self._messages)

        # Context window from settings (0 = auto)
        settings_ctx = self._settings.get("ollama_num_ctx", 0)
        num_ctx = settings_ctx if settings_ctx > 0 else None

        def on_token(token: str):
            def _append():
                if self._first_token:
                    self._first_token = False
                    self._stream_chunks.clear()
                self._stream_chunks.append(token)
                self._stream_label.configure(
                    text="".join(self._stream_chunks)
                )
                self._scroll_to_bottom()
            self.after(0, _append)

        def worker():
            t0 = time.time()
            result = chat(
                messages=messages_copy,
                model=model,
                on_token=on_token,
                num_ctx=num_ctx,
            )
            elapsed = time.time() - t0

            def _done():
                self._generating = False
                self.btn_send.configure(state="normal")
                self.btn_stop.configure(state="disabled")

                if result["success"]:
                    reply = result["reply"]
                    self._last_reply = reply
                    self._messages.append({"role": "assistant", "content": reply})
                    self._stream_label.configure(text=reply)
                    self.counter_label.configure(
                        text=f"{len(self._messages)} msgs  •  "
                             f"{elapsed:.1f}s  •  {len(reply.split())} words"
                    )
                else:
                    self._stream_label.configure(
                        text=f"❌  Error: {result['error']}"
                    )

                self._scroll_to_bottom()
            self.after(0, _done)

        threading.Thread(target=worker, daemon=True).start()

    def _fetch_url(self, url: str):
        """Fetch a URL's content and inject it into the conversation context."""
        self.user_input.delete("1.0", "end")
        self._add_user_bubble(f"/fetch {url}")
        self._add_system_bubble(f"🌐  Fetching {url} ...")
        self._scroll_to_bottom()

        def _bg():
            result = scrape_url(url)
            def _done():
                if result["success"] and result["content"]:
                    content = result["content"]
                    words = len(content.split())
                    if words > 6000:
                        content = " ".join(content.split()[:6000]) + "\n\n[... truncated ...]"
                        words = 6000

                    title = result.get("title", url)
                    context_msg = (
                        f"The user fetched this webpage. Use it to answer their questions.\n\n"
                        f"── {title} ──\n{content}"
                    )
                    self._messages.append({"role": "system", "content": context_msg})

                    self._add_system_bubble(
                        f"✅  Loaded: {title}\n"
                        f"{words:,} words added to context.\n\n"
                        "💡 Now ask a question about this page!"
                    )
                else:
                    error = result.get("error", "Unknown error")
                    self._add_system_bubble(f"❌  Failed to fetch URL: {error}")

                self._update_counter()
                self._scroll_to_bottom()
            self.after(0, _done)

        threading.Thread(target=_bg, daemon=True).start()

    def _stop(self):
        self._generating = False
        self.btn_send.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        partial = "".join(self._stream_chunks) if hasattr(self, '_stream_chunks') else ""
        if partial:
            self._last_reply = partial
            self._messages.append({"role": "assistant", "content": partial})
        self._add_system_bubble("⏹  Generation stopped.")
        self._scroll_to_bottom()

    def _update_counter(self):
        total_words = sum(len(m["content"].split()) for m in self._messages)
        self.counter_label.configure(
            text=f"{len(self._messages)} msgs  •  ~{total_words:,} words in context"
        )

    # ──────────────────────────────────────────────────────────────
    # Clear / Export
    # ──────────────────────────────────────────────────────────────

    def _clear_chat(self):
        """Clear conversation but keep files attached."""
        # Keep system message, drop the rest
        self._messages = [self._messages[0]] if self._messages else []
        self._last_reply = ""
        for w in self.chat_frame.winfo_children():
            w.destroy()
        self._add_system_bubble(
            "🧹  Chat cleared.  Files are still attached — ask a new question!"
        )
        self.counter_label.configure(text="")
        self._scroll_to_bottom()

    def _export_reply_to_library(self):
        """Save the last AI reply as a new library entry."""
        if not self._last_reply.strip():
            self._add_system_bubble("⚠️  No AI reply to save yet — send a message first.")
            self._scroll_to_bottom()
            return

        # Build a title from the first line
        first_line = self._last_reply.strip().split("\n")[0][:80]
        title = f"AI Generated: {first_line}"

        entry_id = add_entry(
            title=title,
            content=self._last_reply,
            source_type="paste",
            source_url="",
            tags="ai-generated, data-chat",
            category="generated",
        )

        self._add_system_bubble(
            f"✅  Saved as library entry #{entry_id}\n"
            f"Title: {title}\n"
            f"Tags: ai-generated, data-chat\n\n"
            "Find it in the Data Library or export it for training."
        )
        self._scroll_to_bottom()

        if self.app:
            self.app.refresh_stats()

    def _export_chat_file(self):
        """Export conversation to .txt file."""
        if len(self._messages) <= 1:
            self._add_system_bubble("Nothing to export — start chatting first!")
            return

        os.makedirs(DATA_DIR, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(DATA_DIR, f"data_chat_{ts}.txt")

        lines = [
            f"Data Chat Export — {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Files: {', '.join(fs['title'] for fs in self._file_summaries)}",
            "=" * 60, "",
        ]
        for msg in self._messages:
            if msg["role"] == "system":
                continue  # skip the massive context block
            role = msg["role"].upper()
            lines.append(f"[{role}]\n{msg['content']}\n")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self._add_system_bubble(f"💾  Exported to:\n{path}")
        self._scroll_to_bottom()
