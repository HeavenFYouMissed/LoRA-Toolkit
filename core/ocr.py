"""
OCR Engine - Extract text from screenshots and images.
Uses pytesseract (requires Tesseract OCR installed on system).
Auto-downloads Tesseract if not found.
Also supports reading images from clipboard on Windows.
"""
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from PIL import Image, ImageGrab

# App-local Tesseract install directory (no admin needed)
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESSERACT_LOCAL_DIR = os.path.join(_APP_DIR, "tesseract")

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


def _find_tesseract():
    """Search for tesseract.exe. Returns path or None."""
    if not HAS_TESSERACT:
        return None

    # 1) App-local install (our auto-download location)
    local_exe = os.path.join(TESSERACT_LOCAL_DIR, "tesseract.exe")
    if os.path.exists(local_exe):
        return local_exe

    # 2) System PATH
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    # 3) Common Windows install locations
    for path in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expanduser(r"~\scoop\apps\tesseract\current\tesseract.exe"),
    ]:
        if os.path.exists(path):
            return path

    return None


def _apply_tesseract_path(exe_path):
    """Set pytesseract to use the given exe."""
    global _TESSERACT_FOUND
    if exe_path and HAS_TESSERACT:
        pytesseract.pytesseract.tesseract_cmd = exe_path
        _TESSERACT_FOUND = True
        return True
    return False


# Initial detection at import time
_TESSERACT_FOUND = False
_apply_tesseract_path(_find_tesseract())


def install_tesseract(on_progress=None):
    """
    Download and silently install Tesseract OCR into the app directory.
    on_progress(message_str) is called with status updates.
    Returns (success: bool, message: str).
    """
    if not HAS_TESSERACT:
        return False, (
            "pytesseract Python package not installed.\n"
            "Go to the Setup tab and run Step 2 first."
        )

    # Already installed?
    existing = _find_tesseract()
    if existing:
        _apply_tesseract_path(existing)
        return True, f"Tesseract already available at {existing}"

    def _progress(msg):
        if on_progress:
            on_progress(msg)

    try:
        # ── Get latest release URL from GitHub API ──────────
        _progress("Finding latest Tesseract release...")
        api_url = "https://api.github.com/repos/UB-Mannheim/tesseract/releases/latest"
        req = urllib.request.Request(api_url, headers={"User-Agent": "LoRA-Data-Toolkit"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            release = json.loads(resp.read().decode())

        # Find the 64-bit Windows installer asset
        asset_url = None
        asset_name = None
        for asset in release.get("assets", []):
            name = asset["name"]
            if "w64" in name and name.endswith(".exe"):
                asset_url = asset["browser_download_url"]
                asset_name = name
                break

        if not asset_url:
            return False, "Could not find Tesseract Windows 64-bit installer in the latest release."

        # ── Download with progress ──────────────────────────
        tmp_path = os.path.join(tempfile.gettempdir(), asset_name)
        _progress(f"Downloading {asset_name}...")

        dl_req = urllib.request.Request(asset_url, headers={"User-Agent": "LoRA-Data-Toolkit"})
        with urllib.request.urlopen(dl_req, timeout=300) as dl_resp:
            total = int(dl_resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = dl_resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded / total * 100)
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total / (1024 * 1024)
                        _progress(f"Downloading Tesseract... {mb_done:.1f}/{mb_total:.1f} MB ({pct}%)")

        # ── Silent install ───────────────────────────────────
        _progress("Installing Tesseract (this may take a moment)...")

        # NSIS silent install: /S = silent
        # Try app-local first, fall back to default (Program Files)
        cmd = [tmp_path, "/S", f"/D={TESSERACT_LOCAL_DIR}"]
        subprocess.run(cmd, check=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)

        # ── Verify (check all known locations) ──────────────
        exe_path = _find_tesseract()
        if exe_path:
            _apply_tesseract_path(exe_path)
            # Clean up installer
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            _progress("Tesseract installed successfully!")
            return True, f"Tesseract installed to {os.path.dirname(exe_path)}"
        else:
            return False, (
                "Installer ran but tesseract.exe not found.\n"
                "Try downloading manually from:\n"
                "  https://github.com/UB-Mannheim/tesseract/wiki"
            )

    except urllib.error.URLError as e:
        return False, f"Download failed — check your internet connection.\n{e}"
    except subprocess.TimeoutExpired:
        return False, "Installer timed out. Try running it manually."
    except Exception as e:
        return False, f"Auto-install failed: {e}"


_PKG_MISSING = (
    "pytesseract Python package not installed.\n"
    "Go to the Setup tab and run Step 2 (pip packages)."
)
_ENGINE_MISSING = (
    "Tesseract OCR engine not found.\n"
    "It should auto-install when you use the OCR page."
)


def ocr_from_file(image_path):
    """
    Extract text from an image file.
    Returns dict: {content, success, error}
    """
    result = {"content": "", "success": False, "error": ""}

    if not HAS_TESSERACT:
        result["error"] = _PKG_MISSING
        return result

    if not _TESSERACT_FOUND:
        result["error"] = _ENGINE_MISSING
        return result

    try:
        if not os.path.exists(image_path):
            result["error"] = f"File not found: {image_path}"
            return result

        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)

        if text.strip():
            result["content"] = text.strip()
            result["success"] = True
        else:
            result["error"] = "No text detected in image"
    except Exception as e:
        result["error"] = f"OCR error: {str(e)}"

    return result


def ocr_from_clipboard():
    """
    Grab image from clipboard and extract text.
    Works with Windows screenshot tools (Snipping Tool, Win+Shift+S, etc.)
    Returns dict: {content, success, error}
    """
    result = {"content": "", "success": False, "error": ""}

    if not HAS_TESSERACT:
        result["error"] = _PKG_MISSING
        return result

    if not _TESSERACT_FOUND:
        result["error"] = _ENGINE_MISSING
        return result

    try:
        image = ImageGrab.grabclipboard()
        if image is None:
            result["error"] = "No image found in clipboard. Take a screenshot first (Win+Shift+S)"
            return result

        text = pytesseract.image_to_string(image)

        if text.strip():
            result["content"] = text.strip()
            result["success"] = True
        else:
            result["error"] = "No text detected in the clipboard image"
    except Exception as e:
        result["error"] = f"OCR error: {str(e)}"

    return result


def ocr_from_image(image):
    """
    Extract text from a PIL Image object.
    Returns dict: {content, success, error}
    """
    result = {"content": "", "success": False, "error": ""}

    if not HAS_TESSERACT:
        result["error"] = _PKG_MISSING
        return result

    if not _TESSERACT_FOUND:
        result["error"] = _ENGINE_MISSING
        return result

    try:
        text = pytesseract.image_to_string(image)
        if text.strip():
            result["content"] = text.strip()
            result["success"] = True
        else:
            result["error"] = "No text detected in image"
    except Exception as e:
        result["error"] = f"OCR error: {str(e)}"

    return result
