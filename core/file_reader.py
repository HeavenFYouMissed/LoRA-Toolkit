"""
File Reader - Extract text from various file formats.
Supports: PDF, TXT, MD, HTML, JSON, CSV
"""
import os


def read_file(file_path):
    """
    Read and extract text from a file.
    Returns dict: {title, content, success, error}
    """
    result = {"title": "", "content": "", "success": False, "error": ""}

    if not os.path.exists(file_path):
        result["error"] = f"File not found: {file_path}"
        return result

    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()
    result["title"] = filename

    try:
        if ext == ".pdf":
            return _read_pdf(file_path, result)
        elif ext in (".txt", ".md", ".markdown", ".rst", ".log"):
            return _read_text(file_path, result)
        elif ext in (".html", ".htm"):
            return _read_html(file_path, result)
        elif ext == ".json":
            return _read_json(file_path, result)
        elif ext == ".csv":
            return _read_csv(file_path, result)
        elif ext in (".py", ".js", ".ts", ".cpp", ".c", ".h", ".cs", ".java", ".lua"):
            return _read_text(file_path, result)  # Code files as text
        else:
            # Try as text
            return _read_text(file_path, result)
    except Exception as e:
        result["error"] = f"Error reading file: {str(e)}"
        return result


def _read_pdf(file_path, result):
    """Extract text from PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        result["error"] = "PyMuPDF not installed. Run: pip install PyMuPDF"
        return result

    try:
        doc = fitz.open(file_path)
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                pages.append(f"--- Page {page_num + 1} ---\n{text.strip()}")

        doc.close()

        if pages:
            result["content"] = "\n\n".join(pages)
            result["title"] = f"{result['title']} ({len(pages)} pages)"
            result["success"] = True
        else:
            result["error"] = "No text found in PDF (might be image-based - try OCR)"
    except Exception as e:
        result["error"] = f"PDF error: {str(e)}"

    return result


def _read_text(file_path, result):
    """Read plain text file."""
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            if content.strip():
                result["content"] = content.strip()
                result["success"] = True
            else:
                result["error"] = "File is empty"
            return result
        except (UnicodeDecodeError, UnicodeError):
            continue

    result["error"] = "Could not decode file with any known encoding"
    return result


def _read_html(file_path, result):
    """Extract text from local HTML file."""
    from bs4 import BeautifulSoup

    with open(file_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts and styles
    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    content = "\n".join(lines)

    if content:
        result["content"] = content
        result["success"] = True
        # Use HTML title if available
        if soup.title:
            result["title"] = soup.title.string.strip()
    else:
        result["error"] = "No text content found in HTML"

    return result


def _read_json(file_path, result):
    """Read JSON file as formatted text."""
    import json

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    content = json.dumps(data, indent=2, ensure_ascii=False)
    result["content"] = content
    result["success"] = True
    return result


def _read_csv(file_path, result):
    """Read CSV file as text."""
    import csv

    rows = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(" | ".join(row))

    if rows:
        result["content"] = "\n".join(rows)
        result["success"] = True
    else:
        result["error"] = "CSV file is empty"

    return result


def get_supported_extensions():
    """Get list of file extensions we can handle."""
    return [
        ("All Supported", "*.pdf *.txt *.md *.html *.htm *.json *.csv *.py *.js *.ts *.cpp *.c *.h *.cs *.java *.lua *.log *.rst"),
        ("PDF Files", "*.pdf"),
        ("Text Files", "*.txt *.md *.rst *.log"),
        ("HTML Files", "*.html *.htm"),
        ("Data Files", "*.json *.csv"),
        ("Code Files", "*.py *.js *.ts *.cpp *.c *.h *.cs *.java *.lua"),
        ("All Files", "*.*"),
    ]
