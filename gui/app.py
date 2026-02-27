"""
Main Application Window - Sidebar navigation + page switching.
"""
import ctypes
import customtkinter as ctk
from config import APP_NAME, WINDOW_WIDTH, WINDOW_HEIGHT, SIDEBAR_WIDTH
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from core.database import get_stats
from core.settings import load_settings
from core.tray import setup_tray, hide_to_tray, destroy_tray
from core.hotkeys import register_hotkeys, unregister_all as unregister_hotkeys
from gui.widgets import setup_global_context_menu, HAS_WINDND


def _apply_mica(window):
    """Apply Windows 11 Mica/dark titlebar effect."""
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20,
            ctypes.byref(ctypes.c_int(1)),
            ctypes.sizeof(ctypes.c_int)
        )
        # DWMWA_MICA_EFFECT = 1029 (Windows 11 22H2+)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 1029,
            ctypes.byref(ctypes.c_int(1)),
            ctypes.sizeof(ctypes.c_int)
        )
    except Exception:
        pass  # Not Windows 11 or not supported, no big deal


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ─── Window Setup ───────────────────────────────────
        self.title(APP_NAME)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(900, 600)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color=COLORS["bg_dark"])

        # Apply Mica dark titlebar after window is drawn
        self.after(100, lambda: _apply_mica(self))

        # Load user settings
        self.settings = load_settings()

        # Apply saved settings (default to fully opaque — avoids drag lag)
        opacity = self.settings.get("window_opacity", 1.0)
        if opacity < 1.0:
            self.attributes("-alpha", opacity)
        self.attributes("-topmost", self.settings.get("always_on_top", False))

        # ─── Layout ─────────────────────────────────────────
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self._create_sidebar()

        # Main content area
        self.main_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        # Pages dict
        self.pages = {}
        self.current_page = None
        self._create_pages()

        # Show default page
        self.show_page("scraper")

        # ─── Global right-click context menus ───────────────
        setup_global_context_menu(self)

        # ─── Global file drag-and-drop ──────────────────────
        if HAS_WINDND:
            import windnd
            try:
                windnd.hook_dropfiles(self, func=self._on_global_drop)
            except Exception:
                pass

        # ─── System Tray ────────────────────────────────────
        self._tray = None
        if self.settings.get("minimize_to_tray", True):
            try:
                self._tray = setup_tray(self)
            except Exception as e:
                print(f"[Tray] Could not start: {e}")

        # Override window close (X button) to tray
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ─── Global Hotkeys ─────────────────────────────────
        try:
            register_hotkeys(self, self.settings)
        except Exception as e:
            print(f"[Hotkeys] Could not register: {e}")

    def _create_sidebar(self):
        """Build the left sidebar with navigation buttons."""
        sidebar = ctk.CTkFrame(
            self, width=SIDEBAR_WIDTH,
            fg_color=COLORS["bg_sidebar"],
            corner_radius=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        # App title
        title_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(20, 5))

        ctk.CTkLabel(
            title_frame,
            text="🧠 LoRA",
            font=(FONT_FAMILY, 22, "bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_frame,
            text="Data Toolkit",
            font=(FONT_FAMILY, 14),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        # Divider with accent glow
        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["accent_dim"]).pack(
            fill="x", padx=15, pady=(15, 4)
        )
        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["divider"]).pack(
            fill="x", padx=20, pady=(0, 10)
        )

        # Section label: COLLECT
        ctk.CTkLabel(
            sidebar,
            text="  COLLECT DATA",
            font=(FONT_FAMILY, FONT_SIZES["tiny"], "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=15, pady=(10, 5))

        # Navigation buttons
        self.nav_buttons = {}
        nav_items = [
            ("scraper", "🌐  Web Scraper"),
            ("bulk", "⚡  Bulk Scraper"),
            ("crawler", "🕷  Site Crawler"),
            ("youtube", "📺  YouTube"),
            ("paste", "📋  Paste Text"),
            ("ocr", "📸  Screenshot OCR"),
            ("import", "📁  Import Files"),
        ]

        for page_id, label in nav_items:
            btn = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                font=(FONT_FAMILY, FONT_SIZES["body"]),
                fg_color="transparent",
                text_color=COLORS["text_secondary"],
                hover_color=COLORS["bg_hover"],
                height=36,
                corner_radius=8,
                command=lambda pid=page_id: self.show_page(pid),
            )
            btn.pack(fill="x", padx=10, pady=1)
            self.nav_buttons[page_id] = btn

        # Section label: MANAGE
        ctk.CTkLabel(
            sidebar,
            text="  MANAGE",
            font=(FONT_FAMILY, FONT_SIZES["tiny"], "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=15, pady=(20, 5))

        manage_items = [
            ("library", "📚  Data Library"),
            ("export", "🚀  Export LoRA"),
        ]
        for page_id, label in manage_items:
            btn = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                font=(FONT_FAMILY, FONT_SIZES["body"]),
                fg_color="transparent",
                text_color=COLORS["text_secondary"],
                hover_color=COLORS["bg_hover"],
                height=36,
                corner_radius=8,
                command=lambda pid=page_id: self.show_page(pid),
            )
            btn.pack(fill="x", padx=10, pady=1)
            self.nav_buttons[page_id] = btn

        # Section label: TRAIN
        ctk.CTkLabel(
            sidebar,
            text="  TRAIN",
            font=(FONT_FAMILY, FONT_SIZES["tiny"], "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=15, pady=(20, 5))

        train_btn = ctk.CTkButton(
            sidebar,
            text="🧬  Train Model",
            anchor="w",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            hover_color=COLORS["bg_hover"],
            height=36,
            corner_radius=8,
            command=lambda: self.show_page("training"),
        )
        train_btn.pack(fill="x", padx=10, pady=1)
        self.nav_buttons["training"] = train_btn

        merge_btn = ctk.CTkButton(
            sidebar,
            text="🔀  Merge Models",
            anchor="w",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            hover_color=COLORS["bg_hover"],
            height=36,
            corner_radius=8,
            command=lambda: self.show_page("merge"),
        )
        merge_btn.pack(fill="x", padx=10, pady=1)
        self.nav_buttons["merge"] = merge_btn

        # Section label: APP
        ctk.CTkLabel(
            sidebar,
            text="  APP",
            font=(FONT_FAMILY, FONT_SIZES["tiny"], "bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=15, pady=(20, 5))

        setup_btn = ctk.CTkButton(
            sidebar,
            text="🖥️  Setup / GPU",
            anchor="w",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            hover_color=COLORS["bg_hover"],
            height=36,
            corner_radius=8,
            command=lambda: self.show_page("setup"),
        )
        setup_btn.pack(fill="x", padx=10, pady=1)
        self.nav_buttons["setup"] = setup_btn

        settings_btn = ctk.CTkButton(
            sidebar,
            text="⚙️  Settings",
            anchor="w",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            hover_color=COLORS["bg_hover"],
            height=36,
            corner_radius=8,
            command=lambda: self.show_page("settings"),
        )
        settings_btn.pack(fill="x", padx=10, pady=1)
        self.nav_buttons["settings"] = settings_btn

        # Stats at bottom
        spacer = ctk.CTkFrame(sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        self.stats_frame = ctk.CTkFrame(sidebar, fg_color=COLORS["bg_card"], corner_radius=10)
        self.stats_frame.pack(fill="x", padx=10, pady=(0, 15))

        self.stats_label = ctk.CTkLabel(
            self.stats_frame,
            text="Loading...",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            justify="left",
        )
        self.stats_label.pack(padx=12, pady=10, anchor="w")

        self._update_stats()

        # ─── Sidebar right-edge glow line ────────────────
        glow_line = ctk.CTkFrame(
            self, width=1, fg_color=COLORS["accent_dim"],
            corner_radius=0,
        )
        glow_line.grid(row=0, column=0, sticky="nse")

    def _create_pages(self):
        """Create all pages (lazy loaded into the main frame)."""
        from gui.pages.scraper_page import ScraperPage
        from gui.pages.bulk_scraper_page import BulkScraperPage
        from gui.pages.site_crawler_page import SiteCrawlerPage
        from gui.pages.youtube_page import YoutubePage
        from gui.pages.paste_page import PastePage
        from gui.pages.ocr_page import OcrPage
        from gui.pages.import_page import ImportPage
        from gui.pages.library_page import LibraryPage
        from gui.pages.export_page import ExportPage
        from gui.pages.training_page import TrainingPage
        from gui.pages.merge_page import MergePage
        from gui.pages.setup_page import SetupPage
        from gui.pages.settings_page import SettingsPage

        page_classes = {
            "scraper": ScraperPage,
            "bulk": BulkScraperPage,
            "crawler": SiteCrawlerPage,
            "youtube": YoutubePage,
            "paste": PastePage,
            "ocr": OcrPage,
            "import": ImportPage,
            "library": LibraryPage,
            "export": ExportPage,
            "training": TrainingPage,
            "merge": MergePage,
            "setup": SetupPage,
            "settings": SettingsPage,
        }

        for page_id, page_class in page_classes.items():
            page = page_class(self.main_frame, app=self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[page_id] = page

    def show_page(self, page_id):
        """Switch to a page."""
        if page_id == self.current_page:
            return

        # Update nav button styles with glow effect
        for pid, btn in self.nav_buttons.items():
            if pid == page_id:
                btn.configure(
                    fg_color=COLORS["accent"],
                    text_color=COLORS["text_primary"],
                    hover_color=COLORS["accent_hover"],
                    border_color=COLORS["accent_dim"],
                    border_width=1,
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=COLORS["text_secondary"],
                    hover_color=COLORS["bg_hover"],
                    border_width=0,
                )

        # Show page
        page = self.pages.get(page_id)
        if page:
            page.tkraise()
            self.current_page = page_id

            # Refresh library/export when switching to them
            if page_id in ("library", "export", "settings") and hasattr(page, "refresh"):
                page.refresh()

        self._update_stats()

    def _update_stats(self):
        """Update the stats display in the sidebar."""
        try:
            stats = get_stats()
            text = (
                f"📊 {stats['total_entries']} entries\n"
                f"📝 {stats['total_words']:,} words\n"
                f"📦 {stats['total_exports']} exports"
            )
            self.stats_label.configure(text=text)
        except Exception:
            self.stats_label.configure(text="📊 Ready")

    def refresh_stats(self):
        """Public method for pages to trigger stats refresh."""
        self._update_stats()

    def _on_close(self):
        """Handle window close button (X). Minimize to tray or quit."""
        if self.settings.get("minimize_to_tray", True) and self._tray:
            hide_to_tray(self)
        else:
            self._shutdown()

    def _on_global_drop(self, file_list):
        """Central windnd handler — route dropped files to the active page."""
        import os
        paths = []
        for f in file_list:
            path = f.decode("utf-8", errors="replace") if isinstance(f, bytes) else str(f)
            if os.path.isfile(path):
                paths.append(path)
            elif os.path.isdir(path):
                for root, _dirs, files in os.walk(path):
                    for fname in files:
                        paths.append(os.path.join(root, fname))
        if not paths:
            return

        page = self.pages.get(self.current_page)
        if page and hasattr(page, "handle_file_drop"):
            page.handle_file_drop(paths)

    def _shutdown(self):
        """Full application shutdown."""
        try:
            unregister_hotkeys()
        except Exception:
            pass
        try:
            destroy_tray()
        except Exception:
            pass
        self.destroy()
