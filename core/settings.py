"""
Settings Manager - Load/save user preferences to JSON.
"""
import os
import json
from config import APP_DIR, DATA_DIR

SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

# Default settings
DEFAULTS = {
    # General
    "minimize_to_tray": True,
    "start_minimized": False,
    "always_on_top": False,

    # Hotkeys  (empty string = disabled)
    "hotkey_show_hide": "ctrl+shift+l",
    "hotkey_quick_ocr": "",
    "hotkey_quick_paste": "",

    # Scraper
    "request_timeout": 30,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",

    # Export defaults
    "default_chunk_size": 512,
    "default_system_prompt": (
        "You are a knowledgeable assistant specializing in video game security, "
        "cheat detection, and game hacking analysis."
    ),
    "default_export_format": "Alpaca (Instruction/Input/Output)",
    "default_instruction_style": "default",

    # OCR
    "tesseract_path": "",  # empty = auto-detect

    # AI Cleaner (Ollama)
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen3-vl:4b-instruct",
    "ollama_num_ctx": 0,  # 0 = auto-calculate based on content

    # Groq Cloud API
    "groq_api_key": "",
    "groq_model": "llama-3.1-70b-versatile",

    # xAI Grok (Super Grok)
    "grok_api_key": "",
    "grok_model": "grok-3-mini",

    "ai_provider": "local",  # "local" = Ollama, "groq" = Groq Cloud, "grok" = xAI Grok

    # Appearance
    "accent_color": "#e94560",
    "window_opacity": 0.97,
}


def load_settings() -> dict:
    """Load settings from JSON, filling in defaults for missing keys."""
    settings = dict(DEFAULTS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings.update(saved)
        except Exception:
            pass  # Corrupt file, use defaults
    return settings


def save_settings(settings: dict):
    """Save settings dict to JSON."""
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def get_setting(key: str):
    """Get a single setting value."""
    settings = load_settings()
    return settings.get(key, DEFAULTS.get(key))


def set_setting(key: str, value):
    """Set a single setting value and save."""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)
