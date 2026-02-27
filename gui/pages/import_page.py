"""
Import Files Page - Drag & drop zone + compact file list + preview.
"""
import os
import threading
import customtkinter as ctk
from tkinter import filedialog
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import (
    PageHeader, ContentPreview, InputField, TagInput,
    ActionButton, StatusBar, Tooltip, DropZone, CompactFileList,
)
from core.file_reader import read_file, get_supported_extensions
from core.database import add_entry
from core.quality import score_entry_quick


class ImportPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self.loaded_files = []
        self._build_ui()

    def _build_ui(self):
        # Main container
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # Header
        PageHeader(
            container, icon="📁", title="Import Files",
            subtitle="Drag files here, or click the zone to browse"
        ).pack(fill="x", pady=(0, 12))

        # ─── Drop Zone (big target at top) ──────────────────
        self.drop_zone = DropZone(
            container,
            on_files_dropped=self._on_files_received,
            height=140,
            text="Click to upload or drag and drop",
            subtext="supports text files, csv's, PDFs, code files, and more!",
            filetypes=get_supported_extensions(),
        )
        self.drop_zone.pack(fill="x", pady=(0, 10))

        # Quick action row (folder import, clear)
        action_row = ctk.CTkFrame(container, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 8))

        btn_folder = ActionButton(
            action_row, text="📂  Import Folder", command=self._select_folder,
            style="secondary", width=160
        )
        btn_folder.pack(side="left", padx=(0, 8))
        Tooltip(btn_folder, "Scan a folder (and subfolders) for supported files.\nFinds PDFs, text, code, HTML, JSON, CSV.\nGreat for importing entire directories.")

        btn_clear = ActionButton(
            action_row, text="🗑  Clear All", command=self._clear,
            style="secondary", width=120
        )
        btn_clear.pack(side="left")
        Tooltip(btn_clear, "Clear the file list and preview.")

        self.file_count_label = ctk.CTkLabel(
            action_row,
            text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.file_count_label.pack(side="right")

        # ─── Compact File List ──────────────────────────────
        self.file_list = CompactFileList(
            container,
            on_preview=self._preview_file,
            on_pin=self._on_pin,
        )
        self.file_list.pack(fill="both", expand=False, pady=(0, 10))

        # ─── Preview Section ────────────────────────────────
        preview_header = ctk.CTkFrame(container, fg_color="transparent")
        preview_header.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            preview_header, text="📄 Preview",
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(side="left")

        self.preview_name = ctk.CTkLabel(
            preview_header, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.preview_name.pack(side="left", padx=(10, 0))

        # Title
        self.title_field = InputField(
            container, label_text="Title",
            placeholder="Auto-filled from filename"
        )
        self.title_field.pack(fill="x", pady=(0, 8))

        # Content Preview
        self.preview = ContentPreview(container, label_text="File Content (editable)", height=280)
        self.preview.pack(fill="both", expand=True, pady=(0, 8))

        # Tags & Category
        self.tag_input = TagInput(container)
        self.tag_input.pack(fill="x", pady=(0, 12))

        # Save buttons
        save_row = ctk.CTkFrame(container, fg_color="transparent")
        save_row.pack(fill="x", pady=(0, 8))

        btn_save = ActionButton(
            save_row, text="💾  Save Current", command=self._save,
            style="success", width=160
        )
        btn_save.pack(side="left", padx=(0, 8))
        Tooltip(btn_save, "Save only the currently previewed file to the library.\nYou can edit the title and content before saving.")

        btn_save_all = ActionButton(
            save_row, text="💾  Save All Files", command=self._save_all,
            style="success", width=180
        )
        btn_save_all.pack(side="left", padx=(0, 8))
        Tooltip(btn_save_all, "Bulk-import ALL selected files at once.\nPinned files are imported first.\nEach file becomes its own entry.\nTags and category are applied to all.")

        btn_save_pinned = ActionButton(
            save_row, text="⭐  Save Pinned Only", command=self._save_pinned,
            style="warning", width=180
        )
        btn_save_pinned.pack(side="left")
        Tooltip(btn_save_pinned, "Import only the pinned (starred) files.\nPin files with the ☆ icon in the file list.")

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))

    # ─── File Handling ──────────────────────────────────────

    def _on_files_received(self, paths):
        """Called when files are dropped or selected via the drop zone."""
        # Filter to supported extensions
        supported = {
            ".pdf", ".txt", ".md", ".markdown", ".html", ".htm",
            ".json", ".csv", ".py", ".js", ".ts", ".cpp", ".c",
            ".h", ".cs", ".java", ".lua", ".log", ".rst", ".ksh",
            ".xml", ".yaml", ".yml",
        }
        valid = [p for p in paths if os.path.splitext(p)[1].lower() in supported]
        skipped = len(paths) - len(valid)

        if not valid:
            self.status.set_error(f"No supported files found ({skipped} skipped)")
            return

        # Merge with existing (avoid duplicates)
        existing = {f["path"] for f in self.file_list.files}
        new_paths = [p for p in valid if p not in existing]

        all_paths = [f["path"] for f in self.file_list.files] + new_paths
        self.file_list.set_files(all_paths)

        msg = f"Added {len(new_paths)} files"
        if skipped:
            msg += f" ({skipped} unsupported skipped)"
        self.status.set_success(msg)
        self.file_count_label.configure(text=f"{len(all_paths)} files loaded")

        # Auto-preview first new file
        if new_paths:
            self._preview_file(new_paths[0])

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return

        supported = {
            ".pdf", ".txt", ".md", ".markdown", ".html", ".htm",
            ".json", ".csv", ".py", ".js", ".ts", ".cpp", ".c",
            ".h", ".cs", ".java", ".lua", ".log", ".rst", ".ksh",
        }
        files = []
        for root, dirs, filenames in os.walk(folder):
            for fname in filenames:
                if os.path.splitext(fname)[1].lower() in supported:
                    files.append(os.path.join(root, fname))

        if files:
            self._on_files_received(files)
        else:
            self.status.set_error("No supported files found in folder")

    def _preview_file(self, file_path):
        """Load a file into the preview area."""
        self.status.set_working(f"Reading: {os.path.basename(file_path)}")

        def do_read():
            result = read_file(file_path)
            self.after(0, lambda: self._handle_result(result, file_path))

        threading.Thread(target=do_read, daemon=True).start()

    def _handle_result(self, result, file_path):
        if result["success"]:
            self.title_field.set(result["title"])
            self.preview.set_text(result["content"])
            self.preview_name.configure(text=os.path.basename(file_path))

            word_count = len(result["content"].split())
            # Quality score
            try:
                _score, _emoji, _grade = score_entry_quick(result["content"])
                q_str = f" | {_emoji} {_grade.title()} ({_score}/100)"
            except Exception:
                q_str = ""

            self.status.set_success(f"Loaded {word_count:,} words{q_str}")
        else:
            self.status.set_error(result["error"])

    def _on_pin(self, finfo):
        """Called when a file is pinned/unpinned."""
        state = "Pinned" if finfo.get("pinned") else "Unpinned"
        self.status.set_status(f"⭐ {state}: {finfo['name']}")

    # ─── Save Logic ─────────────────────────────────────────

    def _save(self):
        title = self.title_field.get()
        content = self.preview.get_text()

        if not content:
            self.status.set_error("Nothing to save — preview a file first")
            return
        if not title:
            title = "Imported File"

        entry_id = add_entry(
            title=title,
            content=content,
            source_type="file",
            tags=self.tag_input.get_tags(),
            category=self.tag_input.get_category(),
        )
        self.status.set_success(f"Saved! (Entry #{entry_id})")
        if self.app:
            self.app.refresh_stats()

    def _save_all(self):
        files = self.file_list.get_selected_files()
        if not files:
            self.status.set_error("No files selected")
            return
        self._batch_import(files, "all selected")

    def _save_pinned(self):
        files = self.file_list.get_pinned_files()
        if not files:
            self.status.set_error("No pinned files — use ☆ to pin files first")
            return
        self._batch_import(files, "pinned")

    def _batch_import(self, files, label):
        self.status.set_working(f"Importing {len(files)} {label} files...")

        def do_import():
            saved = 0
            failed = 0
            for fp in files:
                result = read_file(fp)
                if result["success"]:
                    add_entry(
                        title=result["title"],
                        content=result["content"],
                        source_type="file",
                        source_url=fp,
                        tags=self.tag_input.get_tags(),
                        category=self.tag_input.get_category(),
                    )
                    saved += 1
                else:
                    failed += 1
            self.after(0, lambda: self._batch_done(saved, failed))

        threading.Thread(target=do_import, daemon=True).start()

    def _batch_done(self, saved, failed):
        msg = f"Imported {saved} files"
        if failed:
            msg += f" ({failed} failed)"
        self.status.set_success(msg)
        if self.app:
            self.app.refresh_stats()

    def _clear(self):
        self.title_field.clear()
        self.preview.clear()
        self.tag_input.clear()
        self.file_list.set_files([])
        self.preview_name.configure(text="")
        self.file_count_label.configure(text="")
        self.status.set_status("Cleared")
