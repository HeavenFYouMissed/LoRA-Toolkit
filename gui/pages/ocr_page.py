"""
OCR Page - Extract text from screenshots and images.
Auto-downloads Tesseract OCR if not installed.
"""
import threading
import customtkinter as ctk
from tkinter import filedialog
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, ContentPreview, InputField, TagInput, ActionButton, StatusBar, Tooltip
from core.ocr import (
    ocr_from_clipboard, ocr_from_file,
    HAS_TESSERACT, _TESSERACT_FOUND, install_tesseract,
)
from core.database import add_entry


class OcrPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # Header
        PageHeader(
            container, icon="📸", title="Screenshot OCR",
            subtitle="Extract text from screenshots and images (auto-installs Tesseract OCR)"
        ).pack(fill="x", pady=(0, 15))

        # Info box
        info = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        info.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(
            info,
            text="💡 How to use:\n"
                 "  1. Take a screenshot (Win+Shift+S) or open an image file\n"
                 "  2. Click 'OCR from Clipboard' or 'OCR from File'\n"
                 "  3. Tesseract OCR will auto-download on first use (~70 MB)\n"
                 "  4. Preview and edit the extracted text, then save",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
            justify="left",
        ).pack(padx=15, pady=12, anchor="w")

        # Buttons
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        btn_clipboard = ActionButton(
            btn_row, text="📋  OCR from Clipboard",
            command=self._ocr_clipboard, style="primary", width=200
        )
        btn_clipboard.pack(side="left", padx=(0, 8))
        Tooltip(btn_clipboard, "Reads an image from your clipboard and extracts text.\nWorkflow: Press Win+Shift+S → select area → click this.\nPerfect for grabbing text from images on websites,\nPDFs with image-based text, or game screenshots.\nRequires Tesseract OCR installed on your system.")

        btn_file = ActionButton(
            btn_row, text="📁  OCR from Image File",
            command=self._ocr_file, style="secondary", width=200
        )
        btn_file.pack(side="left", padx=(0, 8))
        Tooltip(btn_file, "Opens a file dialog to select a saved image.\nSupports PNG, JPG, BMP, GIF, TIFF, and WebP.\nExtracts all readable text from the image.")

        btn_clear = ActionButton(
            btn_row, text="🗑  Clear", command=self._clear,
            style="secondary", width=100
        )
        btn_clear.pack(side="left")
        Tooltip(btn_clear, "Clears the preview and all fields.")

        # Title
        self.title_field = InputField(
            container, label_text="Title",
            placeholder="Describe what this image content is about"
        )
        self.title_field.pack(fill="x", pady=(0, 10))

        # Content Preview
        self.preview = ContentPreview(container, label_text="OCR Result (editable)", height=350)
        self.preview.pack(fill="both", expand=True, pady=(0, 10))

        # Tags & Category
        self.tag_input = TagInput(container)
        self.tag_input.pack(fill="x", pady=(0, 15))

        # Save
        save_row = ctk.CTkFrame(container, fg_color="transparent")
        save_row.pack(fill="x", pady=(0, 10))

        ActionButton(
            save_row, text="💾  Save to Library", command=self._save,
            style="success", width=180
        ).pack(side="left")

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))

    def _ocr_clipboard(self):
        self.status.set_working("Reading clipboard image...")

        def do_ocr():
            # Auto-install Tesseract if needed
            if not self._ensure_tesseract():
                return
            result = ocr_from_clipboard()
            self.after(0, lambda: self._handle_result(result))

        threading.Thread(target=do_ocr, daemon=True).start()

    def _ocr_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[
                ("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"),
                ("All Files", "*.*"),
            ]
        )
        if not file_path:
            return

        self.status.set_working("Extracting text from image...")

        def do_ocr():
            # Auto-install Tesseract if needed
            if not self._ensure_tesseract():
                return
            result = ocr_from_file(file_path)
            self.after(0, lambda: self._handle_result(result))

        threading.Thread(target=do_ocr, daemon=True).start()

    def _ensure_tesseract(self):
        """Check for Tesseract and auto-install if missing. Returns True if ready."""
        from core import ocr as _ocr_mod
        if not _ocr_mod.HAS_TESSERACT:
            self.after(0, lambda: self.status.set_error(
                "pytesseract package not installed — go to Setup tab, run Step 2"
            ))
            return False

        if _ocr_mod._TESSERACT_FOUND:
            return True

        # Auto-download and install
        def _progress(msg):
            self.after(0, lambda m=msg: self.status.set_working(m))

        _progress("Tesseract not found — downloading automatically...")
        ok, msg = install_tesseract(on_progress=_progress)
        if ok:
            self.after(0, lambda: self.status.set_working("Tesseract installed! Running OCR..."))
            return True
        else:
            self.after(0, lambda m=msg: self.status.set_error(f"Auto-install failed: {m}"))
            return False

    def _handle_result(self, result):
        if result["success"]:
            self.preview.set_text(result["content"])
            word_count = len(result["content"].split())
            self.status.set_success(f"Extracted {word_count:,} words from image")
        else:
            self.status.set_error(result["error"])

    def _save(self):
        title = self.title_field.get()
        content = self.preview.get_text()

        if not content:
            self.status.set_error("Nothing to save - run OCR first")
            return
        if not title:
            title = "OCR Screenshot"

        entry_id = add_entry(
            title=title,
            content=content,
            source_type="ocr",
            tags=self.tag_input.get_tags(),
            category=self.tag_input.get_category(),
        )

        self.status.set_success(f"Saved! (Entry #{entry_id})")
        if self.app:
            self.app.refresh_stats()

    def _clear(self):
        self.title_field.clear()
        self.preview.clear()
        self.tag_input.clear()
        self.status.set_status("Cleared")
