"""
Site Crawler - Start at a URL, follow links N levels deep, scrape everything.
Respects same-domain filtering, rate limiting, and deduplication.
"""
import time
import re
from urllib.parse import urljoin, urlparse, urldefrag
import requests
from bs4 import BeautifulSoup
from config import REQUEST_TIMEOUT, USER_AGENT

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

from core.github_scraper import is_github_url


def _normalize_url(url):
    """Normalize a URL for dedup (strip fragment, trailing slash)."""
    url, _ = urldefrag(url)
    url = url.rstrip("/")
    return url


def _extract_page_links(html, base_url, same_domain=True):
    """Extract all valid links from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc

    links = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        # Skip non-http links
        if href.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
            continue

        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        full_url = _normalize_url(full_url)

        # Must be http(s)
        if not full_url.startswith(("http://", "https://")):
            continue

        # Same domain filter
        if same_domain and urlparse(full_url).netloc != base_domain:
            continue

        # Skip common non-content URLs
        skip_patterns = [
            r'/login', r'/signup', r'/register', r'/logout', r'/auth',
            r'/cart', r'/checkout', r'/account', r'/admin',
            r'\.(png|jpg|jpeg|gif|svg|ico|css|js|woff|woff2|ttf|eot|mp4|mp3|zip|tar|gz|pdf)$',
        ]
        if any(re.search(p, full_url, re.IGNORECASE) for p in skip_patterns):
            continue

        links.add(full_url)

    return links


def _scrape_single_page(url):
    """Scrape a single page and return its content + links found."""
    result = {
        "url": url, "title": "", "content": "", "links": set(),
        "success": False, "error": "", "word_count": 0,
    }

    # Don't crawl GitHub pages — they need the specialized scraper
    if is_github_url(url):
        from core.github_scraper import scrape_github
        gh = scrape_github(url)
        result["title"] = gh.get("title", "")
        result["content"] = gh.get("content", "")
        result["success"] = gh.get("success", False)
        result["error"] = gh.get("error", "")
        result["word_count"] = len(result["content"].split()) if result["content"] else 0
        return result

    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        html = resp.text

        # Extract links from the page
        result["links"] = _extract_page_links(html, url, same_domain=True)

        # Extract content (trafilatura → BS4 fallback)
        content = None
        if HAS_TRAFILATURA:
            content = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_recall=True,
            )

        if content and len(content.strip()) > 50:
            result["content"] = content.strip()
        else:
            # Fallback
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                tag.decompose()
            main = (
                soup.find("main") or soup.find("article")
                or soup.find(class_=["content", "post-content", "article-body"])
                or soup.find("div", {"role": "main"}) or soup.body
            )
            if main:
                text = main.get_text(separator="\n", strip=True)
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                result["content"] = "\n".join(lines)

        # Title
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            result["title"] = soup.title.string.strip()
        else:
            result["title"] = url

        result["word_count"] = len(result["content"].split()) if result["content"] else 0
        result["success"] = bool(result["content"] and result["word_count"] > 10)

    except requests.exceptions.Timeout:
        result["error"] = "Timeout"
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection failed"
    except requests.exceptions.HTTPError as e:
        result["error"] = f"HTTP {e.response.status_code}"
    except Exception as e:
        result["error"] = str(e)[:100]

    return result


def crawl_site(start_url, max_depth=2, max_pages=100, delay=0.5,
               same_domain=True, min_words=20,
               on_progress=None, should_cancel=None):
    """
    Crawl a website starting from start_url, following links up to max_depth.

    Args:
        start_url: Starting URL
        max_depth: How many levels deep to follow links (1=just the start page's links)
        max_pages: Maximum total pages to scrape
        delay: Seconds between requests (rate limiting)
        same_domain: Only follow same-domain links
        min_words: Skip pages with fewer words than this
        on_progress: Callback(current_count, total_discovered, current_url, result_dict)
        should_cancel: Callable that returns True to abort

    Returns:
        list of result dicts: [{url, title, content, word_count, depth, success, error}, ...]
    """
    start_url = _normalize_url(start_url)
    visited = set()
    results = []

    # Queue: list of (url, depth)
    queue = [(start_url, 0)]
    discovered = {start_url}

    while queue and len(results) < max_pages:
        if should_cancel and should_cancel():
            break

        url, depth = queue.pop(0)

        if url in visited:
            continue
        visited.add(url)

        # Report progress
        if on_progress:
            on_progress(len(results), len(discovered), url, None)

        # Scrape the page
        page = _scrape_single_page(url)
        page["depth"] = depth

        if delay > 0:
            time.sleep(delay)

        if page["success"] and page["word_count"] >= min_words:
            results.append(page)

            # Report with result
            if on_progress:
                on_progress(len(results), len(discovered), url, page)

            # Discover new links (only if we haven't hit max depth)
            if depth < max_depth:
                new_links = page.get("links", set()) - discovered
                for link in new_links:
                    if len(discovered) < max_pages * 3:  # Don't explode the queue
                        discovered.add(link)
                        queue.append((link, depth + 1))
        else:
            # Still report failed pages
            if on_progress:
                on_progress(len(results), len(discovered), url, page)

    return results
