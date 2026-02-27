"""
Export Page - Export collected data as LoRA-ready training files.
One-click export to multiple formats.
"""
import os
import threading
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES, SOURCE_ICONS
from gui.widgets import PageHeader, ActionButton, StatusBar, Tooltip
from core.database import get_all_entries, get_all_categories, get_stats, add_export_record
from core.exporter import (
    EXPORT_FORMATS, export_alpaca, export_sharegpt,
    export_completion, export_chatml, export_raw_json,
)
from config import EXPORTS_DIR, DEFAULT_SYSTEM_PROMPT, DEFAULT_CHUNK_SIZE


class ExportPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # Header
        PageHeader(
            container, icon="🚀", title="Export for LoRA Training",
            subtitle="Export your collected data as ready-to-use training files"
        ).pack(fill="x", pady=(0, 15))

        # Stats overview
        self.stats_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        self.stats_frame.pack(fill="x", pady=(0, 15))

        self.stats_label = ctk.CTkLabel(
            self.stats_frame,
            text="Loading stats...",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
            justify="left",
        )
        self.stats_label.pack(padx=15, pady=12, anchor="w")

        # ─── Format Selection ───────────────────────────────
        format_section = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        format_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            format_section,
            text="📋 Export Format",
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", padx=15, pady=(12, 5))

        self.format_var = ctk.StringVar(value="Alpaca (Instruction/Input/Output)")
        for fmt_name in EXPORT_FORMATS:
            rb = ctk.CTkRadioButton(
                format_section,
                text=fmt_name,
                variable=self.format_var,
                value=fmt_name,
                font=(FONT_FAMILY, FONT_SIZES["body"]),
                text_color=COLORS["text_secondary"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                border_color=COLORS["border"],
            )
            rb.pack(anchor="w", padx=25, pady=3)

        # Format descriptions
        ctk.CTkLabel(
            format_section,
            text=(
                "💡 Alpaca = best for instruction fine-tuning (LLaMA, Mistral, etc.)\n"
                "   ShareGPT = conversation format (many trainers support this)\n"
                "   Completion = raw text chunks (for continued pretraining)\n"
                "   ChatML = ChatML template format\n"
                "   Raw JSON = backup/custom processing"
            ),
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            justify="left",
        ).pack(anchor="w", padx=15, pady=(5, 12))

        # ─── Settings ──────────────────────────────────────
        settings_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        settings_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            settings_frame,
            text="⚙️ Export Settings",
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", padx=15, pady=(12, 10))

        # System prompt
        prompt_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        prompt_frame.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(
            prompt_frame,
            text="System Prompt:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        self.system_prompt = ctk.CTkTextbox(
            prompt_frame, height=60,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            wrap="word",
        )
        self.system_prompt.pack(fill="x", pady=(4, 0))
        self.system_prompt.insert("1.0", DEFAULT_SYSTEM_PROMPT)
        Tooltip(self.system_prompt, "The system prompt is injected into every training sample.\nTells the model what role it should play.\nDefault is tuned for game security/cheat detection.\nChange this to match your training goal.")

        # Chunk size
        chunk_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        chunk_frame.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(
            chunk_frame,
            text="Chunk Size (words per training sample):",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.chunk_size_var = ctk.StringVar(value=str(DEFAULT_CHUNK_SIZE))
        self.chunk_entry = ctk.CTkEntry(
            chunk_frame,
            textvariable=self.chunk_size_var,
            width=80,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=32,
        )
        self.chunk_entry.pack(side="left")
        Tooltip(self.chunk_entry, "How many words per training sample.\nLong entries are split into chunks of this size.\n512 is a good default for most LoRA trainers.\nSmaller = more samples but less context each.\nLarger = fewer samples but richer context.")

        # Instruction template (for Alpaca)
        template_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        template_frame.pack(fill="x", padx=15, pady=(0, 12))

        ctk.CTkLabel(
            template_frame,
            text="Instruction Style (Alpaca only):",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 10))

        self.template_menu = ctk.CTkOptionMenu(
            template_frame,
            values=["default", "qa", "explain", "summarize"],
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=150,
            height=32,
        )
        self.template_menu.set("default")
        self.template_menu.pack(side="left")
        Tooltip(self.template_menu, "How the instruction is phrased in Alpaca format.\n• default: generic instruction style\n• qa: question & answer framing\n• explain: 'Explain the following...'\n• summarize: 'Summarize the following...'\nOnly affects Alpaca exports.")

        # ─── Filter ────────────────────────────────────────
        filter_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        filter_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            filter_frame,
            text="🔍 Filter Entries to Export",
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", padx=15, pady=(12, 8))

        filter_row = ctk.CTkFrame(filter_frame, fg_color="transparent")
        filter_row.pack(fill="x", padx=15, pady=(0, 12))

        ctk.CTkLabel(
            filter_row, text="Source type:",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 8))

        self.export_type_filter = ctk.CTkOptionMenu(
            filter_row,
            values=["all", "web", "youtube", "paste", "ocr", "file"],
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=130,
            height=32,
        )
        self.export_type_filter.set("all")
        self.export_type_filter.pack(side="left", padx=(0, 15))
        Tooltip(self.export_type_filter, "Only export entries from this source type.\n'all' = export everything in your library.")

        ctk.CTkLabel(
            filter_row, text="Category:",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 8))

        self.export_cat_filter = ctk.CTkOptionMenu(
            filter_row,
            values=["all"],
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=180,
            height=32,
        )
        self.export_cat_filter.set("all")
        self.export_cat_filter.pack(side="left")
        Tooltip(self.export_cat_filter, "Only export entries with this category.\n'all' = include every category.\nCategories come from your tags when saving entries.")

        # ─── Export Buttons ─────────────────────────────────
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        btn_export = ActionButton(
            btn_row, text="🚀  Export Training Data", command=self._export,
            style="primary", width=220
        )
        btn_export.pack(side="left", padx=(0, 10))
        Tooltip(btn_export, "Export your data in the selected format.\nCreates a JSONL file in data/exports/.\nReady to load into LoRA trainers like\nAxolotl, Unsloth, LLaMA-Factory, etc.")

        btn_open = ActionButton(
            btn_row, text="📂  Open Export Folder", command=self._open_folder,
            style="secondary", width=200
        )
        btn_open.pack(side="left", padx=(0, 10))
        Tooltip(btn_open, "Opens the data/exports/ folder in Windows Explorer.\nYour exported JSONL files are saved here.")

        btn_export_all = ActionButton(
            btn_row, text="🚀  Export ALL Formats", command=self._export_all,
            style="success", width=200
        )
        btn_export_all.pack(side="left")
        Tooltip(btn_export_all, "Exports in ALL 5 formats at once.\nAlpaca + ShareGPT + Completion + ChatML + Raw JSON.\nGreat for trying different formats with your trainer\nwithout re-exporting each time.")

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(10, 0))

        # Recent exports
        self.export_info = ctk.CTkLabel(
            container,
            text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            justify="left",
        )
        self.export_info.pack(anchor="w", pady=(10, 0))

    def refresh(self):
        """Refresh stats and category list."""
        stats = get_stats()
        type_info = " | ".join(f"{SOURCE_ICONS.get(t, '')} {t}: {c}" for t, c in stats["by_type"].items())

        text = (
            f"📊 Total: {stats['total_entries']} entries | "
            f"{stats['total_words']:,} words | "
            f"{stats['total_exports']} previous exports\n"
            f"📂 {type_info}"
        )
        self.stats_label.configure(text=text)

        # Update categories
        cats = ["all"] + get_all_categories()
        self.export_cat_filter.configure(values=cats)

    def _get_chunk_size(self):
        try:
            return max(50, int(self.chunk_size_var.get()))
        except ValueError:
            return DEFAULT_CHUNK_SIZE

    def _get_entries(self):
        source_type = self.export_type_filter.get()
        category = self.export_cat_filter.get()
        return get_all_entries(
            source_type=source_type if source_type != "all" else None,
            category=category if category != "all" else None,
        )

    def _export(self):
        entries = self._get_entries()
        if not entries:
            self.status.set_error("No entries to export! Collect some data first.")
            return

        fmt_name = self.format_var.get()
        self.status.set_working(f"Exporting {len(entries)} entries as {fmt_name}...")

        def do_export():
            system_prompt = self.system_prompt.get("1.0", "end-1c").strip()
            chunk_size = self._get_chunk_size()

            export_func = EXPORT_FORMATS[fmt_name]

            kwargs = {}
            if export_func != export_raw_json:
                if export_func in (export_alpaca, export_sharegpt, export_chatml):
                    kwargs["system_prompt"] = system_prompt
                if export_func == export_alpaca:
                    kwargs["instruction_template"] = self.template_menu.get()
                kwargs["chunk_size"] = chunk_size

            output_path, count = export_func(entries, **kwargs)

            add_export_record(os.path.basename(output_path), fmt_name, count)

            self.after(0, lambda: self._export_done(output_path, count, fmt_name))

        threading.Thread(target=do_export, daemon=True).start()

    def _export_all(self):
        """Export in all formats at once."""
        entries = self._get_entries()
        if not entries:
            self.status.set_error("No entries to export!")
            return

        self.status.set_working(f"Exporting {len(entries)} entries in all formats...")

        def do_export_all():
            system_prompt = self.system_prompt.get("1.0", "end-1c").strip()
            chunk_size = self._get_chunk_size()
            template = self.template_menu.get()

            results = []

            p1, c1 = export_alpaca(entries, system_prompt=system_prompt,
                                    instruction_template=template, chunk_size=chunk_size)
            results.append(("Alpaca", p1, c1))

            p2, c2 = export_sharegpt(entries, system_prompt=system_prompt, chunk_size=chunk_size)
            results.append(("ShareGPT", p2, c2))

            p3, c3 = export_completion(entries, chunk_size=chunk_size)
            results.append(("Completion", p3, c3))

            p4, c4 = export_chatml(entries, system_prompt=system_prompt, chunk_size=chunk_size)
            results.append(("ChatML", p4, c4))

            p5, c5 = export_raw_json(entries)
            results.append(("Raw JSON", p5, c5))

            for name, path, count in results:
                add_export_record(os.path.basename(path), name, count)

            self.after(0, lambda: self._export_all_done(results))

        threading.Thread(target=do_export_all, daemon=True).start()

    def _export_done(self, path, count, fmt_name):
        self.status.set_success(f"Exported {count} samples to {os.path.basename(path)}")
        self.export_info.configure(
            text=f"📄 Last export: {path}\n"
                 f"   Format: {fmt_name} | Samples: {count}"
        )
        if self.app:
            self.app.refresh_stats()

    def _export_all_done(self, results):
        total = sum(c for _, _, c in results)
        info_lines = [f"�?Exported {total} total samples in {len(results)} formats:\n"]
        for name, path, count in results:
            info_lines.append(f"   📄 {name}: {count} samples �?{os.path.basename(path)}")

        self.status.set_success(f"Exported all formats! ({total} total samples)")
        self.export_info.configure(text="\n".join(info_lines))
        if self.app:
            self.app.refresh_stats()

    def _open_folder(self):
        os.makedirs(EXPORTS_DIR, exist_ok=True)
        os.startfile(EXPORTS_DIR)
