"""
OCR Engine - Extract text from screenshots and images.
Uses pytesseract (requires Tesseract OCR installed on system).
Also supports reading images from clipboard on Windows.
"""
import os
from PIL import Image, ImageGrab

try:
    import pytesseract
    HAS_TESSERACT = True

    # Try common Windows Tesseract paths
    common_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe"),
    ]
    for path in common_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break
except ImportError:
    HAS_TESSERACT = False


def ocr_from_file(image_path):
    """
    Extract text from an image file.
    Returns dict: {content, success, error}
    """
    result = {"content": "", "success": False, "error": ""}

    if not HAS_TESSERACT:
        result["error"] = (
            "pytesseract not installed. Run: pip install pytesseract\n"
            "Also install Tesseract OCR: https://github.com/tesseract-ocr/tesseract/releases"
        )
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
        result["error"] = (
            "pytesseract not installed. Run: pip install pytesseract\n"
            "Also install Tesseract OCR: https://github.com/tesseract-ocr/tesseract/releases"
        )
        return result

    try:
        image = ImageGrab.grabfromclipboard()
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
        result["error"] = "pytesseract not installed"
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
