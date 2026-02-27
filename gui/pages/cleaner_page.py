"""
AI Cleaner Page — Clean & polish library entries with local Ollama AI.

Shows a side-by-side diff (original vs cleaned) with:
  • Keep Original / Keep Cleaned / Regenerate (stricter)
  • Batch mode: processes selected entries one-by-one
  • Auto-detects content type (code, forum, technical, transcript, general)
  • User can override content type and add custom instructions
"""
import threading
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import (
    PageHeader, ActionButton, StatusBar, Tooltip, ProgressIndicator,
)
from core.database import get_all_entries, get_entry, update_entry, mark_cleaned
from core.ai_cleaner import (
    clean_text, detect_content_type, list_models,
    is_ollama_running, preload_model, DEFAULT_MODEL, DEFAULT_API_URL,
)


class CleanerPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self.entries = []           # loaded library entries
        self._queue = []            # entry IDs waiting to be cleaned
        self._queue_idx = 0
        self._current_entry = None
        self._attempt = 1
        self._cleaning = False
        self._build_ui()

    # ───────────────────────────────────────────────────────────────
    # UI BUILD
    # ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # ─── Header ─────────────────────────────────────────
        PageHeader(
            container, icon="🧹", title="AI Cleaner",
            subtitle="Clean & polish your training data with local Ollama AI",
        ).pack(fill="x", pady=(0, 12))

        # ─── Connection / Model Row ─────────────────────────
        conn_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        conn_frame.pack(fill="x", pady=(0, 10))

        conn_inner = ctk.CTkFrame(conn_frame, fg_color="transparent")
        conn_inner.pack(fill="x", padx=12, pady=10)

        # Status dot
        self.conn_dot = ctk.CTkLabel(
            conn_inner, text="●", font=(FONT_FAMILY, 14),
            text_color=COLORS["text_muted"], width=18,
        )
        self.conn_dot.pack(side="left", padx=(0, 4))

        self.conn_label = ctk.CTkLabel(
            conn_inner, text="Checking Ollama...",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.conn_label.pack(side="left", padx=(0, 12))

        # Model selector
        ctk.CTkLabel(
            conn_inner, text="Model:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 5))

        self.model_menu = ctk.CTkOptionMenu(
            conn_inner, values=[DEFAULT_MODEL],
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=200, height=30,
        )
        self.model_menu.pack(side="left", padx=(0, 8))
        Tooltip(self.model_menu, "Select which Ollama model to use for cleaning.\nSmaller models are faster; larger models produce better results.\nHit 'Refresh' to re-scan available models.")

        btn_refresh_models = ActionButton(
            conn_inner, text="🔄", command=self._refresh_models,
            style="secondary", width=35,
        )
        btn_refresh_models.pack(side="left", padx=(0, 12))
        Tooltip(btn_refresh_models, "Refresh the list of available Ollama models.")

        # Content type override
        ctk.CTkLabel(
            conn_inner, text="Type:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 5))

        self.type_menu = ctk.CTkOptionMenu(
            conn_inner,
            values=["auto", "general", "code", "forum", "technical", "transcript"],
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=130, height=30,
        )
        self.type_menu.set("auto")
        self.type_menu.pack(side="left")
        Tooltip(self.type_menu, "Override the auto-detected content type.\n"
                "• auto — let the AI guess\n"
                "• code — source code / scripts\n"
                "• forum — forum posts / Q&A\n"
                "• technical — PDFs / papers\n"
                "• transcript — audio / video transcripts\n"
                "• general — everything else")

        # ─── Entry Selection ────────────────────────────────
        sel_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        sel_frame.pack(fill="x", pady=(0, 10))

        sel_inner = ctk.CTkFrame(sel_frame, fg_color="transparent")
        sel_inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            sel_inner, text="📚 Select Entries to Clean",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(side="left", padx=(0, 10))

        btn_load = ActionButton(
            sel_inner, text="Load Library", command=self._load_entries,
            style="secondary", width=120,
        )
        btn_load.pack(side="left", padx=(0, 8))
        Tooltip(btn_load, "Load all entries from your Data Library.\nThen check the ones you want to clean.")

        btn_sel_all = ActionButton(
            sel_inner, text="Select All", command=self._select_all,
            style="secondary", width=100,
        )
        btn_sel_all.pack(side="left", padx=(0, 8))
        Tooltip(btn_sel_all, "Check all entries in the list.")

        btn_sel_none = ActionButton(
            sel_inner, text="Clear Sel.", command=self._select_none,
            style="secondary", width=100,
        )
        btn_sel_none.pack(side="left", padx=(0, 8))
        Tooltip(btn_sel_none, "Uncheck all entries.")

        self.entry_count_label = ctk.CTkLabel(
            sel_inner, text="0 entries",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.entry_count_label.pack(side="right")

        # Scrollable entry list
        self.entry_list = ctk.CTkScrollableFrame(
            sel_frame, fg_color="transparent", height=140,
        )
        self.entry_list.pack(fill="x", padx=8, pady=(0, 8))

        # Custom instruction
        instr_row = ctk.CTkFrame(sel_frame, fg_color="transparent")
        instr_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(
            instr_row, text="Custom Instruction (optional):",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w")

        self.custom_instr = ctk.CTkEntry(
            instr_row,
            placeholder_text="e.g. 'Remove all references to usernames' or 'Keep code comments in English'",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=8, height=34,
        )
        self.custom_instr.pack(fill="x", pady=(3, 0))
        Tooltip(self.custom_instr,
                "Add an extra instruction that gets appended to the cleaning prompt.\n"
                "Great for domain-specific rules like 'preserve all C++ code blocks'\n"
                "or 'remove any personally identifiable information'.")

        # Start button
        start_row = ctk.CTkFrame(sel_frame, fg_color="transparent")
        start_row.pack(fill="x", padx=12, pady=(0, 10))

        self.btn_start = ActionButton(
            start_row, text="🧹  Start Cleaning", command=self._start_batch,
            style="success", width=180,
        )
        self.btn_start.pack(side="left", padx=(0, 10))
        Tooltip(self.btn_start, "Begin cleaning selected entries one-by-one.\n"
                "Each entry gets a side-by-side review before saving.")

        self.btn_cancel = ActionButton(
            start_row, text="⏹  Cancel", command=self._cancel_batch,
            style="danger", width=100,
        )
        self.btn_cancel.pack(side="left")
        self.btn_cancel.configure(state="disabled")
        Tooltip(self.btn_cancel, "Stop after the current entry finishes.")

        # Progress
        self.progress = ProgressIndicator(container)
        self.progress.pack(fill="x", pady=(0, 10))

        # ─── Side-by-Side Review ────────────────────────────
        review_label = ctk.CTkLabel(
            container, text="📝 Review",
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["text_primary"],
        )
        review_label.pack(anchor="w", pady=(0, 4))

        # Entry info bar
        self.review_info = ctk.CTkLabel(
            container, text="No entry loaded yet",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.review_info.pack(anchor="w", pady=(0, 6))

        # Two-pane area
        pane = ctk.CTkFrame(container, fg_color="transparent")
        pane.pack(fill="both", expand=True, pady=(0, 8))
        pane.grid_columnconfigure(0, weight=1)
        pane.grid_columnconfigure(1, weight=1)
        pane.grid_rowconfigure(1, weight=1)

        # Left: Original
        ctk.CTkLabel(
            pane, text="Original",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["accent_blue"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 5))

        self.orig_word_label = ctk.CTkLabel(
            pane, text="",
            font=(FONT_FAMILY, FONT_SIZES["tiny"]),
            text_color=COLORS["text_muted"],
        )
        self.orig_word_label.grid(row=0, column=0, sticky="e", padx=(0, 8))

        self.orig_text = ctk.CTkTextbox(
            pane, height=350,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_secondary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=8, wrap="word",
        )
        self.orig_text.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=(3, 0))

        # Right: Cleaned
        ctk.CTkLabel(
            pane, text="AI Cleaned",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["accent_green"],
        ).grid(row=0, column=1, sticky="w", padx=(5, 0))

        self.clean_word_label = ctk.CTkLabel(
            pane, text="",
            font=(FONT_FAMILY, FONT_SIZES["tiny"]),
            text_color=COLORS["text_muted"],
        )
        self.clean_word_label.grid(row=0, column=1, sticky="e")

        self.clean_text = ctk.CTkTextbox(
            pane, height=350,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["accent_green"],
            border_width=1, corner_radius=8, wrap="word",
        )
        self.clean_text.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=(3, 0))

        # Decision buttons
        dec_row = ctk.CTkFrame(container, fg_color="transparent")
        dec_row.pack(fill="x", pady=(8, 4))

        self.btn_keep_orig = ActionButton(
            dec_row, text="⏪  Keep Original", command=self._keep_original,
            style="secondary", width=160,
        )
        self.btn_keep_orig.pack(side="left", padx=(0, 8))
        self.btn_keep_orig.configure(state="disabled")
        Tooltip(self.btn_keep_orig, "Discard the AI-cleaned version and keep\nthe original text unchanged.")

        self.btn_keep_clean = ActionButton(
            dec_row, text="✅  Keep Cleaned", command=self._keep_cleaned,
            style="success", width=160,
        )
        self.btn_keep_clean.pack(side="left", padx=(0, 8))
        self.btn_keep_clean.configure(state="disabled")
        Tooltip(self.btn_keep_clean, "Replace the original text in the database\nwith the AI-cleaned version.")

        self.btn_regen = ActionButton(
            dec_row, text="🔁  Regenerate (Stricter)", command=self._regenerate,
            style="warning", width=200,
        )
        self.btn_regen.pack(side="left", padx=(0, 8))
        self.btn_regen.configure(state="disabled")
        Tooltip(self.btn_regen, "Re-run the AI with a stricter prompt.\n"
                "Each regeneration is more aggressive about\n"
                "cutting fluff and improving density.")

        self.btn_skip = ActionButton(
            dec_row, text="⏭  Skip", command=self._skip_entry,
            style="secondary", width=100,
        )
        self.btn_skip.pack(side="left", padx=(0, 8))
        self.btn_skip.configure(state="disabled")
        Tooltip(self.btn_skip, "Skip this entry without saving anything\nand move to the next one in the batch.")

        self.btn_edit_save = ActionButton(
            dec_row, text="✏️  Save Edited", command=self._save_edited,
            style="primary", width=140,
        )
        self.btn_edit_save.pack(side="left")
        self.btn_edit_save.configure(state="disabled")
        Tooltip(self.btn_edit_save, "Save whatever is in the 'AI Cleaned' box\n"
                "(you can manually edit it before saving).")

        # Attempt counter
        self.attempt_label = ctk.CTkLabel(
            dec_row, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.attempt_label.pack(side="right")

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))

        # ─── Initial state ──────────────────────────────────
        self.after(300, self._check_ollama)

    # ───────────────────────────────────────────────────────────────
    # CONNECTION & MODELS
    # ───────────────────────────────────────────────────────────────

    def _check_ollama(self):
        """Background check if Ollama is reachable."""
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
                # Keep current selection if still valid
                current = self.model_menu.get()
                if current not in models:
                    self.model_menu.set(models[0])
            # Preload selected model into VRAM so first clean is instant
            threading.Thread(
                target=lambda: preload_model(self.model_menu.get()),
                daemon=True,
            ).start()
        else:
            self.conn_dot.configure(text_color=COLORS["error"])
            self.conn_label.configure(
                text="Ollama not running — start it first (ollama serve)",
                text_color=COLORS["error"],
            )

    def _refresh_models(self):
        self.conn_label.configure(text="Refreshing...", text_color=COLORS["text_muted"])
        self._check_ollama()

    # ───────────────────────────────────────────────────────────────
    # ENTRY LIST
    # ───────────────────────────────────────────────────────────────

    def _load_entries(self):
        self.entries = get_all_entries()
        self._rebuild_entry_list()

    def _rebuild_entry_list(self):
        for w in self.entry_list.winfo_children():
            w.destroy()

        self._cb_vars = {}

        from gui.theme import SOURCE_ICONS
        for entry in self.entries:
            row = ctk.CTkFrame(self.entry_list, fg_color="transparent", height=28)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            var = ctk.BooleanVar(value=False)
            self._cb_vars[entry["id"]] = var

            cb = ctk.CTkCheckBox(
                row, text="", variable=var, width=18, height=18,
                fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                border_color=COLORS["border"],
            )
            cb.pack(side="left", padx=(0, 4))

            # Cleaned indicator dot
            is_clean = bool(entry.get("cleaned_at"))
            dot_color = COLORS["accent_green"] if is_clean else COLORS["text_muted"]
            dot_char = "●" if is_clean else "○"
            dot_tip = "AI Cleaned" if is_clean else "Not cleaned yet"
            dot = ctk.CTkLabel(
                row, text=dot_char, font=(FONT_FAMILY, 10),
                text_color=dot_color, width=14,
            )
            dot.pack(side="left", padx=(0, 3))
            Tooltip(dot, dot_tip)

            icon = SOURCE_ICONS.get(entry["source_type"], "📄")
            ctk.CTkLabel(
                row, text=icon, font=(FONT_FAMILY, 11),
                text_color=COLORS["text_muted"], width=16,
            ).pack(side="left", padx=(0, 4))

            title = entry["title"][:55] + ("…" if len(entry["title"]) > 55 else "")
            ctk.CTkLabel(
                row, text=title,
                font=(FONT_FAMILY, FONT_SIZES["small"]),
                text_color=COLORS["text_primary"], anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))

            ctk.CTkLabel(
                row, text=f"{entry['word_count']:,}w",
                font=(FONT_FAMILY, FONT_SIZES["tiny"]),
                text_color=COLORS["text_muted"], width=45,
            ).pack(side="right")

            ctype = detect_content_type(entry.get("content", "")[:1000])
            ctk.CTkLabel(
                row, text=ctype[:4],
                font=(FONT_FAMILY, FONT_SIZES["tiny"]),
                text_color=COLORS["accent_blue"], width=35,
            ).pack(side="right", padx=(0, 4))

        self.entry_count_label.configure(text=f"{len(self.entries)} entries")

    def _select_all(self):
        for var in self._cb_vars.values():
            var.set(True)

    def _select_none(self):
        for var in self._cb_vars.values():
            var.set(False)

    def _get_selected_ids(self):
        return [eid for eid, var in self._cb_vars.items() if var.get()]

    # ───────────────────────────────────────────────────────────────
    # BATCH CLEANING
    # ───────────────────────────────────────────────────────────────

    def _start_batch(self):
        selected = self._get_selected_ids()
        if not selected:
            self.status.set_error("No entries selected — check some boxes first")
            return

        if not is_ollama_running():
            self._show_ollama_popup()
            return

        self._queue = selected
        self._queue_idx = 0
        self._skipped = 0
        self._saved = 0
        self._cleaning = True
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.reset()
        self.status.set_working(f"Cleaning 0/{len(self._queue)}...")
        self._process_next()

    def _show_ollama_popup(self):
        """Show a friendly popup explaining how to start Ollama."""
        popup = ctk.CTkToplevel(self)
        popup.title("Ollama Not Running")
        popup.geometry("440x280")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=COLORS["bg_dark"])
        popup.grab_set()

        # Center on parent
        popup.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - 440) // 2
        y = self.winfo_rooty() + (self.winfo_height() - 280) // 2
        popup.geometry(f"+{x}+{y}")

        inner = ctk.CTkFrame(popup, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            inner, text="🦙  Ollama Not Running",
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            inner,
            text=(
                "The AI Cleaner needs Ollama running locally.\n\n"
                "How to start:\n"
                "  1. Open a terminal and run:  ollama serve\n"
                "  2. Or go to Setup / GPU page → click 'Start Ollama'\n\n"
                "If you haven't installed Ollama yet:\n"
                "  • Go to Setup / GPU page → click 'Download Ollama'\n"
                "  • Or download from https://ollama.com"
            ),
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
            justify="left", wraplength=400,
        ).pack(anchor="w", fill="x")

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=(15, 0))

        ActionButton(
            btn_row, text="Go to Setup",
            command=lambda: (popup.destroy(), self.app.show_page("setup") if self.app else None),
            style="primary", width=130,
        ).pack(side="left", padx=(0, 8))

        ActionButton(
            btn_row, text="Close",
            command=popup.destroy,
            style="secondary", width=100,
        ).pack(side="left")

    def _cancel_batch(self):
        self._cleaning = False
        self.btn_cancel.configure(state="disabled")
        self.btn_start.configure(state="normal")
        self.progress.stop("Cancelled")
        self.status.set_status("Batch cancelled")

    def _process_next(self):
        """Clean the next entry in the queue."""
        if not self._cleaning or self._queue_idx >= len(self._queue):
            self._batch_done()
            return

        entry_id = self._queue[self._queue_idx]
        entry = get_entry(entry_id)
        if not entry or not entry.get("content", "").strip():
            self._queue_idx += 1
            self.after(10, self._process_next)
            return

        self._current_entry = entry
        self._attempt = 1
        total = len(self._queue)
        idx = self._queue_idx + 1
        frac = self._queue_idx / total
        title_short = entry["title"][:40]
        self.progress.set_progress(
            frac,
            f"[{idx}/{total}]  {title_short}  •  "
            f"{self._saved} saved, {self._skipped} skipped"
        )

        self._run_clean(entry)

    def _run_clean(self, entry):
        """Run the cleaning in a worker thread, streaming tokens live."""
        self.status.set_working(f"AI cleaning: {entry['title'][:50]}...")
        self._set_decision_buttons("disabled")

        # ── Show original immediately in left pane ──
        self.orig_text.configure(state="normal")
        self.orig_text.delete("1.0", "end")
        self.orig_text.insert("1.0", entry["content"])
        self.orig_text.configure(state="disabled")
        ow = len(entry["content"].split())
        self.orig_word_label.configure(text=f"{ow:,} words")

        # ── Clear right pane — tokens will stream in ──
        self.clean_text.delete("1.0", "end")
        self.clean_text.insert("1.0", "⏳  Waiting for AI response...")
        self.clean_word_label.configure(text="streaming...")

        title_short = entry["title"][:60]
        self.review_info.configure(
            text=f"Cleaning: #{entry['id']}  •  {title_short}  •  streaming..."
        )
        self.attempt_label.configure(text=f"Attempt {self._attempt}")

        model = self.model_menu.get()
        ctype = self.type_menu.get()
        custom = self.custom_instr.get().strip()
        attempt = self._attempt
        self._first_token = True

        def on_token(text):
            """Push each token to the UI as it arrives from Ollama."""
            def _append(t=text):
                if self._first_token:
                    self._first_token = False
                    self.clean_text.delete("1.0", "end")
                self.clean_text.insert("end", t)
            self.after(0, _append)

        def worker():
            result = clean_text(
                raw_text=entry["content"],
                content_type=ctype,
                model=model,
                attempt=attempt,
                custom_instruction=custom,
                on_token=on_token,
            )
            self.after(0, lambda: self._finalize_result(entry, result))

        threading.Thread(target=worker, daemon=True).start()

    def _finalize_result(self, entry, result):
        """Finalize after streaming — update stats, diff coloring, enable buttons."""
        ctype = result.get("content_type", "general")
        stats = result.get("stats", {})
        reduction = stats.get("reduction_pct", 0)
        idx = self._queue_idx + 1
        total = len(self._queue) if self._queue else 1
        self.review_info.configure(
            text=f"[{idx}/{total}]  #{entry['id']}  •  {entry['title'][:60]}  •  "
                 f"type: {ctype}  •  {reduction:+.1f}% words  •  {result.get('explanation', '')}"
        )

        cleaned = result.get("cleaned", "")
        if not result["success"]:
            # Error — streaming may have partial content, replace with fallback
            self.clean_text.delete("1.0", "end")
            self.clean_text.insert("1.0", cleaned)

        cw = len(cleaned.split())
        self.clean_word_label.configure(text=f"{cw:,} words")

        # Diff coloring (applies tags on top of existing streamed text)
        self._apply_diff_colors(entry["content"], cleaned)

        self.attempt_label.configure(text=f"Attempt {self._attempt}")

        if result["success"]:
            self.status.set_success(result["explanation"])
        else:
            self.status.set_error(result["explanation"])
        self._set_decision_buttons("normal")

    def _apply_diff_colors(self, original: str, cleaned: str):
        """Highlight differences between original and cleaned text with colors.

        Uses a simple line-based diff: green lines are new/changed,
        red highlights in the original pane for removed content.
        """
        try:
            import difflib
        except ImportError:
            return

        orig_lines = original.splitlines(keepends=True)
        clean_lines = cleaned.splitlines(keepends=True)

        # Configure tags for the cleaned pane
        try:
            self.clean_text._textbox.tag_configure(
                "added", foreground="#4ade80",  # green
            )
            self.clean_text._textbox.tag_configure(
                "changed", foreground="#60a5fa",  # blue
            )
        except Exception:
            return

        # Configure tags for the original pane
        try:
            self.orig_text.configure(state="normal")
            self.orig_text._textbox.tag_configure(
                "removed", foreground="#f87171",  # red
            )
        except Exception:
            pass

        matcher = difflib.SequenceMatcher(None, orig_lines, clean_lines)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                # Original: mark removed lines in red
                for line_num in range(i1, i2):
                    start = f"{line_num + 1}.0"
                    end = f"{line_num + 1}.end"
                    try:
                        self.orig_text._textbox.tag_add("removed", start, end)
                    except Exception:
                        pass
                # Cleaned: mark new lines in blue
                for line_num in range(j1, j2):
                    start = f"{line_num + 1}.0"
                    end = f"{line_num + 1}.end"
                    try:
                        self.clean_text._textbox.tag_add("changed", start, end)
                    except Exception:
                        pass
            elif tag == "delete":
                # Lines removed — mark in original
                for line_num in range(i1, i2):
                    start = f"{line_num + 1}.0"
                    end = f"{line_num + 1}.end"
                    try:
                        self.orig_text._textbox.tag_add("removed", start, end)
                    except Exception:
                        pass
            elif tag == "insert":
                # Lines added — mark in cleaned
                for line_num in range(j1, j2):
                    start = f"{line_num + 1}.0"
                    end = f"{line_num + 1}.end"
                    try:
                        self.clean_text._textbox.tag_add("added", start, end)
                    except Exception:
                        pass

        self.orig_text.configure(state="disabled")

    # ───────────────────────────────────────────────────────────────
    # DECISION BUTTONS
    # ───────────────────────────────────────────────────────────────

    def _set_decision_buttons(self, state):
        for btn in (self.btn_keep_orig, self.btn_keep_clean,
                    self.btn_regen, self.btn_skip, self.btn_edit_save):
            btn.configure(state=state)

    def _keep_original(self):
        """Skip this entry — keep original text."""
        self._skipped += 1
        self.status.set_status(f"Kept original for #{self._current_entry['id']}")
        self._advance()

    def _skip_entry(self):
        """Skip to the next entry without any action."""
        self._skipped += 1
        self.status.set_status(f"Skipped #{self._current_entry['id']}")
        self._advance()

    def _keep_cleaned(self):
        """Replace original with AI-cleaned version."""
        cleaned = self.clean_text.get("1.0", "end-1c").strip()
        if not cleaned:
            self.status.set_error("Cleaned text is empty — keeping original")
            self._advance()
            return

        update_entry(self._current_entry["id"], content=cleaned)
        mark_cleaned(self._current_entry["id"])
        self._saved += 1
        self.status.set_success(f"Updated #{self._current_entry['id']} with cleaned text")
        if self.app:
            self.app.refresh_stats()
        self._advance()

    def _save_edited(self):
        """Save whatever the user manually edited in the cleaned pane."""
        edited = self.clean_text.get("1.0", "end-1c").strip()
        if not edited:
            self.status.set_error("Nothing to save")
            return

        update_entry(self._current_entry["id"], content=edited)
        mark_cleaned(self._current_entry["id"])
        self._saved += 1
        self.status.set_success(f"Saved edited text for #{self._current_entry['id']}")
        if self.app:
            self.app.refresh_stats()
        self._advance()

    def _regenerate(self):
        """Re-run with stricter prompt."""
        if not self._current_entry:
            return
        self._attempt += 1
        self._run_clean(self._current_entry)

    def _advance(self):
        """Move to the next entry in the batch."""
        self._set_decision_buttons("disabled")
        self._queue_idx += 1
        self.after(100, self._process_next)

    def _batch_done(self):
        self._cleaning = False
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        total = len(self._queue)
        saved = getattr(self, '_saved', 0)
        skipped = getattr(self, '_skipped', 0)
        self.progress.stop(
            f"Done — {total} reviewed  •  {saved} saved  •  {skipped} skipped"
        )
        self.status.set_success(
            f"Batch complete: {total} entries reviewed, "
            f"{saved} saved, {skipped} skipped"
        )
        # Refresh entry list so cleaned dots update
        self._load_entries()

    # ───────────────────────────────────────────────────────────────
    # REFRESH (called when page becomes visible)
    # ───────────────────────────────────────────────────────────────

    def refresh(self):
        self._check_ollama()
