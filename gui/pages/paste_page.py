"""
Paste Text Page - Simple text input for manual data entry.
"""
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, ContentPreview, InputField, TagInput, ActionButton, StatusBar, Tooltip
from core.database import add_entry


class PastePage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # Header
        PageHeader(
            container, icon="📋", title="Paste Text",
            subtitle="Paste or type text content directly — copy from websites, docs, anywhere"
        ).pack(fill="x", pady=(0, 15))

        # Title
        self.title_field = InputField(
            container, label_text="Title",
            placeholder="Give this content a descriptive title"
        )
        self.title_field.pack(fill="x", pady=(0, 10))
        Tooltip(self.title_field, "Give this paste a descriptive name.\nIf left blank, the first line of content is used.\nGood titles make finding things in the Library easier.")

        # Source URL (optional)
        self.source_field = InputField(
            container, label_text="Source URL (optional)",
            placeholder="Where did this come from? (optional)"
        )
        self.source_field.pack(fill="x", pady=(0, 10))
        Tooltip(self.source_field, "Optional: paste where this content came from.\nJust for your own reference — not used in training.\nHelps you remember the source later.")

        # Content area
        self.preview = ContentPreview(container, label_text="Content", height=350)
        self.preview.pack(fill="both", expand=True, pady=(0, 10))
        Tooltip(self.preview, "Type or paste your content here.\nYou can paste anything: website text, notes, code,\nchat logs, documentation, etc.\nNo size limit — paste as much as you want.")

        # Quick paste from clipboard button
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        btn_paste = ActionButton(
            btn_row, text="📋  Paste from Clipboard", command=self._paste_clipboard,
            style="secondary", width=200
        )
        btn_paste.pack(side="left", padx=(0, 8))
        Tooltip(btn_paste, "Quick paste whatever is in your clipboard (Ctrl+C).\nReplaces any existing text in the content box.\nSame as Ctrl+V but fills the whole box at once.")

        btn_clear = ActionButton(
            btn_row, text="🗑  Clear All", command=self._clear,
            style="secondary", width=120
        )
        btn_clear.pack(side="left")
        Tooltip(btn_clear, "Clears all fields including title, source, content, and tags.")

        # Tags & Category
        self.tag_input = TagInput(container)
        self.tag_input.pack(fill="x", pady=(0, 15))
        Tooltip(self.tag_input, "Tags: comma-separated labels for organizing.\nCategory: pick a topic bucket.\nThese help filter entries in Library and when exporting.")

        # Save button
        save_row = ctk.CTkFrame(container, fg_color="transparent")
        save_row.pack(fill="x", pady=(0, 10))

        btn_save = ActionButton(
            save_row, text="💾  Save to Library", command=self._save,
            style="success", width=180
        )
        btn_save.pack(side="left", padx=(0, 8))
        Tooltip(btn_save, "Saves this content to your local database.\nYou can find it later in the Library tab.")

        btn_save_new = ActionButton(
            save_row, text="💾  Save & New", command=self._save_and_new,
            style="success", width=150
        )
        btn_save_new.pack(side="left")
        Tooltip(btn_save_new, "Saves the current content and clears the form\nso you can immediately paste the next thing.\nKeeps your tags and category for rapid entry.\nGreat for bulk copy-paste sessions.")

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))

    def _paste_clipboard(self):
        try:
            text = self.clipboard_get()
            if text:
                self.preview.set_text(text)
                self.status.set_success(f"Pasted {len(text.split()):,} words from clipboard")
            else:
                self.status.set_error("Clipboard is empty")
        except Exception:
            self.status.set_error("Nothing in clipboard to paste")

    def _save(self):
        title = self.title_field.get()
        content = self.preview.get_text()

        if not content:
            self.status.set_error("Enter some content first")
            return
        if not title:
            # Auto-generate title from first line
            first_line = content.split("\n")[0][:80]
            title = first_line if first_line else "Untitled Paste"

        entry_id = add_entry(
            title=title,
            content=content,
            source_type="paste",
            source_url=self.source_field.get(),
            tags=self.tag_input.get_tags(),
            category=self.tag_input.get_category(),
        )

        self.status.set_success(f"Saved! (Entry #{entry_id})")
        if self.app:
            self.app.refresh_stats()
        return entry_id

    def _save_and_new(self):
        entry_id = self._save()
        if entry_id:
            self.title_field.clear()
            self.source_field.clear()
            self.preview.clear()
            # Keep tags and category for rapid entry

    def handle_file_drop(self, paths):
        """Read first dropped text file into the editor."""
        import os
        for p in paths:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self.preview.set_text(content)
                self.title_field.set(os.path.splitext(os.path.basename(p))[0])
                self.source_field.set(p)
                self.status.set_success(f"Loaded: {os.path.basename(p)}")
                return
            except Exception as e:
                self.status.set_error(f"Could not read file: {e}")

    def _clear(self):
        self.title_field.clear()
        self.source_field.clear()
        self.preview.clear()
        self.tag_input.clear()
        self.status.set_status("Cleared")
