"""
System Tray Module - Minimize to tray with right-click menu.
Uses pystray + Pillow to create a tray icon.
"""
import threading
import os

_tray_icon = None
_app_ref = None


def _create_tray_image():
    """Create a simple tray icon image (brain emoji style)."""
    from PIL import Image, ImageDraw, ImageFont

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle
    draw.ellipse([4, 4, 60, 60], fill="#e94560")

    # "L" letter in the center (for LoRA)
    try:
        font = ImageFont.truetype("segoeui.ttf", 32)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), "L", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - 4), "L", fill="white", font=font)

    return img


def _on_show(icon, item):
    """Show the main window."""
    if _app_ref:
        _app_ref.after(0, _restore_window)


def _on_quick_ocr(icon, item):
    """Quick OCR from clipboard."""
    if _app_ref:
        _app_ref.after(0, lambda: _quick_capture("ocr"))


def _on_quick_paste(icon, item):
    """Quick paste from clipboard."""
    if _app_ref:
        _app_ref.after(0, lambda: _quick_capture("paste"))


def _on_quit(icon, item):
    """Quit the application."""
    if _app_ref:
        _app_ref.after(0, _do_quit)


def _restore_window():
    """Restore and focus the main window."""
    if _app_ref:
        _app_ref.deiconify()
        _app_ref.lift()
        _app_ref.focus_force()
        _app_ref.state("normal")


def _quick_capture(mode):
    """Show app, switch to page, trigger capture."""
    _restore_window()
    if mode == "ocr":
        _app_ref.show_page("ocr")
        page = _app_ref.pages.get("ocr")
        if page and hasattr(page, "_ocr_clipboard"):
            _app_ref.after(200, page._ocr_clipboard)
    elif mode == "paste":
        _app_ref.show_page("paste")
        page = _app_ref.pages.get("paste")
        if page and hasattr(page, "_paste_clipboard"):
            _app_ref.after(200, page._paste_clipboard)


def _do_quit():
    """Clean shutdown."""
    global _tray_icon
    if _tray_icon:
        _tray_icon.stop()
        _tray_icon = None
    if _app_ref:
        _app_ref.destroy()


def setup_tray(app):
    """Initialize the system tray icon."""
    global _tray_icon, _app_ref
    import pystray

    _app_ref = app
    image = _create_tray_image()

    menu = pystray.Menu(
        pystray.MenuItem("Show / Hide", _on_show, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quick OCR (Clipboard)", _on_quick_ocr),
        pystray.MenuItem("Quick Paste (Clipboard)", _on_quick_paste),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _on_quit),
    )

    _tray_icon = pystray.Icon(
        "lora_toolkit",
        image,
        "LoRA Data Toolkit",
        menu,
    )

    # Run tray in its own thread
    tray_thread = threading.Thread(target=_tray_icon.run, daemon=True)
    tray_thread.start()

    return _tray_icon


def hide_to_tray(app):
    """Hide main window to tray."""
    app.withdraw()


def destroy_tray():
    """Clean up tray icon."""
    global _tray_icon
    if _tray_icon:
        try:
            _tray_icon.stop()
        except Exception:
            pass
        _tray_icon = None
