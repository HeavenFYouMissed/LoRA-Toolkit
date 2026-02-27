"""
Data Library Page - View, search, edit, and manage all collected data.
This is the heart of the app: see everything you've collected.
"""
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES, SOURCE_ICONS
from gui.widgets import PageHeader, ContentPreview, ActionButton, StatusBar, Tooltip
from core.database import get_all_entries, get_entry, update_entry, delete_entry, delete_multiple_entries, get_all_categories
from core.quality import score_entry_quick


class LibraryPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self.entries = []
        self.selected_entry = None
        self.selected_ids = set()
        self._build_ui()

    def _build_ui(self):
        # Use a paned layout: left = list, right = detail
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ─── Left Panel: Entry List ─────────────────────────
        left_panel = ctk.CTkFrame(self, fg_color=COLORS["bg_sidebar"], corner_radius=0)
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.grid_rowconfigure(2, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkFrame(left_panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            header,
            text="📚 Data Library",
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w")

        self.count_label = ctk.CTkLabel(
            header,
            text="0 entries",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.count_label.pack(anchor="w")

        # Filters row
        filters = ctk.CTkFrame(left_panel, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

        # Search
        self.search_entry = ctk.CTkEntry(
            filters,
            placeholder_text="🔍 Search...",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=32,
        )
        self.search_entry.pack(fill="x", pady=(0, 5))
        self._search_after_id = None
        self.search_entry.bind("<Return>", lambda e: self.refresh())
        self.search_entry.bind("<KeyRelease>", self._schedule_search)
        Tooltip(self.search_entry, "Type to search across all entries.\nSearches titles, content, and tags.\nResults filter in real-time as you type.")

        # Type filter
        filter_row = ctk.CTkFrame(filters, fg_color="transparent")
        filter_row.pack(fill="x")

        self.type_filter = ctk.CTkOptionMenu(
            filter_row,
            values=["all", "web", "youtube", "paste", "ocr", "file"],
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=110,
            height=28,
            command=lambda v: self.refresh(),
        )
        self.type_filter.set("all")
        self.type_filter.pack(side="left", padx=(0, 5))
        Tooltip(self.type_filter, "Filter by data source type.\nShow only web scrapes, YouTube transcripts,\npastes, OCR captures, or imported files.")

        btn_refresh = ActionButton(
            filter_row, text="🔄", command=self.refresh,
            style="secondary", width=35
        )
        btn_refresh.pack(side="left", padx=(0, 5))
        Tooltip(btn_refresh, "Refresh the entry list from the database.")

        btn_del_sel = ActionButton(
            filter_row, text="🗑 Delete Sel.", command=self._delete_selected,
            style="danger", width=110
        )
        btn_del_sel.pack(side="right")
        Tooltip(btn_del_sel, "Delete all checked entries (use checkboxes).\nThis is permanent — cannot be undone.\nUseful for cleaning up bad scrapes or duplicates.")

        btn_chat_sel = ActionButton(
            filter_row, text="💬 Chat", command=self._chat_with_selected,
            style="primary", width=80
        )
        btn_chat_sel.pack(side="right", padx=(0, 4))
        Tooltip(btn_chat_sel,
                "Open a chat window with the checked entries loaded as context.\n"
                "Ask the AI to explain, compare, summarise, or generate\n"
                "training data from the selected files.")

        # Entry list (scrollable)
        self.list_frame = ctk.CTkScrollableFrame(
            left_panel,
            fg_color="transparent",
        )
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)

        # ─── Right Panel: Detail View ───────────────────────
        right_panel = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], corner_radius=0)
        right_panel.grid(row=0, column=1, sticky="nsew")

        detail_container = ctk.CTkScrollableFrame(right_panel, fg_color="transparent")
        detail_container.pack(fill="both", expand=True, padx=15, pady=10)

        self.detail_header = ctk.CTkLabel(
            detail_container,
            text="Select an entry to view details",
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["text_primary"],
            wraplength=500,
        )
        self.detail_header.pack(anchor="w", pady=(0, 5))

        self.detail_meta = ctk.CTkLabel(
            detail_container,
            text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.detail_meta.pack(anchor="w", pady=(0, 10))

        # Editable title
        title_row = ctk.CTkFrame(detail_container, fg_color="transparent")
        title_row.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(
            title_row, text="Title:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 5))

        self.detail_title = ctk.CTkEntry(
            title_row,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=35,
        )
        self.detail_title.pack(fill="x", expand=True, side="left")
        Tooltip(self.detail_title, "Edit the entry title here.\nGood titles help you find things fast in the library.")

        # Editable tags
        tags_row = ctk.CTkFrame(detail_container, fg_color="transparent")
        tags_row.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(
            tags_row, text="Tags:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 5))

        self.detail_tags = ctk.CTkEntry(
            tags_row,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=35,
        )
        self.detail_tags.pack(fill="x", expand=True, side="left")
        Tooltip(self.detail_tags, "Comma-separated tags for this entry.\nEdit to re-organize or add more context.")

        # Content preview
        self.detail_content = ContentPreview(
            detail_container, label_text="Content (editable)", height=400
        )
        self.detail_content.pack(fill="both", expand=True, pady=(10, 10))

        # Action buttons
        action_row = ctk.CTkFrame(detail_container, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 10))

        btn_save_ch = ActionButton(
            action_row, text="💾  Save Changes", command=self._save_changes,
            style="success", width=160
        )
        btn_save_ch.pack(side="left", padx=(0, 8))
        Tooltip(btn_save_ch, "Saves your edits to this entry.\nUpdates the title, tags, and content in the database.\nGreat for cleaning up or improving data quality.")

        btn_del_one = ActionButton(
            action_row, text="🗑  Delete Entry", command=self._delete_current,
            style="danger", width=140
        )
        btn_del_one.pack(side="left")
        Tooltip(btn_del_one, "Permanently delete this entry from the database.\nCannot be undone. Use this for junk or duplicate data.")

        # Status
        self.status = StatusBar(detail_container)
        self.status.pack(fill="x")

    def _schedule_search(self, event=None):
        """Debounce: wait 300 ms after last keystroke before refreshing."""
        if self._search_after_id:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(300, self.refresh)

    def refresh(self, event=None):
        """Reload the entry list from database."""
        self._search_after_id = None
        search = self.search_entry.get().strip() if self.search_entry.get() else None
        source_type = self.type_filter.get()

        self.entries = get_all_entries(
            source_type=source_type if source_type != "all" else None,
            search=search,
        )

        self.count_label.configure(text=f"{len(self.entries)} entries")

        # Clear the list
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        self.selected_ids = set()

        # Build entry cards
        for entry in self.entries:
            self._create_entry_card(entry)

    def _create_entry_card(self, entry):
        """Create a compact single-row card for an entry in the list."""
        icon = SOURCE_ICONS.get(entry["source_type"], "📄")

        card = ctk.CTkFrame(
            self.list_frame,
            fg_color=COLORS["bg_card"],
            corner_radius=6,
            height=34,
            cursor="hand2",
        )
        card.pack(fill="x", pady=1)
        card.pack_propagate(False)

        # Checkbox
        cb_var = ctk.BooleanVar(value=False)
        cb = ctk.CTkCheckBox(
            card, text="", variable=cb_var, width=18, height=18,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
            command=lambda eid=entry["id"], var=cb_var: self._toggle_select(eid, var),
        )
        cb.pack(side="left", padx=(6, 4))

        # Icon
        ctk.CTkLabel(
            card, text=icon, font=(FONT_FAMILY, 12),
            text_color=COLORS["text_muted"], width=18,
        ).pack(side="left", padx=(0, 4))

        # Title (truncated)
        title_text = entry["title"][:45]
        title_label = ctk.CTkLabel(
            card,
            text=title_text,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        title_label.pack(side="left", fill="x", expand=True, padx=(0, 4))

        # Eye icon (view detail)
        eye_btn = ctk.CTkLabel(
            card, text="👁", cursor="hand2",
            font=(FONT_FAMILY, 12),
            text_color=COLORS["text_muted"],
            width=22,
        )
        eye_btn.pack(side="right", padx=(0, 6))
        eye_btn.bind("<Button-1>", lambda e, eid=entry["id"]: self._show_detail(eid))
        eye_btn.bind("<Enter>", lambda e, w=eye_btn: w.configure(text_color=COLORS["accent_blue"]))
        eye_btn.bind("<Leave>", lambda e, w=eye_btn: w.configure(text_color=COLORS["text_muted"]))

        # Quality badge
        try:
            _score, _emoji, _grade = score_entry_quick(entry.get("content", ""))
            quality_text = f"{_emoji}{_score}"
        except Exception:
            quality_text = ""

        if quality_text:
            ctk.CTkLabel(
                card, text=quality_text,
                font=(FONT_FAMILY, FONT_SIZES["tiny"]),
                text_color=COLORS["text_muted"],
                width=34,
            ).pack(side="right", padx=(0, 2))

        # Word count badge
        ctk.CTkLabel(
            card,
            text=f"{entry['word_count']:,}w",
            font=(FONT_FAMILY, FONT_SIZES["tiny"]),
            text_color=COLORS["text_muted"],
            width=40,
        ).pack(side="right", padx=(0, 2))

        # Click on card/title to view detail
        card.bind("<Button-1>", lambda e, eid=entry["id"]: self._show_detail(eid))
        title_label.bind("<Button-1>", lambda e, eid=entry["id"]: self._show_detail(eid))

    def _toggle_select(self, entry_id, var):
        if var.get():
            self.selected_ids.add(entry_id)
        else:
            self.selected_ids.discard(entry_id)

    def _show_detail(self, entry_id):
        """Show entry details in the right panel."""
        entry = get_entry(entry_id)
        if not entry:
            return

        self.selected_entry = entry
        icon = SOURCE_ICONS.get(entry["source_type"], "📄")

        self.detail_header.configure(text=f"{icon} {entry['title']}")

        # Quality score
        try:
            _s, _e, _g = score_entry_quick(entry.get("content", ""))
            quality_str = f"{_e} {_g.title()} ({_s}/100)"
        except Exception:
            quality_str = "—"

        meta = (
            f"Source: {entry['source_type']} | "
            f"Words: {entry['word_count']:,} | "
            f"Quality: {quality_str}\n"
            f"Created: {entry['created_at']} | "
            f"Category: {entry['category']}"
        )
        if entry["source_url"]:
            meta += f"\nURL: {entry['source_url']}"
        self.detail_meta.configure(text=meta)

        self.detail_title.delete(0, "end")
        self.detail_title.insert(0, entry["title"])

        self.detail_tags.delete(0, "end")
        self.detail_tags.insert(0, entry.get("tags", ""))

        self.detail_content.set_text(entry["content"])
        self.status.set_status(f"Viewing entry #{entry['id']}")

    def _save_changes(self):
        if not self.selected_entry:
            self.status.set_error("No entry selected")
            return

        new_title = self.detail_title.get().strip()
        new_tags = self.detail_tags.get().strip()
        new_content = self.detail_content.get_text()

        update_entry(
            self.selected_entry["id"],
            title=new_title,
            tags=new_tags,
            content=new_content,
        )

        self.status.set_success(f"Entry #{self.selected_entry['id']} updated!")
        self.refresh()
        if self.app:
            self.app.refresh_stats()

    def _delete_current(self):
        if not self.selected_entry:
            self.status.set_error("No entry selected")
            return

        delete_entry(self.selected_entry["id"])
        self.status.set_success(f"Deleted entry #{self.selected_entry['id']}")
        self.selected_entry = None
        self.detail_header.configure(text="Entry deleted")
        self.detail_meta.configure(text="")
        self.detail_content.clear()
        self.refresh()
        if self.app:
            self.app.refresh_stats()

    def _delete_selected(self):
        if not self.selected_ids:
            self.status.set_error("No entries selected (use checkboxes)")
            return

        count = len(self.selected_ids)
        delete_multiple_entries(list(self.selected_ids))
        self.status.set_success(f"Deleted {count} entries")
        self.selected_ids = set()
        self.refresh()
        if self.app:
            self.app.refresh_stats()

    def _chat_with_selected(self):
        """Open the Data Chat popup with selected entries loaded as context."""
        if not self.selected_ids:
            self.status.set_error("No entries selected — check some boxes first")
            return

        from gui.pages.data_chat_popup import DataChatPopup
        DataChatPopup(self, list(self.selected_ids), app=self.app)
