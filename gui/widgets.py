"""
Reusable custom widgets for the GUI.
"""
import os
import tkinter as tk
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES

# Try to import windnd for native drag-and-drop on Windows
try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False


# ─── Tooltip System ───────────────────────────────────────────────

class Tooltip:
    """
    Hover tooltip for any widget.
    Usage: Tooltip(widget, "This button does X")
    """
    DELAY_MS = 400  # delay before showing

    def __init__(self, widget, text, wrap_length=320):
        self.widget = widget
        self.text = text
        self.wrap_length = wrap_length
        self.tip_window = None
        self._after_id = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<ButtonPress>", self._cancel, add="+")

    def _schedule(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self, event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self):
        if self.tip_window or not self.text:
            return

        # Position near the widget
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)

        # Tooltip styling — dark card with accent border
        frame = tk.Frame(
            tw,
            background="#151b28",
            borderwidth=1,
            relief="solid",
            highlightbackground="#e94560",
            highlightthickness=1,
        )
        frame.pack()

        label = tk.Label(
            frame,
            text=self.text,
            justify="left",
            wraplength=self.wrap_length,
            background="#151b28",
            foreground="#e6edf3",
            font=(FONT_FAMILY, 11),
            padx=10,
            pady=6,
        )
        label.pack()

        # Keep tooltip on screen
        tw.update_idletasks()
        screen_w = tw.winfo_screenwidth()
        screen_h = tw.winfo_screenheight()
        tip_w = tw.winfo_width()
        tip_h = tw.winfo_height()

        if x + tip_w > screen_w - 10:
            x = screen_w - tip_w - 10
        if y + tip_h > screen_h - 10:
            y = self.widget.winfo_rooty() - tip_h - 4

        tw.wm_geometry(f"+{x}+{y}")

    def _hide(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

    def update_text(self, new_text):
        """Change tooltip text dynamically."""
        self.text = new_text


# ─── Global Right-Click Context Menu ─────────────────────────────

def setup_global_context_menu(root):
    """
    Bind right-click Cut / Copy / Paste / Select All to **every**
    Entry and Text widget in the application (including CTk wrappers).
    Call once from App.__init__().
    """
    _menu = tk.Menu(
        root, tearoff=0,
        bg="#1a1f2e", fg="#e6edf3",
        activebackground="#e94560", activeforeground="#ffffff",
        font=(FONT_FAMILY, 10),
        relief="flat", borderwidth=1,
    )

    def _show(event):
        w = event.widget
        is_text = isinstance(w, tk.Text)
        is_entry = isinstance(w, tk.Entry)
        if not (is_text or is_entry):
            return

        w.focus_set()
        _menu.delete(0, "end")

        # Detect read-only state
        state = str(w.cget("state"))
        readonly = state in ("disabled", "readonly")

        if not readonly:
            _menu.add_command(
                label="✂  Cut", accelerator="Ctrl+X",
                command=lambda: w.event_generate("<<Cut>>"),
            )
        _menu.add_command(
            label="📋 Copy", accelerator="Ctrl+C",
            command=lambda: w.event_generate("<<Copy>>"),
        )
        if not readonly:
            _menu.add_command(
                label="📄 Paste", accelerator="Ctrl+V",
                command=lambda: w.event_generate("<<Paste>>"),
            )
        _menu.add_separator()
        if is_text:
            _menu.add_command(
                label="🔘 Select All", accelerator="Ctrl+A",
                command=lambda: w.tag_add("sel", "1.0", "end"),
            )
        else:
            _menu.add_command(
                label="🔘 Select All", accelerator="Ctrl+A",
                command=lambda: w.select_range(0, "end"),
            )

        try:
            _menu.tk_popup(event.x_root, event.y_root)
        finally:
            _menu.grab_release()

    root.bind_all("<Button-3>", _show)


class StatusBar(ctk.CTkFrame):
    """Simple status bar at the bottom of a page."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=30, fg_color=COLORS["bg_dark"], **kwargs)
        self.label = ctk.CTkLabel(
            self,
            text="Ready",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.label.pack(side="left", padx=10)

    def set_status(self, text, color=None):
        self.label.configure(text=text, text_color=color or COLORS["text_muted"])

    def set_success(self, text):
        self.set_status(f"✓ {text}", COLORS["success"])

    def set_error(self, text):
        self.set_status(f"✗ {text}", COLORS["error"])

    def set_working(self, text):
        self.set_status(f"⏳ {text}", COLORS["accent_yellow"])


class ContentPreview(ctk.CTkFrame):
    """Large text preview area with word count."""

    def __init__(self, parent, label_text="Content Preview", height=300, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        # Header with label and word count
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text=label_text,
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left")

        self.word_count_label = ctk.CTkLabel(
            header,
            text="0 words",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.word_count_label.pack(side="right")

        # Text box
        self.textbox = ctk.CTkTextbox(
            self,
            height=height,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            wrap="word",
        )
        self.textbox.pack(fill="both", expand=True, pady=(5, 0))
        self.textbox.bind("<KeyRelease>", self._update_word_count)

        # Focus glow
        self.textbox.bind("<FocusIn>", lambda e: self.textbox.configure(border_color=COLORS.get("border_focus", COLORS["accent"]), border_width=2))
        self.textbox.bind("<FocusOut>", lambda e: self.textbox.configure(border_color=COLORS["border"], border_width=1))

    def get_text(self):
        return self.textbox.get("1.0", "end-1c").strip()

    def set_text(self, text):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)
        self._update_word_count()

    def clear(self):
        self.textbox.delete("1.0", "end")
        self._update_word_count()

    def _update_word_count(self, event=None):
        text = self.get_text()
        words = len(text.split()) if text else 0
        chars = len(text)
        self.word_count_label.configure(text=f"{words:,} words | {chars:,} chars")

    def set_readonly(self, readonly=True):
        self.textbox.configure(state="disabled" if readonly else "normal")


class InputField(ctk.CTkFrame):
    """Labeled input field."""

    def __init__(self, parent, label_text, placeholder="", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        ctk.CTkLabel(
            self,
            text=label_text,
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w")

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text=placeholder,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=38,
        )
        self.entry.pack(fill="x", pady=(4, 0))

        # Focus glow effect
        self.entry.bind("<FocusIn>", lambda e: self.entry.configure(border_color=COLORS.get("border_focus", COLORS["accent"]), border_width=2))
        self.entry.bind("<FocusOut>", lambda e: self.entry.configure(border_color=COLORS["border"], border_width=1))

    def get(self):
        return self.entry.get().strip()

    def set(self, text):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)

    def clear(self):
        self.entry.delete(0, "end")


class ActionButton(ctk.CTkButton):
    """Styled action button."""

    def __init__(self, parent, text, command=None, style="primary", width=140, **kwargs):
        colors = {
            "primary": (COLORS["accent"], COLORS["accent_hover"]),
            "success": (COLORS["accent_green"], "#7bed9f"),
            "secondary": (COLORS["bg_input"], COLORS["bg_hover"]),
            "danger": (COLORS["error"], "#ff6b81"),
            "warning": (COLORS["accent_orange"], "#fdcb6e"),
        }
        fg, hover = colors.get(style, colors["primary"])

        super().__init__(
            parent,
            text=text,
            command=command,
            width=width,
            height=38,
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            fg_color=fg,
            hover_color=hover,
            corner_radius=8,
            **kwargs,
        )


# ─── Animated Progress Indicator ──────────────────────────────────

class ProgressIndicator(ctk.CTkFrame):
    """
    Animated progress bar with phase label, percentage, and ETA.

    Modes:
      • determinate  – call set_progress(0.0 … 1.0)
      • indeterminate – call start_indeterminate() for a pulsing bar
    """

    def __init__(self, parent, height=22, **kwargs):
        super().__init__(parent, fg_color="transparent", height=height + 24, **kwargs)
        self.pack_propagate(False)

        # Phase label row  (e.g.  "Checking PyTorch…  42%")
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")

        self.phase_label = ctk.CTkLabel(
            top, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
        )
        self.phase_label.pack(side="left")

        self.pct_label = ctk.CTkLabel(
            top, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["accent"],
        )
        self.pct_label.pack(side="right")

        # Bar
        self.bar = ctk.CTkProgressBar(
            self, height=height,
            fg_color=COLORS["bg_input"],
            progress_color=COLORS["accent"],
            corner_radius=height // 2,
        )
        self.bar.pack(fill="x", pady=(3, 0))
        self.bar.set(0)

        self._indeterminate = False
        self._pulse_pos = 0.0
        self._pulse_dir = 1

    def set_phase(self, text: str):
        """Update the phase label (e.g. 'Checking PyTorch…')."""
        self.phase_label.configure(text=text)

    def set_progress(self, fraction: float, text: str = ""):
        """Set determinate progress (0.0 – 1.0)."""
        self._indeterminate = False
        fraction = max(0.0, min(1.0, fraction))
        self.bar.set(fraction)
        pct = int(fraction * 100)
        self.pct_label.configure(text=f"{pct}%")
        if text:
            self.phase_label.configure(text=text)

    def start_indeterminate(self, text: str = "Working…"):
        """Start a pulsing animation for unknown-duration tasks."""
        self._indeterminate = True
        self.phase_label.configure(text=text)
        self.pct_label.configure(text="")
        self._pulse()

    def stop(self, text: str = "Done"):
        """Stop animation and show completion."""
        self._indeterminate = False
        self.bar.set(1.0)
        self.phase_label.configure(text=text)
        self.pct_label.configure(text="✓")
        self.bar.configure(progress_color=COLORS["accent_green"])

    def reset(self):
        """Reset to empty state."""
        self._indeterminate = False
        self.bar.set(0)
        self.bar.configure(progress_color=COLORS["accent"])
        self.phase_label.configure(text="")
        self.pct_label.configure(text="")

    def _pulse(self):
        """Animate indeterminate bar with a bouncing pulse."""
        if not self._indeterminate:
            return
        self._pulse_pos += 0.02 * self._pulse_dir
        if self._pulse_pos >= 0.95:
            self._pulse_dir = -1
        elif self._pulse_pos <= 0.05:
            self._pulse_dir = 1
        self.bar.set(self._pulse_pos)
        self.after(30, self._pulse)


# ─── Placeholder Entry (fixes CTk placeholder bug) ───────────────

class PlaceholderEntry(ctk.CTkFrame):
    """
    Entry with a permanent hint label below it (not inside).
    Avoids the CTkEntry placeholder bug where text disappears on window focus.
    """

    def __init__(self, parent, hint_text="", width=500, height=32, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.entry = ctk.CTkEntry(
            self,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=6,
            width=width, height=height,
        )
        self.entry.pack(anchor="w")

        if hint_text:
            ctk.CTkLabel(
                self, text=f"💡 {hint_text}",
                font=(FONT_FAMILY, FONT_SIZES["tiny"]),
                text_color=COLORS["text_muted"],
            ).pack(anchor="w", pady=(1, 0))

    def get(self):
        return self.entry.get().strip()

    def set(self, text):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)

    def clear(self):
        self.entry.delete(0, "end")


class TagInput(ctk.CTkFrame):
    """Tags and category input fields."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")

        # Tags
        tags_frame = ctk.CTkFrame(row, fg_color="transparent")
        tags_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkLabel(
            tags_frame,
            text="Tags (comma-separated)",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w")

        self.tags_entry = ctk.CTkEntry(
            tags_frame,
            placeholder_text="e.g. cheat-detection, aimbot, memory-hacking",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            height=35,
        )
        self.tags_entry.pack(fill="x", pady=(2, 0))
        self.tags_entry.bind("<FocusIn>", lambda e: self.tags_entry.configure(border_color=COLORS.get("border_focus", COLORS["accent"]), border_width=2))
        self.tags_entry.bind("<FocusOut>", lambda e: self.tags_entry.configure(border_color=COLORS["border"], border_width=1))

        # Category
        cat_frame = ctk.CTkFrame(row, fg_color="transparent")
        cat_frame.pack(side="right", padx=(5, 0))

        ctk.CTkLabel(
            cat_frame,
            text="Category",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w")

        self.category_menu = ctk.CTkOptionMenu(
            cat_frame,
            values=["general", "cheat-detection", "game-hacking", "reverse-engineering",
                    "memory-editing", "anti-cheat", "tutorials", "tools", "other"],
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=200,
            height=35,
        )
        self.category_menu.pack(pady=(2, 0))

    def get_tags(self):
        return self.tags_entry.get().strip()

    def get_category(self):
        return self.category_menu.get()

    def clear(self):
        self.tags_entry.delete(0, "end")
        self.category_menu.set("general")


class PageHeader(ctk.CTkFrame):
    """Page title header with icon."""

    def __init__(self, parent, icon, title, subtitle="", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        ctk.CTkLabel(
            self,
            text=f"{icon}  {title}",
            font=(FONT_FAMILY, FONT_SIZES["title"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w")

        if subtitle:
            ctk.CTkLabel(
                self,
                text=subtitle,
                font=(FONT_FAMILY, FONT_SIZES["small"]),
                text_color=COLORS["text_muted"],
            ).pack(anchor="w", pady=(2, 0))

        # Accent underline
        ctk.CTkFrame(
            self, height=2,
            fg_color=COLORS.get("accent_dim", COLORS["accent"]),
            corner_radius=1,
        ).pack(fill="x", pady=(8, 0))


# ─── Drop Zone ────────────────────────────────────────────────────

class DropZone(ctk.CTkFrame):
    """
    Drag-and-drop file zone with dashed border.
    Click to open file dialog, or drag files from Explorer.
    Calls on_files_dropped(list_of_paths) when files are received.
    """

    def __init__(self, parent, on_files_dropped=None, height=160,
                 filetypes=None, text="Click to upload or drag and drop",
                 subtext="supports text files, csv's, PDFs, audio files, and more!", **kwargs):
        super().__init__(parent, fg_color="transparent", height=height, **kwargs)
        self.pack_propagate(False)

        self.on_files_dropped = on_files_dropped
        self.filetypes = filetypes
        self._drag_over = False

        # Outer border frame (simulates dashed border with double outline)
        self.border = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_card"],
            corner_radius=14,
            border_width=2,
            border_color=COLORS["border"],
        )
        self.border.pack(fill="both", expand=True, padx=4, pady=4)
        self.border.pack_propagate(False)

        # Inner content (centered)
        inner = ctk.CTkFrame(self.border, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        # Upload icon
        self.icon_label = ctk.CTkLabel(
            inner,
            text="☁↑",
            font=(FONT_FAMILY, 28),
            text_color=COLORS["text_secondary"],
        )
        self.icon_label.pack(pady=(0, 6))

        # Main text
        self.main_label = ctk.CTkLabel(
            inner,
            text=text,
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_primary"],
        )
        self.main_label.pack()

        # Sub text
        self.sub_label = ctk.CTkLabel(
            inner,
            text=subtext,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.sub_label.pack(pady=(2, 0))

        # Click handler on all children
        for w in [self.border, inner, self.icon_label, self.main_label, self.sub_label]:
            w.configure(cursor="hand2")
            w.bind("<Button-1>", self._on_click)

        # Hover effect
        self.border.bind("<Enter>", self._on_hover_in)
        self.border.bind("<Leave>", self._on_hover_out)

        # NOTE: Native drag-and-drop is handled centrally by App._on_global_drop
        # so that drops route to whichever page is currently visible.

    def _on_click(self, event=None):
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(
            title="Select Files",
            filetypes=self.filetypes or [("All supported", "*.*")],
        )
        if paths:
            self._deliver(list(paths))

    def _on_drop_native(self, file_list):
        """windnd callback — receives list of bytes paths."""
        paths = []
        for f in file_list:
            if isinstance(f, bytes):
                path = f.decode("utf-8", errors="replace")
            else:
                path = str(f)
            if os.path.isfile(path):
                paths.append(path)
            elif os.path.isdir(path):
                # Recursively find files in dropped folders
                for root, dirs, files in os.walk(path):
                    for fname in files:
                        paths.append(os.path.join(root, fname))
        if paths:
            self._deliver(paths)

    def _deliver(self, paths):
        if self.on_files_dropped:
            self.on_files_dropped(paths)

    def _on_hover_in(self, event=None):
        self.border.configure(border_color=COLORS["accent"], fg_color=COLORS["bg_hover"])
        self.icon_label.configure(text_color=COLORS["accent"])

    def _on_hover_out(self, event=None):
        self.border.configure(border_color=COLORS["border"], fg_color=COLORS["bg_card"])
        self.icon_label.configure(text_color=COLORS["text_secondary"])

    def set_active(self, active=True):
        """Visual feedback for drag-over state."""
        if active:
            self.border.configure(border_color=COLORS["accent_green"], fg_color="#0e1a0e")
            self.main_label.configure(text="Drop files here!")
        else:
            self.border.configure(border_color=COLORS["border"], fg_color=COLORS["bg_card"])
            self.main_label.configure(text="Click to upload or drag and drop")


# ─── Compact File List ────────────────────────────────────────────

class CompactFileList(ctk.CTkFrame):
    """
    Compact file list with eye (preview) and pin (star) icons.
    Like the screenshot — small rows, efficient, scannable.
    """

    def __init__(self, parent, on_preview=None, on_pin=None, on_remove=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=10, **kwargs)

        self.on_preview = on_preview
        self.on_pin = on_pin
        self.on_remove = on_remove
        self.files = []         # list of dicts: {path, name, pinned, size}
        self.pinned = set()
        self.row_widgets = []

        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent", height=32)
        header.pack(fill="x", padx=10, pady=(8, 2))

        self.select_all_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            header, text="", variable=self.select_all_var,
            width=20, height=20,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
            command=self._toggle_select_all,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            header, text="Name",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_muted"],
        ).pack(side="left")

        # Scrollable body
        self.list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=200,
        )
        self.list_frame.pack(fill="both", expand=True, padx=2, pady=(0, 4))

        # Counter label
        self.count_label = ctk.CTkLabel(
            self, text="0 files",
            font=(FONT_FAMILY, FONT_SIZES["tiny"]),
            text_color=COLORS["text_muted"],
        )
        self.count_label.pack(anchor="w", padx=12, pady=(0, 6))

    def set_files(self, file_paths):
        """Set the file list from a list of paths."""
        self.files = []
        for fp in file_paths:
            name = os.path.basename(fp)
            try:
                size = os.path.getsize(fp)
            except Exception:
                size = 0
            self.files.append({
                "path": fp, "name": name, "size": size,
                "pinned": False, "selected": True,
            })
        self.pinned = set()
        self._rebuild()

    def get_selected_files(self):
        """Return paths of selected (checked) files."""
        return [f["path"] for f in self.files if f.get("selected", True)]

    def get_pinned_files(self):
        """Return paths of pinned files."""
        return [f["path"] for f in self.files if f.get("pinned", False)]

    def _rebuild(self):
        """Redraw the entire list."""
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.row_widgets = []

        # Sort: pinned first, then alphabetical
        sorted_files = sorted(self.files, key=lambda f: (not f["pinned"], f["name"].lower()))

        for idx, finfo in enumerate(sorted_files):
            self._create_row(finfo, idx)

        self.count_label.configure(text=f"{len(self.files)} files")

    def _create_row(self, finfo, idx):
        """Create a single compact file row."""
        row_color = COLORS["bg_card"] if idx % 2 == 0 else COLORS["bg_dark"]
        row = ctk.CTkFrame(self.list_frame, fg_color=row_color, height=34, corner_radius=4)
        row.pack(fill="x", pady=1, padx=4)
        row.pack_propagate(False)

        # Checkbox
        cb_var = ctk.BooleanVar(value=finfo.get("selected", True))
        cb = ctk.CTkCheckBox(
            row, text="", variable=cb_var, width=18, height=18,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
            command=lambda f=finfo, v=cb_var: self._toggle_file(f, v),
        )
        cb.pack(side="left", padx=(8, 6))

        # File icon
        ext = os.path.splitext(finfo["name"])[1].lower()
        icon = self._get_file_icon(ext)
        ctk.CTkLabel(
            row, text=icon,
            font=(FONT_FAMILY, 12),
            text_color=COLORS["text_muted"],
            width=20,
        ).pack(side="left", padx=(0, 4))

        # File name (truncated)
        display_name = finfo["name"]
        if len(display_name) > 55:
            display_name = display_name[:25] + "..." + display_name[-25:]

        name_label = ctk.CTkLabel(
            row, text=display_name,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        name_label.pack(side="left", fill="x", expand=True, padx=(0, 4))
        Tooltip(name_label, finfo["path"])

        # Eye icon (preview)
        eye_btn = ctk.CTkLabel(
            row, text="👁", cursor="hand2",
            font=(FONT_FAMILY, 13),
            text_color=COLORS["text_muted"],
            width=24,
        )
        eye_btn.pack(side="right", padx=(0, 4))
        eye_btn.bind("<Button-1>", lambda e, f=finfo: self._preview_file(f))
        eye_btn.bind("<Enter>", lambda e, w=eye_btn: w.configure(text_color=COLORS["accent_blue"]))
        eye_btn.bind("<Leave>", lambda e, w=eye_btn: w.configure(text_color=COLORS["text_muted"]))

        # Pin/star icon
        pin_text = "★" if finfo.get("pinned") else "☆"
        pin_color = COLORS["accent_yellow"] if finfo.get("pinned") else COLORS["text_muted"]
        pin_btn = ctk.CTkLabel(
            row, text=pin_text, cursor="hand2",
            font=(FONT_FAMILY, 14),
            text_color=pin_color,
            width=24,
        )
        pin_btn.pack(side="right", padx=(0, 2))
        pin_btn.bind("<Button-1>", lambda e, f=finfo: self._toggle_pin(f))
        pin_btn.bind("<Enter>", lambda e, w=pin_btn: w.configure(text_color=COLORS["accent_yellow"]))
        pin_btn.bind("<Leave>", lambda e, w=pin_btn, f=finfo:
                     w.configure(text_color=COLORS["accent_yellow"] if f.get("pinned") else COLORS["text_muted"]))

        self.row_widgets.append(row)

    def _toggle_file(self, finfo, var):
        finfo["selected"] = var.get()

    def _toggle_pin(self, finfo):
        finfo["pinned"] = not finfo.get("pinned", False)
        if self.on_pin:
            self.on_pin(finfo)
        self._rebuild()

    def _preview_file(self, finfo):
        if self.on_preview:
            self.on_preview(finfo["path"])

    def _toggle_select_all(self):
        val = self.select_all_var.get()
        for f in self.files:
            f["selected"] = val
        self._rebuild()

    def _get_file_icon(self, ext):
        """Return emoji icon based on file extension."""
        icons = {
            ".pdf": "📕", ".txt": "📄", ".md": "📝", ".html": "🌐", ".htm": "🌐",
            ".json": "📋", ".csv": "📊", ".py": "🐍", ".js": "📜", ".ts": "📜",
            ".cpp": "⚙", ".c": "⚙", ".h": "⚙", ".cs": "💠", ".java": "☕",
            ".lua": "🌙", ".log": "📃", ".ksh": "🖥", ".xml": "📰",
            ".yaml": "📐", ".yml": "📐", ".rst": "📄", ".gitignore": "🔒",
        }
        return icons.get(ext, "📄")
