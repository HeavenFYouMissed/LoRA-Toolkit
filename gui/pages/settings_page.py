"""
Settings Page - Configure app behavior, hotkeys, tray, and export defaults.
"""
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, ActionButton, StatusBar, Tooltip
from core.settings import load_settings, save_settings, DEFAULTS


class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self.settings = load_settings()
        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # Header
        PageHeader(
            container, icon="⚙️", title="Settings",
            subtitle="Configure app behavior, hotkeys, system tray, and defaults"
        ).pack(fill="x", pady=(0, 15))

        # ─── General Section ────────────────────────────────
        self._section_label(container, "🖥️  General")

        gen_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        gen_frame.pack(fill="x", pady=(0, 15))

        # Minimize to tray
        self.tray_var = ctk.BooleanVar(value=self.settings["minimize_to_tray"])
        tray_cb = ctk.CTkCheckBox(
            gen_frame, text="Minimize to system tray instead of taskbar",
            variable=self.tray_var,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
        )
        tray_cb.pack(anchor="w", padx=15, pady=(12, 4))
        Tooltip(tray_cb, "When you close/minimize the window, it hides to\nthe system tray (hidden icons area) instead of closing.\nRight-click the tray icon to show, quick-capture, or quit.")

        # Always on top
        self.ontop_var = ctk.BooleanVar(value=self.settings["always_on_top"])
        ontop_cb = ctk.CTkCheckBox(
            gen_frame, text="Always on top",
            variable=self.ontop_var,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
        )
        ontop_cb.pack(anchor="w", padx=15, pady=(4, 4))
        Tooltip(ontop_cb, "Keep the app window above all other windows.\nUseful when copy-pasting from a browser.")

        # Window opacity
        opacity_row = ctk.CTkFrame(gen_frame, fg_color="transparent")
        opacity_row.pack(fill="x", padx=15, pady=(8, 12))

        ctk.CTkLabel(
            opacity_row, text="Window Opacity:",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.opacity_var = ctk.DoubleVar(value=self.settings["window_opacity"])
        opacity_slider = ctk.CTkSlider(
            opacity_row, from_=0.5, to=1.0,
            variable=self.opacity_var,
            width=200,
            fg_color=COLORS["bg_input"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        opacity_slider.pack(side="left", padx=(0, 8))
        Tooltip(opacity_slider, "Adjust window transparency.\nLeft = more transparent, Right = fully opaque.\nDefault is 0.97 (very subtle).")

        self.opacity_label = ctk.CTkLabel(
            opacity_row, text=f"{self.settings['window_opacity']:.0%}",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_muted"],
            width=50,
        )
        self.opacity_label.pack(side="left")
        self.opacity_var.trace_add("write", self._update_opacity_label)

        # ─── Hotkeys Section ────────────────────────────────
        self._section_label(container, "⌨️  Global Hotkeys")

        hk_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        hk_frame.pack(fill="x", pady=(0, 15))

        hk_info = ctk.CTkLabel(
            hk_frame,
            text="💡 Hotkeys work system-wide even when the app is minimized/hidden.\n"
                 "   Format: ctrl+shift+l, alt+f9, ctrl+alt+o, etc. Leave blank to disable.",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            justify="left",
        )
        hk_info.pack(anchor="w", padx=15, pady=(12, 8))

        self.hk_show = self._hotkey_row(
            hk_frame, "Show / Hide App:",
            self.settings["hotkey_show_hide"],
            "Toggle the app window visibility from anywhere.\nPress the combo to pop the app up or hide it."
        )
        self.hk_ocr = self._hotkey_row(
            hk_frame, "Quick OCR (Clipboard):",
            self.settings["hotkey_quick_ocr"],
            "Opens the app, switches to OCR page, and\nimmediately runs OCR on your clipboard screenshot.\nWorkflow: Win+Shift+S → this hotkey → done."
        )
        self.hk_paste = self._hotkey_row(
            hk_frame, "Quick Paste (Clipboard):",
            self.settings["hotkey_quick_paste"],
            "Opens the app, switches to Paste page, and\npastes clipboard text ready for saving.",
        )

        # Bottom padding
        ctk.CTkFrame(hk_frame, height=8, fg_color="transparent").pack()

        # ─── OCR Section ────────────────────────────────────
        self._section_label(container, "📸  OCR Settings")

        ocr_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        ocr_frame.pack(fill="x", pady=(0, 15))

        tess_row = ctk.CTkFrame(ocr_frame, fg_color="transparent")
        tess_row.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(
            tess_row, text="Tesseract Path:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        self.tess_entry = ctk.CTkEntry(
            tess_row,
            placeholder_text="Leave blank for auto-detect (C:\\Program Files\\Tesseract-OCR\\tesseract.exe)",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=35,
        )
        self.tess_entry.pack(fill="x", pady=(4, 0))
        if self.settings["tesseract_path"]:
            self.tess_entry.insert(0, self.settings["tesseract_path"])
        Tooltip(self.tess_entry, "Full path to tesseract.exe on your system.\nLeave blank to auto-detect common install locations.\nDownload from: github.com/UB-Mannheim/tesseract/wiki")

        # ─── AI / Ollama Section ────────────────────────────
        self._section_label(container, "🤖  AI / Ollama")

        ai_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        ai_frame.pack(fill="x", pady=(0, 15))

        # Ollama URL
        url_row = ctk.CTkFrame(ai_frame, fg_color="transparent")
        url_row.pack(fill="x", padx=15, pady=(12, 6))

        ctk.CTkLabel(
            url_row, text="Ollama URL:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.ollama_url_entry = ctk.CTkEntry(
            url_row, width=300,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=8, height=32,
            placeholder_text="http://localhost:11434",
        )
        self.ollama_url_entry.pack(side="left")
        self.ollama_url_entry.insert(0, self.settings.get("ollama_url", DEFAULTS["ollama_url"]))
        Tooltip(self.ollama_url_entry,
                "The URL where Ollama is running.\n"
                "Default: http://localhost:11434\n"
                "Change this if Ollama runs on another machine.")

        # Default model
        model_row = ctk.CTkFrame(ai_frame, fg_color="transparent")
        model_row.pack(fill="x", padx=15, pady=(0, 6))

        ctk.CTkLabel(
            model_row, text="Default Model:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.ollama_model_entry = ctk.CTkEntry(
            model_row, width=200,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=8, height=32,
            placeholder_text="qwen3-vl:4b-instruct",
        )
        self.ollama_model_entry.pack(side="left")
        self.ollama_model_entry.insert(0, self.settings.get("ollama_model", DEFAULTS["ollama_model"]))
        Tooltip(self.ollama_model_entry,
                "Default Ollama model for AI Cleaner and Chat.\n"
                "Auto-pulled on first run if not available.\n"
                "Examples: qwen3-vl:4b-instruct, llama3.2:3b, mistral:7b")

        ai_hint = ctk.CTkLabel(
            ai_frame,
            text="💡  Pull models from the Setup / GPU page.  "
                 "Smaller models (3B) are faster, larger models (7B+) give better results.",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            wraplength=600, justify="left",
        )
        ai_hint.pack(anchor="w", padx=15, pady=(0, 4))

        # Context window size
        ctx_row = ctk.CTkFrame(ai_frame, fg_color="transparent")
        ctx_row.pack(fill="x", padx=15, pady=(0, 12))

        ctk.CTkLabel(
            ctx_row, text="Context Window:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.ctx_var = ctk.IntVar(value=self.settings.get("ollama_num_ctx", 0))
        ctx_slider = ctk.CTkSlider(
            ctx_row, from_=0, to=32768,
            variable=self.ctx_var,
            width=220, number_of_steps=32,
            fg_color=COLORS["bg_input"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        ctx_slider.pack(side="left", padx=(0, 8))
        Tooltip(ctx_slider,
                "Maximum context window size for Ollama.\n"
                "0 = Auto (recommended) — calculated from content.\n"
                "Higher values let the AI see more text at once\n"
                "but use more VRAM. Max 32768 tokens.")

        self.ctx_label = ctk.CTkLabel(
            ctx_row, text=self._ctx_display(self.ctx_var.get()),
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_muted"], width=80,
        )
        self.ctx_label.pack(side="left")
        self.ctx_var.trace_add("write", self._update_ctx_label)

        # ─── Groq Cloud Section ─────────────────────────────
        self._section_label(container, "☁️  Groq Cloud (Big Models)")

        groq_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        groq_frame.pack(fill="x", pady=(0, 15))

        groq_info = ctk.CTkLabel(
            groq_frame,
            text="🚀  Connect to Groq for blazing-fast cloud inference with 70B+ models.\n"
                 "   Free tier available — sign up at console.groq.com",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            justify="left",
        )
        groq_info.pack(anchor="w", padx=15, pady=(12, 8))

        # API Key
        key_row = ctk.CTkFrame(groq_frame, fg_color="transparent")
        key_row.pack(fill="x", padx=15, pady=(0, 6))

        ctk.CTkLabel(
            key_row, text="API Key:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.groq_key_entry = ctk.CTkEntry(
            key_row, width=350,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=8, height=32,
            placeholder_text="gsk_xxxxxxxxxxxxxxxxxxxxxxxx",
            show="●",
        )
        self.groq_key_entry.pack(side="left")
        if self.settings.get("groq_api_key"):
            self.groq_key_entry.insert(0, self.settings["groq_api_key"])
        Tooltip(self.groq_key_entry,
                "Your Groq API key from console.groq.com.\n"
                "Kept locally in settings.json — never sent anywhere but Groq.\n"
                "Leave blank to disable cloud features.")

        # Show/hide key toggle
        self._groq_key_visible = False
        btn_eye = ActionButton(
            key_row, text="👁", command=self._toggle_groq_key_vis,
            style="secondary", width=35,
        )
        btn_eye.pack(side="left", padx=(6, 0))
        Tooltip(btn_eye, "Show / hide API key")

        # Default cloud model
        gmodel_row = ctk.CTkFrame(groq_frame, fg_color="transparent")
        gmodel_row.pack(fill="x", padx=15, pady=(0, 6))

        ctk.CTkLabel(
            gmodel_row, text="Cloud Model:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        from core.ai_cleaner import GROQ_MODELS, GROQ_DEFAULT_MODEL
        self.groq_model_menu = ctk.CTkOptionMenu(
            gmodel_row,
            values=GROQ_MODELS,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=250, height=30,
        )
        self.groq_model_menu.pack(side="left")
        self.groq_model_menu.set(
            self.settings.get("groq_model", GROQ_DEFAULT_MODEL)
        )
        Tooltip(self.groq_model_menu,
                "Default model for Groq Cloud.\n"
                "70B models give GPT-4 quality at insane speed.\n"
                "8B models are fastest for quick cleaning.")

        # Default provider
        prov_row = ctk.CTkFrame(groq_frame, fg_color="transparent")
        prov_row.pack(fill="x", padx=15, pady=(4, 12))

        ctk.CTkLabel(
            prov_row, text="Default Provider:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.provider_var = ctk.StringVar(
            value=self.settings.get("ai_provider", "local")
        )
        prov_local = ctk.CTkRadioButton(
            prov_row, text="🖥  Local (Ollama)",
            variable=self.provider_var, value="local",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
        )
        prov_local.pack(side="left", padx=(0, 15))
        Tooltip(prov_local, "Use your local Ollama models by default.\nFree, private, works offline.")

        prov_groq = ctk.CTkRadioButton(
            prov_row, text="☁️  Groq Cloud",
            variable=self.provider_var, value="groq",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
        )
        prov_groq.pack(side="left")
        Tooltip(prov_groq, "Use Groq Cloud by default for all AI features.\n70B+ models, 50-150ms latency.\nRequires API key above.")

        # ─── Export Defaults Section ────────────────────────
        self._section_label(container, "🚀  Export Defaults")

        exp_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        exp_frame.pack(fill="x", pady=(0, 15))

        # Default chunk size
        chunk_row = ctk.CTkFrame(exp_frame, fg_color="transparent")
        chunk_row.pack(fill="x", padx=15, pady=(12, 6))

        ctk.CTkLabel(
            chunk_row, text="Default Chunk Size:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.chunk_entry = ctk.CTkEntry(
            chunk_row, width=80,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=32,
        )
        self.chunk_entry.pack(side="left")
        self.chunk_entry.insert(0, str(self.settings["default_chunk_size"]))
        Tooltip(self.chunk_entry, "Default words per training sample on the Export page.\nLong entries get split into chunks of this size.")

        # Default system prompt
        prompt_frame = ctk.CTkFrame(exp_frame, fg_color="transparent")
        prompt_frame.pack(fill="x", padx=15, pady=(6, 12))

        ctk.CTkLabel(
            prompt_frame, text="Default System Prompt:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        self.prompt_text = ctk.CTkTextbox(
            prompt_frame, height=60,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            wrap="word",
        )
        self.prompt_text.pack(fill="x", pady=(4, 0))
        self.prompt_text.insert("1.0", self.settings["default_system_prompt"])
        Tooltip(self.prompt_text, "The system prompt pre-filled on the Export page.\nChange this to match your training domain.")

        # ─── Scraper Section ────────────────────────────────
        self._section_label(container, "🌐  Scraper Settings")

        scraper_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        scraper_frame.pack(fill="x", pady=(0, 15))

        timeout_row = ctk.CTkFrame(scraper_frame, fg_color="transparent")
        timeout_row.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(
            timeout_row, text="Request Timeout (seconds):",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.timeout_entry = ctk.CTkEntry(
            timeout_row, width=80,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=32,
        )
        self.timeout_entry.pack(side="left")
        self.timeout_entry.insert(0, str(self.settings["request_timeout"]))
        Tooltip(self.timeout_entry, "How long to wait for a web page to respond.\n30 seconds is fine for most sites. Increase for slow pages.")

        # ─── Save / Reset Buttons ───────────────────────────
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(5, 10))

        btn_save = ActionButton(
            btn_row, text="💾  Save Settings", command=self._save,
            style="success", width=180
        )
        btn_save.pack(side="left", padx=(0, 10))
        Tooltip(btn_save, "Save all settings to disk.\nChanges take effect immediately.\nHotkeys are re-registered automatically.")

        btn_reset = ActionButton(
            btn_row, text="🔄  Reset to Defaults", command=self._reset,
            style="secondary", width=180
        )
        btn_reset.pack(side="left")
        Tooltip(btn_reset, "Reset ALL settings back to factory defaults.\nYou'll need to click Save to apply.")

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))

    # ─── Helpers ────────────────────────────────────────────

    def _section_label(self, parent, text):
        ctk.CTkLabel(
            parent, text=text,
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", pady=(5, 4))

    def _hotkey_row(self, parent, label, value, tooltip_text):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(0, 6))

        ctk.CTkLabel(
            row, text=label,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        entry = ctk.CTkEntry(
            row, width=200,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=32,
            placeholder_text="e.g. ctrl+shift+l",
        )
        entry.pack(side="left")
        if value:
            entry.insert(0, value)
        Tooltip(entry, tooltip_text)
        return entry

    def _update_opacity_label(self, *args):
        try:
            val = self.opacity_var.get()
            self.opacity_label.configure(text=f"{val:.0%}")
        except Exception:
            pass

    @staticmethod
    def _ctx_display(val: int) -> str:
        """Pretty-print context window value."""
        if val <= 0:
            return "Auto"
        if val >= 1024:
            return f"{val // 1024}k"
        return str(val)

    def _update_ctx_label(self, *args):
        try:
            val = self.ctx_var.get()
            self.ctx_label.configure(text=self._ctx_display(val))
        except Exception:
            pass

    def _toggle_groq_key_vis(self):
        """Show/hide the Groq API key."""
        self._groq_key_visible = not self._groq_key_visible
        self.groq_key_entry.configure(show="" if self._groq_key_visible else "●")

    def _gather_settings(self) -> dict:
        """Collect current UI values into a settings dict."""
        return {
            "minimize_to_tray": self.tray_var.get(),
            "always_on_top": self.ontop_var.get(),
            "window_opacity": round(self.opacity_var.get(), 2),
            "hotkey_show_hide": self.hk_show.get().strip(),
            "hotkey_quick_ocr": self.hk_ocr.get().strip(),
            "hotkey_quick_paste": self.hk_paste.get().strip(),
            "tesseract_path": self.tess_entry.get().strip(),
            "ollama_url": self.ollama_url_entry.get().strip() or DEFAULTS["ollama_url"],
            "ollama_model": self.ollama_model_entry.get().strip() or DEFAULTS["ollama_model"],
            "ollama_num_ctx": self.ctx_var.get(),
            "groq_api_key": self.groq_key_entry.get().strip(),
            "groq_model": self.groq_model_menu.get(),
            "ai_provider": self.provider_var.get(),
            "default_chunk_size": self._safe_int(self.chunk_entry.get(), 512),
            "default_system_prompt": self.prompt_text.get("1.0", "end-1c").strip(),
            "request_timeout": self._safe_int(self.timeout_entry.get(), 30),
            # Preserve other settings
            "start_minimized": self.settings.get("start_minimized", False),
            "user_agent": self.settings.get("user_agent", DEFAULTS["user_agent"]),
            "default_export_format": self.settings.get("default_export_format", DEFAULTS["default_export_format"]),
            "default_instruction_style": self.settings.get("default_instruction_style", DEFAULTS["default_instruction_style"]),
            "accent_color": self.settings.get("accent_color", DEFAULTS["accent_color"]),
        }

    def _safe_int(self, val, default):
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return default

    def _save(self):
        """Save settings and apply changes."""
        self.settings = self._gather_settings()
        save_settings(self.settings)

        # Apply immediate changes
        if self.app:
            # Opacity
            try:
                self.app.attributes("-alpha", self.settings["window_opacity"])
            except Exception:
                pass

            # Always on top
            try:
                self.app.attributes("-topmost", self.settings["always_on_top"])
            except Exception:
                pass

            # Re-register hotkeys
            try:
                from core.hotkeys import register_hotkeys
                register_hotkeys(self.app, self.settings)
            except Exception:
                pass

        self.status.set_success("Settings saved! Changes applied immediately.")

    def _reset(self):
        """Reset UI to defaults (still need to click Save)."""
        self.tray_var.set(DEFAULTS["minimize_to_tray"])
        self.ontop_var.set(DEFAULTS["always_on_top"])
        self.opacity_var.set(DEFAULTS["window_opacity"])

        self.hk_show.delete(0, "end")
        self.hk_show.insert(0, DEFAULTS["hotkey_show_hide"])
        self.hk_ocr.delete(0, "end")
        self.hk_paste.delete(0, "end")

        self.tess_entry.delete(0, "end")

        self.ollama_url_entry.delete(0, "end")
        self.ollama_url_entry.insert(0, DEFAULTS["ollama_url"])
        self.ollama_model_entry.delete(0, "end")
        self.ollama_model_entry.insert(0, DEFAULTS["ollama_model"])

        self.ctx_var.set(DEFAULTS["ollama_num_ctx"])

        self.groq_key_entry.delete(0, "end")
        self.groq_model_menu.set(DEFAULTS["groq_model"])
        self.provider_var.set(DEFAULTS["ai_provider"])

        self.chunk_entry.delete(0, "end")
        self.chunk_entry.insert(0, str(DEFAULTS["default_chunk_size"]))

        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", DEFAULTS["default_system_prompt"])

        self.timeout_entry.delete(0, "end")
        self.timeout_entry.insert(0, str(DEFAULTS["request_timeout"]))

        self.settings = dict(DEFAULTS)
        self.status.set_status("Reset to defaults. Click 'Save Settings' to apply.")

    def refresh(self):
        """Reload settings from disk."""
        self.settings = load_settings()
