"""
Web Scraper - Extract clean text content from URLs.
Uses trafilatura for high-quality extraction, BeautifulSoup as fallback.
GitHub URLs are automatically routed to the specialized GitHub scraper.
"""
import requests
from config import REQUEST_TIMEOUT, USER_AGENT

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

from bs4 import BeautifulSoup
from core.github_scraper import is_github_url, scrape_github


def scrape_url(url):
    """
    Scrape a URL and return clean text content.
    Auto-detects GitHub URLs and routes to the specialized scraper.
    Returns dict: {title, content, url, success, error}
    """
    result = {"title": "", "content": "", "url": url, "success": False, "error": ""}

    # ── GitHub special handling ─────────────────────────────
    if is_github_url(url):
        return scrape_github(url)

    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        html = response.text

        # Try trafilatura first (best quality extraction)
        if HAS_TRAFILATURA:
            content = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_precision=False,
                favor_recall=True,
            )
            if content and len(content.strip()) > 100:
                # Get title from HTML
                soup = BeautifulSoup(html, "html.parser")
                title = soup.title.string if soup.title else url
                result["title"] = title.strip() if title else url
                result["content"] = content.strip()
                result["success"] = True
                return result

        # Fallback: BeautifulSoup extraction
        soup = BeautifulSoup(html, "html.parser")

        # Get title
        title = soup.title.string if soup.title else url
        result["title"] = title.strip() if title else url

        # Remove script, style, nav, footer elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        # Try to find main content area
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(class_=["content", "post-content", "article-body", "entry-content"])
            or soup.find("div", {"role": "main"})
            or soup.body
        )

        if main:
            # Get text, clean up whitespace
            text = main.get_text(separator="\n", strip=True)
            # Clean up excessive blank lines
            lines = [line.strip() for line in text.splitlines()]
            text = "\n".join(line for line in lines if line)
            result["content"] = text
            result["success"] = True
        else:
            result["error"] = "Could not find main content on page"

    except requests.exceptions.Timeout:
        result["error"] = "Request timed out"
    except requests.exceptions.ConnectionError:
        result["error"] = "Could not connect to URL"
    except requests.exceptions.HTTPError as e:
        result["error"] = f"HTTP error: {e.response.status_code}"
    except Exception as e:
        result["error"] = f"Error: {str(e)}"

    return result


def scrape_multiple_urls(urls):
    """Scrape multiple URLs. Returns list of results."""
    results = []
    for url in urls:
        url = url.strip()
        if url:
            results.append(scrape_url(url))
    return results


def extract_links(url, filter_domain=True):
    """Extract all links from a page (useful for crawling documentation)."""
    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(response.text, "html.parser")

        from urllib.parse import urljoin, urlparse
        base_domain = urlparse(url).netloc

        links = []
        for a_tag in soup.find_all("a", href=True):
            href = urljoin(url, a_tag["href"])
            # Filter to same domain if requested
            if filter_domain and urlparse(href).netloc != base_domain:
                continue
            # Skip anchors, javascript, mailto
            if href.startswith(("javascript:", "mailto:", "#")):
                continue
            link_text = a_tag.get_text(strip=True)
            links.append({"url": href, "text": link_text})

        # Remove duplicates
        seen = set()
        unique_links = []
        for link in links:
            if link["url"] not in seen:
                seen.add(link["url"])
                unique_links.append(link)

        return unique_links
    except Exception:
        return []
