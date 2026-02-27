"""
Global Hotkey Module - Register system-wide keyboard shortcuts.
Uses the `keyboard` library for low-level hotkey capture.
"""
import threading

_registered_hotkeys = []
_app_ref = None
_keyboard_available = False

try:
    import keyboard
    _keyboard_available = True
except ImportError:
    _keyboard_available = False


def _toggle_visibility():
    """Toggle main window show/hide."""
    if not _app_ref:
        return
    _app_ref.after(0, _do_toggle)


def _do_toggle():
    """Must run on main thread."""
    if _app_ref.state() == "withdrawn" or not _app_ref.winfo_viewable():
        _app_ref.deiconify()
        _app_ref.lift()
        _app_ref.focus_force()
        _app_ref.state("normal")
    else:
        from core.settings import get_setting
        if get_setting("minimize_to_tray"):
            _app_ref.withdraw()
        else:
            _app_ref.iconify()


def _quick_ocr():
    """Quick OCR capture via hotkey."""
    if not _app_ref:
        return
    _app_ref.after(0, _do_quick_ocr)


def _do_quick_ocr():
    _app_ref.deiconify()
    _app_ref.lift()
    _app_ref.focus_force()
    _app_ref.show_page("ocr")
    page = _app_ref.pages.get("ocr")
    if page and hasattr(page, "_ocr_clipboard"):
        _app_ref.after(300, page._ocr_clipboard)


def _quick_paste():
    """Quick paste capture via hotkey."""
    if not _app_ref:
        return
    _app_ref.after(0, _do_quick_paste)


def _do_quick_paste():
    _app_ref.deiconify()
    _app_ref.lift()
    _app_ref.focus_force()
    _app_ref.show_page("paste")
    page = _app_ref.pages.get("paste")
    if page and hasattr(page, "_paste_clipboard"):
        _app_ref.after(300, page._paste_clipboard)


def register_hotkeys(app, settings: dict):
    """Register all hotkeys from settings dict."""
    global _app_ref, _registered_hotkeys

    if not _keyboard_available:
        return

    _app_ref = app
    unregister_all()

    hotkey_map = {
        "hotkey_show_hide": _toggle_visibility,
        "hotkey_quick_ocr": _quick_ocr,
        "hotkey_quick_paste": _quick_paste,
    }

    for key, callback in hotkey_map.items():
        combo = settings.get(key, "").strip()
        if combo:
            try:
                keyboard.add_hotkey(combo, callback, suppress=False)
                _registered_hotkeys.append(combo)
            except Exception as e:
                print(f"[Hotkey] Failed to register '{combo}': {e}")


def unregister_all():
    """Remove all registered hotkeys."""
    global _registered_hotkeys
    if not _keyboard_available:
        return
    for combo in _registered_hotkeys:
        try:
            keyboard.remove_hotkey(combo)
        except Exception:
            pass
    _registered_hotkeys = []


def is_available() -> bool:
    """Check if hotkey module is usable."""
    return _keyboard_available
