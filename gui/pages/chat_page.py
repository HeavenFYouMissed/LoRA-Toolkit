"""
AI Chat Page — Chat with local Ollama models.

Features:
  • Model selector (auto-populated from Ollama)
  • Editable system prompt
  • Scrollable conversation history with styled bubbles
  • User input with Send button + Enter key binding
  • Clear chat / Export conversation
  • Connection status indicator
"""
import threading
import time
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import (
    PageHeader, ActionButton, StatusBar, Tooltip, ProgressIndicator,
)
from core.ai_cleaner import (
    chat, list_models, is_ollama_running,
    DEFAULT_MODEL, DEFAULT_API_URL,
)


class ChatPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self._messages: list[dict] = []    # full conversation history
        self._generating = False
        self._build_ui()

    # ───────────────────────────────────────────────────────────────
    # UI BUILD
    # ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Main vertical layout
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ─── Top Bar (connection + model + system prompt) ───
        top = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=0)
        top.grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        top_inner = ctk.CTkFrame(top, fg_color="transparent")
        top_inner.pack(fill="x", padx=15, pady=10)

        # Connection dot
        self.conn_dot = ctk.CTkLabel(
            top_inner, text="●", font=(FONT_FAMILY, 14),
            text_color=COLORS["text_muted"], width=18,
        )
        self.conn_dot.pack(side="left", padx=(0, 4))

        self.conn_label = ctk.CTkLabel(
            top_inner, text="Checking Ollama...",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.conn_label.pack(side="left", padx=(0, 12))

        # Model selector
        ctk.CTkLabel(
            top_inner, text="Model:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 5))

        self.model_menu = ctk.CTkOptionMenu(
            top_inner, values=[DEFAULT_MODEL],
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=200, height=30,
        )
        self.model_menu.pack(side="left", padx=(0, 8))
        Tooltip(self.model_menu, "Select which Ollama model to chat with.\nPull models from the Setup page if none appear.")

        btn_refresh = ActionButton(
            top_inner, text="🔄", command=self._refresh_models,
            style="secondary", width=35,
        )
        btn_refresh.pack(side="left", padx=(0, 15))
        Tooltip(btn_refresh, "Refresh model list from Ollama.")

        # Clear chat
        btn_clear = ActionButton(
            top_inner, text="🗑  Clear Chat", command=self._clear_chat,
            style="danger", width=120,
        )
        btn_clear.pack(side="right", padx=(8, 0))
        Tooltip(btn_clear, "Clear the entire conversation history.\nStarts a fresh chat.")

        # Export chat
        btn_export = ActionButton(
            top_inner, text="💾  Export", command=self._export_chat,
            style="secondary", width=100,
        )
        btn_export.pack(side="right", padx=(0, 0))
        Tooltip(btn_export, "Export the conversation to a .txt file\nin your data directory.")

        # System prompt row
        sp_row = ctk.CTkFrame(top, fg_color="transparent")
        sp_row.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(
            sp_row, text="System Prompt:",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_muted"],
        ).pack(side="left", padx=(0, 8))

        self.system_prompt = ctk.CTkEntry(
            sp_row,
            placeholder_text="You are a helpful assistant specializing in ...",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=8, height=32,
        )
        self.system_prompt.pack(side="left", fill="x", expand=True)
        self.system_prompt.insert(0,
            "You are a helpful AI assistant for LoRA training data preparation. "
            "You help with data cleaning, formatting, and training questions."
        )
        Tooltip(self.system_prompt,
                "Set the AI's personality and expertise.\n"
                "This is sent at the start of every conversation.\n"
                "Change it to specialise the AI for your domain.")

        # ─── Chat History (scrollable) ──────────────────────
        self.chat_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLORS["bg_dark"],
            corner_radius=0,
        )
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # Welcome message
        self._add_system_bubble(
            "👋  Welcome to AI Chat!\n\n"
            "Chat with your local Ollama model about anything — "
            "training data, LoRA configs, data cleaning strategies, or just ask questions.\n\n"
            "💡 Tip: Set a system prompt above to specialise the AI for your domain."
        )

        # ─── Input Bar (bottom) ─────────────────────────────
        input_bar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=0)
        input_bar.grid(row=2, column=0, sticky="ew", padx=0, pady=0)

        input_inner = ctk.CTkFrame(input_bar, fg_color="transparent")
        input_inner.pack(fill="x", padx=15, pady=10)

        self.user_input = ctk.CTkTextbox(
            input_inner, height=60,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=8,
            wrap="word",
        )
        self.user_input.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Bind Enter (without shift) to send
        self.user_input.bind("<Return>", self._on_enter)
        self.user_input.bind("<Shift-Return>", self._on_shift_enter)

        btn_col = ctk.CTkFrame(input_inner, fg_color="transparent")
        btn_col.pack(side="right")

        self.btn_send = ActionButton(
            btn_col, text="📤  Send", command=self._send_message,
            style="success", width=100,
        )
        self.btn_send.pack(pady=(0, 4))
        Tooltip(self.btn_send, "Send your message (or press Enter).\nShift+Enter for a new line.")

        self.btn_stop = ActionButton(
            btn_col, text="⏹  Stop", command=self._stop_generating,
            style="danger", width=100,
        )
        self.btn_stop.pack()
        self.btn_stop.configure(state="disabled")

        # Token/word counter
        self.counter_label = ctk.CTkLabel(
            input_bar, text="",
            font=(FONT_FAMILY, FONT_SIZES["tiny"]),
            text_color=COLORS["text_muted"],
        )
        self.counter_label.pack(padx=15, pady=(0, 5), anchor="w")

        # ─── Initial connection check ───────────────────────
        self.after(300, self._check_ollama)

    # ───────────────────────────────────────────────────────────────
    # CONNECTION & MODELS
    # ───────────────────────────────────────────────────────────────

    def _check_ollama(self):
        def _check():
            ok = is_ollama_running()
            models = list_models() if ok else []
            self.after(0, lambda: self._update_connection(ok, models))
        threading.Thread(target=_check, daemon=True).start()

    def _update_connection(self, online, models):
        if online:
            self.conn_dot.configure(text_color=COLORS["accent_green"])
            self.conn_label.configure(
                text=f"Ollama connected  •  {len(models)} model{'s' if len(models) != 1 else ''}",
                text_color=COLORS["accent_green"],
            )
            if models:
                self.model_menu.configure(values=models)
                current = self.model_menu.get()
                if current not in models:
                    self.model_menu.set(models[0])
        else:
            self.conn_dot.configure(text_color=COLORS["error"])
            self.conn_label.configure(
                text="Ollama not running — start it from Setup page or run 'ollama serve'",
                text_color=COLORS["error"],
            )

    def _refresh_models(self):
        self.conn_label.configure(text="Refreshing...", text_color=COLORS["text_muted"])
        self._check_ollama()

    # ───────────────────────────────────────────────────────────────
    # CHAT BUBBLES
    # ───────────────────────────────────────────────────────────────

    def _add_user_bubble(self, text: str):
        """Add a right-aligned user message bubble."""
        wrapper = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        wrapper.pack(fill="x", padx=10, pady=(6, 2))

        # Right-align
        spacer = ctk.CTkFrame(wrapper, fg_color="transparent", width=80)
        spacer.pack(side="left")

        bubble = ctk.CTkFrame(
            wrapper, fg_color=COLORS["accent"],
            corner_radius=12,
        )
        bubble.pack(side="right", padx=(0, 5))

        label = ctk.CTkLabel(
            bubble, text=text,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color="#ffffff",
            wraplength=500, justify="left",
        )
        label.pack(padx=12, pady=8)

    def _add_assistant_bubble(self, text: str):
        """Add a left-aligned assistant message bubble."""
        wrapper = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        wrapper.pack(fill="x", padx=10, pady=(2, 6))

        bubble = ctk.CTkFrame(
            wrapper, fg_color=COLORS["bg_card"],
            corner_radius=12,
        )
        bubble.pack(side="left", padx=(5, 0))

        # Spacer to limit width
        spacer = ctk.CTkFrame(wrapper, fg_color="transparent", width=80)
        spacer.pack(side="right")

        label = ctk.CTkLabel(
            bubble, text=text,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_primary"],
            wraplength=500, justify="left",
        )
        label.pack(padx=12, pady=8)

    def _add_assistant_bubble_start(self):
        """Create an empty assistant bubble and return the label for streaming."""
        wrapper = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        wrapper.pack(fill="x", padx=10, pady=(2, 6))

        bubble = ctk.CTkFrame(
            wrapper, fg_color=COLORS["bg_card"],
            corner_radius=12,
        )
        bubble.pack(side="left", padx=(5, 0))

        spacer = ctk.CTkFrame(wrapper, fg_color="transparent", width=80)
        spacer.pack(side="right")

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
        """Add a centered system/info bubble."""
        wrapper = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        wrapper.pack(fill="x", padx=30, pady=8)

        bubble = ctk.CTkFrame(
            wrapper,
            fg_color=COLORS["bg_input"],
            corner_radius=10,
        )
        bubble.pack(fill="x")

        label = ctk.CTkLabel(
            bubble, text=text,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            wraplength=550, justify="left",
        )
        label.pack(padx=15, pady=10)

    def _scroll_to_bottom(self):
        """Scroll the chat frame to the bottom."""
        self.chat_frame.update_idletasks()
        self.chat_frame._parent_canvas.yview_moveto(1.0)

    # ───────────────────────────────────────────────────────────────
    # SENDING MESSAGES
    # ───────────────────────────────────────────────────────────────

    def _on_enter(self, event):
        """Send on Enter (without Shift)."""
        self._send_message()
        return "break"  # prevent newline insertion

    def _on_shift_enter(self, event):
        """Allow Shift+Enter to insert a newline."""
        return  # let default behavior happen

    def _send_message(self):
        if self._generating:
            return

        text = self.user_input.get("1.0", "end-1c").strip()
        if not text:
            return

        if not is_ollama_running():
            self._add_system_bubble(
                "⚠️  Ollama is not running!\n\n"
                "To start Ollama:\n"
                "1. Go to the Setup / GPU page and click 'Start Ollama', or\n"
                "2. Open a terminal and run:  ollama serve\n\n"
                "If you haven't installed Ollama yet, download it from the Setup page."
            )
            self._scroll_to_bottom()
            return

        # Clear input
        self.user_input.delete("1.0", "end")

        # Add user bubble
        self._add_user_bubble(text)
        self._scroll_to_bottom()

        # Build messages list
        sys_prompt = self.system_prompt.get().strip()
        if sys_prompt and not self._messages:
            self._messages.append({"role": "system", "content": sys_prompt})

        self._messages.append({"role": "user", "content": text})

        # Create streaming bubble
        self._stream_label = self._add_assistant_bubble_start()
        self._stream_chunks: list[str] = []
        self._first_token = True

        # Start generation
        self._generating = True
        self.btn_send.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._update_counter()

        model = self.model_menu.get()
        messages_copy = list(self._messages)

        def on_token(token: str):
            def _append():
                if self._first_token:
                    self._first_token = False
                    self._stream_chunks.clear()
                self._stream_chunks.append(token)
                self._stream_label.configure(text="".join(self._stream_chunks))
                self._scroll_to_bottom()
            self.after(0, _append)

        def worker():
            t0 = time.time()
            result = chat(messages=messages_copy, model=model, on_token=on_token)
            elapsed = time.time() - t0

            def _show():
                self._generating = False
                self.btn_send.configure(state="normal")
                self.btn_stop.configure(state="disabled")

                if result["success"]:
                    reply = result["reply"]
                    self._messages.append({"role": "assistant", "content": reply})
                    self._stream_label.configure(text=reply)
                    self.counter_label.configure(
                        text=f"{len(self._messages)} messages  •  "
                             f"response in {elapsed:.1f}s  •  "
                             f"{len(reply.split())} words"
                    )
                else:
                    self._stream_label.configure(
                        text=f"❌  Error: {result['error']}"
                    )

                self._scroll_to_bottom()

            self.after(0, _show)

        threading.Thread(target=worker, daemon=True).start()

    def _stop_generating(self):
        """Cancel the current generation (best-effort)."""
        self._generating = False
        self.btn_send.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        # Keep whatever was streamed so far
        partial = "".join(self._stream_chunks) if hasattr(self, '_stream_chunks') else ""
        if partial:
            self._stream_label.configure(text=partial + "\n\n[stopped]")
            self._messages.append({"role": "assistant", "content": partial})
        else:
            if hasattr(self, '_stream_label'):
                self._stream_label.configure(text="⏹  Stopped")
        self._add_system_bubble("⏹  Generation stopped.")
        self._scroll_to_bottom()

    def _update_counter(self):
        total_words = sum(len(m["content"].split()) for m in self._messages)
        self.counter_label.configure(
            text=f"{len(self._messages)} messages  •  ~{total_words:,} words in context"
        )

    # ───────────────────────────────────────────────────────────────
    # CLEAR / EXPORT
    # ───────────────────────────────────────────────────────────────

    def _clear_chat(self):
        """Clear all messages and chat bubbles."""
        self._messages.clear()
        for widget in self.chat_frame.winfo_children():
            widget.destroy()

        self._add_system_bubble(
            "🧹  Chat cleared. Start a new conversation!"
        )
        self.counter_label.configure(text="")
        self._scroll_to_bottom()

    def _export_chat(self):
        """Export conversation to a text file."""
        if not self._messages:
            self._add_system_bubble("Nothing to export — start chatting first!")
            return

        import os
        from config import DATA_DIR

        os.makedirs(DATA_DIR, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(DATA_DIR, f"chat_export_{ts}.txt")

        lines = []
        for msg in self._messages:
            role = msg["role"].upper()
            lines.append(f"[{role}]\n{msg['content']}\n")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self._add_system_bubble(f"💾  Chat exported to:\n{path}")
        self._scroll_to_bottom()

    # ───────────────────────────────────────────────────────────────
    # REFRESH (called when page becomes visible)
    # ───────────────────────────────────────────────────────────────

    def refresh(self):
        self._check_ollama()
