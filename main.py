"""
LoRA Data Toolkit - Main Entry Point
A simple tool to collect, organize, and export training data for LoRA fine-tuning.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.logger import log          # noqa: E402  — must come after path fix
from gui.app import App


def _handle_exception(exc_type, exc_value, exc_tb):
    """Catch any uncaught exception and write it to toolkit.log."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    log.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))


def main():
    sys.excepthook = _handle_exception
    log.info("=== LoRA Data Toolkit starting ===")
    try:
        app = App()
        app.mainloop()
    except Exception:
        log.critical("Fatal error during startup", exc_info=True)
        raise
    finally:
        log.info("=== LoRA Data Toolkit stopped ===")


if __name__ == "__main__":
    main()
