"""
OCR Engine - Extract text from screenshots and images.
Uses pytesseract (requires Tesseract OCR installed on system).
Also supports reading images from clipboard on Windows.
"""
import os
import shutil
from PIL import Image, ImageGrab

try:
    import pytesseract
    HAS_TESSERACT = True
    _TESSERACT_FOUND = False

    # 1) Check system PATH first (works if user installed + added to PATH)
    _tess_on_path = shutil.which("tesseract")
    if _tess_on_path:
        pytesseract.pytesseract.tesseract_cmd = _tess_on_path
        _TESSERACT_FOUND = True
    else:
        # 2) Try common Windows install locations
        common_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe"),
            os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
            os.path.expanduser(r"~\scoop\apps\tesseract\current\tesseract.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                _TESSERACT_FOUND = True
                break
except ImportError:
    HAS_TESSERACT = False
    _TESSERACT_FOUND = False

_TESS_NOT_INSTALLED = (
    "Tesseract OCR engine is not installed on this system.\n\n"
    "Download and install it from:\n"
    "  https://github.com/UB-Mannheim/tesseract/wiki\n\n"
    "During install, check 'Add to PATH' or install to:\n"
    "  C:\\Program Files\\Tesseract-OCR\\\n\n"
    "After installing, restart the app."
)
_PKG_NOT_INSTALLED = (
    "pytesseract Python package not installed.\n"
    "Go to the Setup tab and run Step 2 (pip packages),\n"
    "or run: pip install pytesseract"
)


def ocr_from_file(image_path):
    """
    Extract text from an image file.
    Returns dict: {content, success, error}
    """
    result = {"content": "", "success": False, "error": ""}

    if not HAS_TESSERACT:
        result["error"] = _PKG_NOT_INSTALLED
        return result

    if not _TESSERACT_FOUND:
        result["error"] = _TESS_NOT_INSTALLED
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
        result["error"] = _PKG_NOT_INSTALLED
        return result

    if not _TESSERACT_FOUND:
        result["error"] = _TESS_NOT_INSTALLED
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
        result["error"] = _PKG_NOT_INSTALLED
        return result

    if not _TESSERACT_FOUND:
        result["error"] = _TESS_NOT_INSTALLED
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
