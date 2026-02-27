"""
Web Scraper Page - Paste a URL, preview content, save to library.
"""
import threading
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, ContentPreview, InputField, TagInput, ActionButton, StatusBar, Tooltip
from core.scraper import scrape_url
from core.database import add_entry, url_exists
from core.quality import score_entry


class ScraperPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        # Scrollable container
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # Header
        PageHeader(
            container, icon="🌐", title="Web Scraper",
            subtitle="Paste a URL to extract text content from any webpage"
        ).pack(fill="x", pady=(0, 15))

        # URL Input
        self.url_field = InputField(
            container, label_text="URL",
            placeholder="https://docs.example.com/article/..."
        )
        self.url_field.pack(fill="x", pady=(0, 10))
        Tooltip(self.url_field, "Paste any webpage URL here.\nThe scraper will extract the main text content from the page.\nWorks with articles, docs, forum posts, GitHub pages, etc.")

        # Buttons row
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        btn_scrape = ActionButton(
            btn_row, text="🔍  Scrape URL", command=self._scrape,
            style="primary", width=160
        )
        btn_scrape.pack(side="left", padx=(0, 8))
        Tooltip(btn_scrape, "Scrapes ONE page at a time.\nExtracts the main text content (articles, posts, docs).\nStrips out ads, navbars, footers — just the good stuff.\nYou can preview and edit before saving.")

        btn_links = ActionButton(
            btn_row, text="🔗  Extract Links", command=self._extract_links,
            style="secondary", width=160
        )
        btn_links.pack(side="left", padx=(0, 8))
        Tooltip(btn_links, "Finds all links on the page (same domain only).\nUseful for discovering sub-pages to scrape.\nE.g. paste a forum index → see all thread links.\nDoesn't auto-scrape them — you pick which to grab.")

        btn_clear = ActionButton(
            btn_row, text="🗑  Clear", command=self._clear,
            style="secondary", width=100
        )
        btn_clear.pack(side="left")
        Tooltip(btn_clear, "Clears all fields on this page.\nDoesn't delete anything from your library.")

        # Title field (auto-filled from scrape)
        self.title_field = InputField(
            container, label_text="Title",
            placeholder="Auto-filled from page title (editable)"
        )
        self.title_field.pack(fill="x", pady=(0, 10))
        Tooltip(self.title_field, "Auto-filled from the page's <title> tag.\nEdit this to something descriptive — it's how you'll\nfind this entry later in the library and exports.")

        # Content Preview
        self.preview = ContentPreview(container, label_text="Scraped Content (editable)")
        self.preview.pack(fill="both", expand=True, pady=(0, 10))
        Tooltip(self.preview, "Preview of the scraped text.\nYou can edit this before saving!\nRemove junk, fix formatting, add context — this is\nexactly what goes into your training data.")

        # Tags & Category
        self.tag_input = TagInput(container)
        self.tag_input.pack(fill="x", pady=(0, 15))
        Tooltip(self.tag_input, "Tags: comma-separated labels (e.g. 'aimbot, detection').\nCategory: pick a topic bucket.\nBoth help organize and filter when you have 100s of entries.\nYou can also filter exports by these later.")

        # Save button
        save_row = ctk.CTkFrame(container, fg_color="transparent")
        save_row.pack(fill="x", pady=(0, 10))

        btn_save = ActionButton(
            save_row, text="💾  Save to Library", command=self._save,
            style="success", width=180
        )
        btn_save.pack(side="left")
        Tooltip(btn_save, "Saves the scraped content to your local database.\nStored in data/toolkit.db (SQLite — handles 100k+ entries).\nYou can view, edit, and delete entries in the Library tab.")

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))
        Tooltip(self.status, "Shows the result of your last action.\nGreen = success, Red = error, Yellow = working.")

    def _scrape(self):
        url = self.url_field.get()
        if not url:
            self.status.set_error("Enter a URL first")
            return

        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.url_field.set(url)

        self.status.set_working("Scraping...")

        def do_scrape():
            result = scrape_url(url)
            self.after(0, lambda: self._handle_scrape_result(result))

        threading.Thread(target=do_scrape, daemon=True).start()

    def _handle_scrape_result(self, result):
        if result["success"]:
            self.title_field.set(result["title"])
            self.preview.set_text(result["content"])
            word_count = len(result["content"].split())

            # Quality score
            q = score_entry(result["content"], result["title"])
            quality_msg = f"Scraped {word_count:,} words  •  Quality: {q['emoji']} {q['overall']}/100 ({q['grade']})"
            if q["issues"]:
                quality_msg += f"\n⚠ {', '.join(q['issues'][:2])}"

            # Duplicate check
            existing = url_exists(result["url"])
            if existing:
                quality_msg += f"\n⚠ DUPLICATE: This URL was already saved as entry #{existing['id']} ({existing['title'][:40]})"

            self.status.set_success(quality_msg)
        else:
            self.status.set_error(result["error"])

    def _extract_links(self):
        url = self.url_field.get()
        if not url:
            self.status.set_error("Enter a URL first")
            return

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        self.status.set_working("Extracting links...")

        def do_extract():
            from core.scraper import extract_links
            links = extract_links(url)
            self.after(0, lambda: self._handle_links(links))

        threading.Thread(target=do_extract, daemon=True).start()

    def _handle_links(self, links):
        if links:
            text = "\n".join(f"{link['text']} → {link['url']}" for link in links)
            self.preview.set_text(text)
            self.title_field.set("Extracted Links")
            self.status.set_success(f"Found {len(links)} links")
        else:
            self.status.set_error("No links found")

    def _save(self):
        title = self.title_field.get()
        content = self.preview.get_text()

        if not content:
            self.status.set_error("Nothing to save - scrape a URL first")
            return
        if not title:
            title = "Untitled Web Scrape"

        # Duplicate warning (still saves — just warns)
        url = self.url_field.get()
        existing = url_exists(url) if url else None

        entry_id = add_entry(
            title=title,
            content=content,
            source_type="web",
            source_url=url,
            tags=self.tag_input.get_tags(),
            category=self.tag_input.get_category(),
        )

        msg = f"Saved! (Entry #{entry_id})"
        if existing:
            msg += f"  ⚠ Note: URL was already saved as #{existing['id']}"
        self.status.set_success(msg)
        if self.app:
            self.app.refresh_stats()

    def _clear(self):
        self.url_field.clear()
        self.title_field.clear()
        self.preview.clear()
        self.tag_input.clear()
        self.status.set_status("Cleared")
