"""
Site Crawler Page - Crawl a website N levels deep, scraping every page.
Like a smarter bulk scraper that discovers links automatically.
"""
import threading
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, InputField, TagInput, ActionButton, StatusBar, Tooltip
from core.site_crawler import crawl_site
from core.database import add_entry, url_exists
from core.quality import score_entry_quick


class SiteCrawlerPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self._cancel_flag = False
        self._running = False
        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # Header
        PageHeader(
            container, icon="🕷", title="Site Crawler",
            subtitle="Start at a URL, follow links N levels deep, scrape everything"
        ).pack(fill="x", pady=(0, 12))

        # URL Input
        self.url_field = InputField(
            container, label_text="Starting URL",
            placeholder="https://docs.example.com/guide/introduction"
        )
        self.url_field.pack(fill="x", pady=(0, 10))
        Tooltip(self.url_field, "The starting page URL.\nThe crawler will scrape this page, find all links,\nthen follow those links and repeat up to N levels deep.\nGreat for documentation sites, wikis, forum sections.")

        # Settings row
        settings_row = ctk.CTkFrame(container, fg_color=COLORS["bg_card"], corner_radius=10)
        settings_row.pack(fill="x", pady=(0, 10))

        settings_inner = ctk.CTkFrame(settings_row, fg_color="transparent")
        settings_inner.pack(fill="x", padx=15, pady=12)

        # Depth slider
        depth_frame = ctk.CTkFrame(settings_inner, fg_color="transparent")
        depth_frame.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(
            depth_frame, text="Crawl Depth",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        depth_row = ctk.CTkFrame(depth_frame, fg_color="transparent")
        depth_row.pack(anchor="w")

        self.depth_var = ctk.IntVar(value=2)
        self.depth_label = ctk.CTkLabel(
            depth_row, text="2",
            font=(FONT_FAMILY, FONT_SIZES["heading"], "bold"),
            text_color=COLORS["accent"],
            width=30,
        )
        self.depth_label.pack(side="left")

        self.depth_slider = ctk.CTkSlider(
            depth_row, from_=1, to=5, number_of_steps=4,
            variable=self.depth_var,
            width=120,
            fg_color=COLORS["bg_input"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=lambda v: self.depth_label.configure(text=str(int(v))),
        )
        self.depth_slider.pack(side="left", padx=(5, 0))
        Tooltip(depth_frame, "How many levels deep to follow links.\n1 = only links on the starting page\n2 = links found on those pages too\n3+ = deeper (more pages, takes longer)\nRecommended: 2 for most sites")

        # Max pages
        pages_frame = ctk.CTkFrame(settings_inner, fg_color="transparent")
        pages_frame.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(
            pages_frame, text="Max Pages",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        self.max_pages_var = ctk.StringVar(value="50")
        self.max_pages_entry = ctk.CTkEntry(
            pages_frame, textvariable=self.max_pages_var,
            width=80, height=30,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=6,
        )
        self.max_pages_entry.pack(anchor="w", pady=(2, 0))
        Tooltip(pages_frame, "Maximum number of pages to scrape.\nThe crawler stops after this many.\n50 is a good default for most sites.\nSet higher for large documentation sites.")

        # Delay
        delay_frame = ctk.CTkFrame(settings_inner, fg_color="transparent")
        delay_frame.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(
            delay_frame, text="Delay (sec)",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        self.delay_var = ctk.StringVar(value="0.5")
        ctk.CTkEntry(
            delay_frame, textvariable=self.delay_var,
            width=60, height=30,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=6,
        ).pack(anchor="w", pady=(2, 0))
        Tooltip(delay_frame, "Seconds to wait between requests.\nBe polite — 0.5s is good for most sites.\nSet to 1.0+ for smaller servers.\n0.2 is OK for large sites like GitHub.")

        # Same domain toggle
        domain_frame = ctk.CTkFrame(settings_inner, fg_color="transparent")
        domain_frame.pack(side="left")

        ctk.CTkLabel(
            domain_frame, text="Same Domain Only",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        self.same_domain_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            domain_frame, text="", variable=self.same_domain_var,
            fg_color=COLORS["bg_input"],
            progress_color=COLORS["accent"],
            button_color=COLORS["text_secondary"],
            button_hover_color=COLORS["accent"],
            width=40,
        ).pack(anchor="w", pady=(4, 0))
        Tooltip(domain_frame, "When ON: only follows links on the same domain.\nWhen OFF: follows links to external sites too.\nKeep ON for scraping a single documentation site.\nTurn OFF if you want to discover cross-linked resources.")

        # Button row
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        self.btn_start = ActionButton(
            btn_row, text="🕷  Start Crawl", command=self._start_crawl,
            style="primary", width=160
        )
        self.btn_start.pack(side="left", padx=(0, 8))
        Tooltip(self.btn_start, "Start crawling from the URL.\nFinds links on each page and follows them.\nAll scraped pages are auto-saved to your library.")

        self.btn_cancel = ActionButton(
            btn_row, text="⏹  Cancel", command=self._cancel_crawl,
            style="danger", width=120
        )
        self.btn_cancel.pack(side="left")
        self.btn_cancel.configure(state="disabled")

        # Tags
        self.tag_input = TagInput(container)
        self.tag_input.pack(fill="x", pady=(0, 10))

        # Progress bar
        self.progress = ctk.CTkProgressBar(
            container,
            fg_color=COLORS["bg_input"],
            progress_color=COLORS["accent"],
            height=6,
            corner_radius=3,
        )
        self.progress.pack(fill="x", pady=(0, 4))
        self.progress.set(0)

        self.progress_label = ctk.CTkLabel(
            container, text="Ready to crawl",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.progress_label.pack(anchor="w", pady=(0, 8))

        # Results log
        ctk.CTkLabel(
            container, text="📋 Crawl Log",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(0, 4))

        self.log = ctk.CTkTextbox(
            container, height=280,
            font=("Consolas", 11),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
            state="disabled",
        )
        self.log.pack(fill="both", expand=True, pady=(0, 8))

        # Status
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))

    def _log_msg(self, text):
        """Append a line to the log."""
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start_crawl(self):
        url = self.url_field.get()
        if not url:
            self.status.set_error("Enter a starting URL")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.url_field.set(url)

        try:
            max_pages = int(self.max_pages_var.get())
        except ValueError:
            max_pages = 50

        try:
            delay = float(self.delay_var.get())
        except ValueError:
            delay = 0.5

        depth = self.depth_var.get()
        same_domain = self.same_domain_var.get()

        # Reset UI
        self._cancel_flag = False
        self._running = True
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.set(0)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._log_msg(f"🕷 Starting crawl: {url}")
        self._log_msg(f"   Depth: {depth} | Max pages: {max_pages} | Delay: {delay}s | Same domain: {same_domain}")
        self._log_msg("")

        tags = self.tag_input.get_tags()
        category = self.tag_input.get_category()

        def do_crawl():
            def on_progress(scraped, discovered, current_url, result):
                self.after(0, lambda: self._update_progress(scraped, discovered, max_pages, current_url, result, tags, category))

            def should_cancel():
                return self._cancel_flag

            results = crawl_site(
                start_url=url,
                max_depth=depth,
                max_pages=max_pages,
                delay=delay,
                same_domain=same_domain,
                on_progress=on_progress,
                should_cancel=should_cancel,
            )
            self.after(0, lambda: self._crawl_done(results))

        threading.Thread(target=do_crawl, daemon=True).start()

    def _update_progress(self, scraped, discovered, max_pages, current_url, result, tags, category):
        """Called from the crawl thread via self.after."""
        progress_val = min(scraped / max(max_pages, 1), 1.0)
        self.progress.set(progress_val)
        self.progress_label.configure(
            text=f"Scraped {scraped} pages | Discovered {discovered} links | Current: {current_url[:60]}..."
        )

        if result and result.get("success"):
            # Auto-save to library (skip duplicates)
            existing = url_exists(result["url"])
            if existing:
                self._log_msg(f"  ⏭ SKIP (duplicate): {result['url'][:70]}")
            else:
                # Quality score
                try:
                    _s, _e, _g = score_entry_quick(result.get("content", ""))
                    q_str = f"{_e}{_s}"
                except Exception:
                    q_str = ""

                entry_id = add_entry(
                    title=result.get("title", result["url"]),
                    content=result["content"],
                    source_type="web",
                    source_url=result["url"],
                    tags=tags,
                    category=category,
                )
                wc = result.get("word_count", 0)
                d = result.get("depth", 0)
                self._log_msg(f"  ✅ #{entry_id} | d={d} | {wc:,}w | {q_str} | {result['title'][:55]}")
        elif result and result.get("error"):
            self._log_msg(f"  ❌ {result.get('error', 'Failed')[:40]} | {current_url[:55]}")

    def _cancel_crawl(self):
        self._cancel_flag = True
        self._log_msg("\n⏹ Cancelling crawl...")
        self.btn_cancel.configure(state="disabled")

    def _crawl_done(self, results):
        self._running = False
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.progress.set(1.0)

        total = len(results)
        total_words = sum(r.get("word_count", 0) for r in results)

        self._log_msg(f"\n{'='*50}")
        self._log_msg(f"🏁 Crawl complete! {total} pages scraped, {total_words:,} total words")

        if self._cancel_flag:
            self._log_msg("   (Cancelled early by user)")
            self.status.set_status(f"Crawl cancelled — saved {total} pages")
        else:
            self.status.set_success(f"Done! Scraped {total} pages ({total_words:,} words)")

        if self.app:
            self.app.refresh_stats()
