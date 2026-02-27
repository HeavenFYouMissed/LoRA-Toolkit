"""
Bulk Scraper Page - Paste many URLs, scrape them all with a progress bar.
Auto-saves to library, skips duplicates, shows quality scores.
"""
import threading
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, ContentPreview, TagInput, ActionButton, StatusBar, Tooltip
from core.scraper import scrape_url
from core.database import add_entry, url_exists
from core.quality import score_entry_quick


class BulkScraperPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self._scraping = False
        self._cancel = False
        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # Header
        PageHeader(
            container, icon="⚡", title="Bulk URL Scraper",
            subtitle="Paste up to 100 URLs — scrape them all with progress tracking"
        ).pack(fill="x", pady=(0, 15))

        # URL input area
        url_label = ctk.CTkLabel(
            container, text="URLs (one per line):",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        )
        url_label.pack(anchor="w", pady=(0, 4))

        self.url_text = ctk.CTkTextbox(
            container, height=180,
            font=("Consolas", FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            wrap="none",
        )
        self.url_text.pack(fill="x", pady=(0, 10))
        Tooltip(self.url_text, "Paste URLs here, one per line.\nSupports up to 100 URLs at once.\nDuplicate URLs (already in your library) will be skipped.\nBlank lines and invalid URLs are ignored.")

        # Buttons row
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        self.btn_start = ActionButton(
            btn_row, text="⚡  Start Bulk Scrape", command=self._start_scrape,
            style="primary", width=200
        )
        self.btn_start.pack(side="left", padx=(0, 8))
        Tooltip(self.btn_start, "Scrapes ALL URLs in the box one by one.\nEach successful scrape is auto-saved to your library.\nDuplicate URLs are automatically skipped.\nYou can cancel mid-way — already-saved entries stay.")

        self.btn_cancel = ActionButton(
            btn_row, text="⏹  Cancel", command=self._cancel_scrape,
            style="danger", width=120
        )
        self.btn_cancel.pack(side="left", padx=(0, 8))
        self.btn_cancel.configure(state="disabled")
        Tooltip(self.btn_cancel, "Stop scraping after the current URL finishes.\nAlready-saved entries are kept in the library.")

        btn_clear = ActionButton(
            btn_row, text="🗑  Clear", command=self._clear,
            style="secondary", width=100
        )
        btn_clear.pack(side="left", padx=(0, 8))
        Tooltip(btn_clear, "Clear the URL list and results log.")

        btn_paste = ActionButton(
            btn_row, text="📋  Paste URLs", command=self._paste_clipboard,
            style="secondary", width=140
        )
        btn_paste.pack(side="left")
        Tooltip(btn_paste, "Paste URLs from your clipboard into the box.\nAppends to whatever is already there.")

        # URL count indicator
        self.url_count_label = ctk.CTkLabel(
            container, text="0 URLs entered",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.url_count_label.pack(anchor="w", pady=(0, 5))
        self.url_text.bind("<KeyRelease>", lambda e: self._update_url_count())

        # Tags & Category (applied to all)
        self.tag_input = TagInput(container)
        self.tag_input.pack(fill="x", pady=(0, 10))
        Tooltip(self.tag_input, "Tags and category are applied to ALL scraped entries.\nGreat for batch-labeling a whole topic at once.")

        # Progress bar
        progress_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        progress_frame.pack(fill="x", pady=(0, 10))

        self.progress_label = ctk.CTkLabel(
            progress_frame, text="Ready to scrape",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
        )
        self.progress_label.pack(anchor="w", padx=15, pady=(10, 5))

        self.progress_bar = ctk.CTkProgressBar(
            progress_frame,
            fg_color=COLORS["bg_input"],
            progress_color=COLORS["accent"],
            height=12,
            corner_radius=6,
        )
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 5))
        self.progress_bar.set(0)

        self.progress_stats = ctk.CTkLabel(
            progress_frame, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.progress_stats.pack(anchor="w", padx=15, pady=(0, 10))

        # Results log
        log_label = ctk.CTkLabel(
            container, text="Results Log:",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        )
        log_label.pack(anchor="w", pady=(5, 4))

        self.log_text = ctk.CTkTextbox(
            container, height=200,
            font=("Consolas", FONT_SIZES["small"]),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text_secondary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            wrap="word",
            state="disabled",
        )
        self.log_text.pack(fill="both", expand=True, pady=(0, 10))
        Tooltip(self.log_text, "Live results of each URL being scraped.\nShows success/fail, word count, quality score, and duplicates.")

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))

    def _get_urls(self):
        """Parse URLs from the text box."""
        text = self.url_text.get("1.0", "end-1c")
        urls = []
        for line in text.splitlines():
            url = line.strip()
            if not url:
                continue
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            urls.append(url)
        return urls

    def _update_url_count(self):
        urls = self._get_urls()
        self.url_count_label.configure(text=f"{len(urls)} URL{'s' if len(urls) != 1 else ''} entered")

    def _paste_clipboard(self):
        try:
            text = self.clipboard_get()
            if text:
                current = self.url_text.get("1.0", "end-1c")
                if current.strip():
                    self.url_text.insert("end", "\n" + text)
                else:
                    self.url_text.delete("1.0", "end")
                    self.url_text.insert("1.0", text)
                self._update_url_count()
        except Exception:
            self.status.set_error("Nothing in clipboard")

    def _log(self, message):
        """Append to the results log."""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _start_scrape(self):
        urls = self._get_urls()
        if not urls:
            self.status.set_error("No URLs entered")
            return

        if self._scraping:
            return

        self._scraping = True
        self._cancel = False
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")

        # Clear log
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.progress_bar.set(0)
        self.progress_label.configure(text=f"Scraping 0/{len(urls)}...")
        self.status.set_working(f"Starting bulk scrape of {len(urls)} URLs...")

        tags = self.tag_input.get_tags()
        category = self.tag_input.get_category()

        threading.Thread(
            target=self._scrape_worker,
            args=(urls, tags, category),
            daemon=True,
        ).start()

    def _scrape_worker(self, urls, tags, category):
        """Background worker that scrapes all URLs."""
        total = len(urls)
        saved = 0
        skipped = 0
        failed = 0

        for i, url in enumerate(urls):
            if self._cancel:
                self.after(0, lambda: self._log(f"\n⏹ Cancelled by user after {i} URLs"))
                break

            # Update progress
            self.after(0, lambda idx=i: self.progress_label.configure(
                text=f"Scraping {idx + 1}/{total}..."
            ))
            self.after(0, lambda idx=i: self.progress_bar.set((idx + 1) / total))

            # Check for duplicate
            existing = url_exists(url)
            if existing:
                skipped += 1
                self.after(0, lambda u=url, e=existing: self._log(
                    f"⏭ SKIP (duplicate #{e['id']}): {u[:80]}"
                ))
                continue

            # Scrape
            try:
                result = scrape_url(url)
            except Exception as e:
                failed += 1
                self.after(0, lambda u=url, err=str(e): self._log(
                    f"❌ FAIL: {u[:80]} — {err}"
                ))
                continue

            if not result["success"]:
                failed += 1
                self.after(0, lambda u=url, err=result["error"]: self._log(
                    f"❌ FAIL: {u[:80]} — {err}"
                ))
                continue

            # Quality check
            score, emoji, grade = score_entry_quick(result["content"])
            word_count = len(result["content"].split())

            # Save to library
            try:
                entry_id = add_entry(
                    title=result["title"],
                    content=result["content"],
                    source_type="web",
                    source_url=url,
                    tags=tags,
                    category=category,
                )
                saved += 1
                self.after(0, lambda u=url, wc=word_count, s=score, e=emoji, g=grade, eid=entry_id: self._log(
                    f"✅ #{eid} {e} {s}/100 ({g}) {wc:,}w — {u[:70]}"
                ))
            except Exception as e:
                failed += 1
                self.after(0, lambda u=url, err=str(e): self._log(
                    f"❌ SAVE FAIL: {u[:80]} — {err}"
                ))

            # Update stats line
            self.after(0, lambda s=saved, sk=skipped, f=failed: self.progress_stats.configure(
                text=f"✅ {s} saved  •  ⏭ {sk} skipped (dupes)  •  ❌ {f} failed"
            ))

        # Done
        self.after(0, lambda: self._scrape_done(saved, skipped, failed, total))

    def _scrape_done(self, saved, skipped, failed, total):
        self._scraping = False
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.progress_bar.set(1.0)
        self.progress_label.configure(text="Done!")

        summary = f"Finished! ✅ {saved} saved, ⏭ {skipped} duplicates skipped, ❌ {failed} failed (out of {total})"
        self._log(f"\n{'═' * 60}\n{summary}")
        self.progress_stats.configure(
            text=f"✅ {saved} saved  •  ⏭ {skipped} skipped  •  ❌ {failed} failed"
        )

        if saved > 0:
            self.status.set_success(summary)
        elif skipped == total:
            self.status.set_status("All URLs were already in your library!")
        else:
            self.status.set_error(summary)

        if self.app:
            self.app.refresh_stats()

    def _cancel_scrape(self):
        self._cancel = True
        self.status.set_working("Cancelling after current URL...")

    def handle_file_drop(self, paths):
        """Load URLs from a dropped text file into the URL list."""
        import os
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext in (".txt", ".csv", ".tsv", ".md", ".list"):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    existing = self.url_text.get("1.0", "end-1c").strip()
                    if existing:
                        self.url_text.insert("end", "\n" + content)
                    else:
                        self.url_text.delete("1.0", "end")
                        self.url_text.insert("1.0", content)
                    self._update_url_count()
                    self.status.set_success(f"Loaded URLs from: {os.path.basename(p)}")
                    return
                except Exception as e:
                    self.status.set_error(f"Could not read file: {e}")

    def _clear(self):
        self.url_text.delete("1.0", "end")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Ready to scrape")
        self.progress_stats.configure(text="")
        self._update_url_count()
        self.status.set_status("Cleared")
