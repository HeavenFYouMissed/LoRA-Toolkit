"""
YouTube Page - Extract transcripts from YouTube videos.
"""
import threading
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, ContentPreview, InputField, TagInput, ActionButton, StatusBar, Tooltip
from core.youtube import get_transcript, get_transcript_with_timestamps
from core.database import add_entry


class YoutubePage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # Header
        PageHeader(
            container, icon="📺", title="YouTube Transcripts",
            subtitle="Extract transcripts from YouTube videos for training data"
        ).pack(fill="x", pady=(0, 15))

        # URL Input
        self.url_field = InputField(
            container, label_text="YouTube URL or Video ID",
            placeholder="https://www.youtube.com/watch?v=... or just the video ID"
        )
        self.url_field.pack(fill="x", pady=(0, 10))
        Tooltip(self.url_field, "Paste a YouTube video URL or just the 11-character video ID.\nWorks with youtube.com/watch?v=... and youtu.be/... links.\nThe video must have captions/subtitles enabled.")

        # Buttons row
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        btn_transcript = ActionButton(
            btn_row, text="📥  Get Transcript", command=self._get_transcript,
            style="primary", width=180
        )
        btn_transcript.pack(side="left", padx=(0, 8))
        Tooltip(btn_transcript, "Downloads the video's auto-generated or manual transcript.\nReturns clean text without timestamps.\nGreat for training data — captures spoken content.\nWon't work if the video has captions disabled.")

        btn_timestamps = ActionButton(
            btn_row, text="⏱  With Timestamps", command=self._get_with_timestamps,
            style="secondary", width=180
        )
        btn_timestamps.pack(side="left", padx=(0, 8))
        Tooltip(btn_timestamps, "Same as Get Transcript but includes [MM:SS] timestamps.\nUseful for reference — know where info appears in the video.\nTimestamps are included in the text but can be\nremoved before saving if you prefer clean output.")

        btn_clear = ActionButton(
            btn_row, text="🗑  Clear", command=self._clear,
            style="secondary", width=100
        )
        btn_clear.pack(side="left")
        Tooltip(btn_clear, "Clears all fields on this page.\nDoesn't delete anything from your library.")

        # Title
        self.title_field = InputField(
            container, label_text="Title",
            placeholder="Auto-filled from video title"
        )
        self.title_field.pack(fill="x", pady=(0, 10))

        # Content Preview
        self.preview = ContentPreview(container, label_text="Transcript Content (editable)")
        self.preview.pack(fill="both", expand=True, pady=(0, 10))

        # Batch section
        batch_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        batch_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            batch_frame,
            text="📋 Batch Mode: Paste multiple YouTube URLs (one per line)",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.batch_text = ctk.CTkTextbox(
            batch_frame, height=80,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
        )
        self.batch_text.pack(fill="x", padx=15, pady=(0, 5))

        btn_batch = ActionButton(
            batch_frame, text="📥  Fetch All Transcripts", command=self._batch_fetch,
            style="primary", width=200
        )
        btn_batch.pack(padx=15, pady=(0, 10), anchor="w")
        Tooltip(btn_batch, "Fetches transcripts for ALL URLs in the batch box.\nEach transcript is saved as its own entry with the\nvideo title auto-detected. Failed videos are skipped.\nTags and category below are applied to all.")

        Tooltip(self.batch_text, "Paste multiple YouTube URLs here, one per line.\nAll transcripts will be fetched and saved automatically.\nGreat for grabbing a whole playlist or channel's content.")

        # Tags & Category
        self.tag_input = TagInput(container)
        self.tag_input.pack(fill="x", pady=(0, 15))
        Tooltip(self.tag_input, "Tags and category are applied to everything you save.\nFor batch mode, all videos get the same tags/category.\nYou can always change them later in the Library tab.")

        # Save button
        save_row = ctk.CTkFrame(container, fg_color="transparent")
        save_row.pack(fill="x", pady=(0, 10))

        btn_save = ActionButton(
            save_row, text="💾  Save to Library", command=self._save,
            style="success", width=180
        )
        btn_save.pack(side="left")
        Tooltip(btn_save, "Saves the single transcript shown in the preview.\nFor multiple videos, use Batch Mode + Fetch All instead.")

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))

    def _get_transcript(self):
        url = self.url_field.get()
        if not url:
            self.status.set_error("Enter a YouTube URL or video ID")
            return

        self.status.set_working("Fetching transcript...")

        def do_fetch():
            result = get_transcript(url)
            self.after(0, lambda: self._handle_result(result))

        threading.Thread(target=do_fetch, daemon=True).start()

    def _get_with_timestamps(self):
        url = self.url_field.get()
        if not url:
            self.status.set_error("Enter a YouTube URL or video ID")
            return

        self.status.set_working("Fetching transcript with timestamps...")

        def do_fetch():
            text, error = get_transcript_with_timestamps(url)
            if text:
                result = get_transcript(url)
                result["content"] = text  # Replace with timestamped version
            else:
                result = {"success": False, "error": error or "Failed", "title": "", "content": ""}
            self.after(0, lambda: self._handle_result(result))

        threading.Thread(target=do_fetch, daemon=True).start()

    def _handle_result(self, result):
        if result["success"]:
            self.title_field.set(result.get("title", ""))
            self.preview.set_text(result["content"])
            word_count = len(result["content"].split())
            self.status.set_success(f"Got transcript: {word_count:,} words")
        else:
            self.status.set_error(result["error"])

    def _batch_fetch(self):
        urls_text = self.batch_text.get("1.0", "end-1c").strip()
        if not urls_text:
            self.status.set_error("Paste YouTube URLs in the batch box (one per line)")
            return

        urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
        self.status.set_working(f"Fetching {len(urls)} transcripts...")

        def do_batch():
            saved = 0
            failed = 0
            for url in urls:
                result = get_transcript(url)
                if result["success"]:
                    add_entry(
                        title=result.get("title", f"YouTube: {url}"),
                        content=result["content"],
                        source_type="youtube",
                        source_url=result.get("url", url),
                        tags=self.tag_input.get_tags(),
                        category=self.tag_input.get_category(),
                    )
                    saved += 1
                else:
                    failed += 1

            self.after(0, lambda: self._batch_done(saved, failed))

        threading.Thread(target=do_batch, daemon=True).start()

    def _batch_done(self, saved, failed):
        msg = f"Batch complete: {saved} saved"
        if failed:
            msg += f", {failed} failed"
        self.status.set_success(msg)
        if self.app:
            self.app.refresh_stats()

    def _save(self):
        title = self.title_field.get()
        content = self.preview.get_text()

        if not content:
            self.status.set_error("Nothing to save - fetch a transcript first")
            return
        if not title:
            title = "Untitled YouTube Transcript"

        entry_id = add_entry(
            title=title,
            content=content,
            source_type="youtube",
            source_url=self.url_field.get(),
            tags=self.tag_input.get_tags(),
            category=self.tag_input.get_category(),
        )

        self.status.set_success(f"Saved! (Entry #{entry_id})")
        if self.app:
            self.app.refresh_stats()

    def _clear(self):
        self.url_field.clear()
        self.title_field.clear()
        self.preview.clear()
        self.tag_input.clear()
        self.batch_text.delete("1.0", "end")
        self.status.set_status("Cleared")
