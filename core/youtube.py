"""
YouTube Transcript Extractor - Get transcripts + metadata from YouTube videos.
Grabs: title, description, chapters, channel name, transcript text.
"""
import re
import requests

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_YT_API = True
except ImportError:
    HAS_YT_API = False


def extract_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',  # Just the ID
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _fetch_video_metadata(video_id):
    """
    Scrape YouTube page for rich metadata: title, description, channel, chapters.
    Uses oEmbed API + page scraping (no API key needed).
    """
    meta = {
        "title": f"YouTube Video: {video_id}",
        "description": "",
        "channel": "",
        "chapters": [],
    }

    # oEmbed for title + channel (reliable, no JS needed)
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        resp = requests.get(oembed_url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            meta["title"] = data.get("title", meta["title"])
            meta["channel"] = data.get("author_name", "")
    except Exception:
        pass

    # Page scrape for description + chapters
    try:
        page_url = f"https://www.youtube.com/watch?v={video_id}"
        resp = requests.get(
            page_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                     "Accept-Language": "en-US,en;q=0.9"},
            timeout=15,
        )
        html = resp.text

        # Extract description from meta tag or JSON
        # Try og:description first
        og_desc = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', html)
        if og_desc:
            desc = og_desc.group(1)
            # HTML unescape
            desc = desc.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
            meta["description"] = desc

        # Try to get the full description from the inline JSON (ytInitialData)
        desc_match = re.search(
            r'"attributedDescription"\s*:\s*\{\s*"content"\s*:\s*"((?:[^"\\]|\\.)*)"',
            html
        )
        if desc_match:
            full_desc = desc_match.group(1)
            # Unescape JSON string
            full_desc = full_desc.encode().decode('unicode_escape', errors='replace')
            if len(full_desc) > len(meta["description"]):
                meta["description"] = full_desc

        # Extract chapters from description (timestamps like 0:00, 1:23:45)
        chapter_pattern = r'(?:^|\n)\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+[-–—]?\s*(.+?)(?:\n|$)'
        if meta["description"]:
            chapters = re.findall(chapter_pattern, meta["description"])
            meta["chapters"] = [{"time": t, "title": title.strip()} for t, title in chapters]

        # Fallback title from <title> tag
        if meta["title"] == f"YouTube Video: {video_id}":
            title_match = re.search(r'<title>(.+?)</title>', html)
            if title_match:
                title = title_match.group(1).replace(" - YouTube", "").strip()
                meta["title"] = title

    except Exception:
        pass

    return meta


def get_transcript(url_or_id, include_metadata=True):
    """
    Get transcript + rich metadata from a YouTube video.
    Returns dict: {title, content, video_id, url, description, channel, chapters, success, error}
    """
    result = {
        "title": "",
        "content": "",
        "video_id": "",
        "url": "",
        "description": "",
        "channel": "",
        "chapters": [],
        "success": False,
        "error": ""
    }

    if not HAS_YT_API:
        result["error"] = "youtube-transcript-api not installed. Run: pip install youtube-transcript-api"
        return result

    video_id = extract_video_id(url_or_id)
    if not video_id:
        result["error"] = "Could not extract video ID from URL"
        return result

    result["video_id"] = video_id
    result["url"] = f"https://www.youtube.com/watch?v={video_id}"

    try:
        # Fetch rich metadata (title, description, channel, chapters)
        if include_metadata:
            meta = _fetch_video_metadata(video_id)
            result["title"] = meta["title"]
            result["description"] = meta["description"]
            result["channel"] = meta["channel"]
            result["chapters"] = meta["chapters"]
        else:
            result["title"] = f"YouTube Video: {video_id}"

        # Get transcript
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)

        # Combine all text segments
        full_text = []
        for snippet in transcript.snippets:
            text = snippet.text.strip()
            if text:
                full_text.append(text)

        if full_text:
            # Build rich content: metadata header + transcript
            content_parts = []

            if result["channel"]:
                content_parts.append(f"Channel: {result['channel']}")
            content_parts.append(f"Title: {result['title']}")

            if result["description"]:
                content_parts.append(f"\n--- Description ---\n{result['description']}")

            if result["chapters"]:
                chapter_lines = [f"  {ch['time']} — {ch['title']}" for ch in result["chapters"]]
                content_parts.append(f"\n--- Chapters ---\n" + "\n".join(chapter_lines))

            content_parts.append(f"\n--- Transcript ---\n{' '.join(full_text)}")

            result["content"] = "\n".join(content_parts)
            result["success"] = True
        else:
            result["error"] = "Transcript is empty"

    except Exception as e:
        error_msg = str(e)
        if "TranscriptsDisabled" in error_msg:
            result["error"] = "Transcripts are disabled for this video"
        elif "NoTranscriptFound" in error_msg:
            result["error"] = "No transcript found for this video"
        elif "VideoUnavailable" in error_msg:
            result["error"] = "Video is unavailable"
        else:
            result["error"] = f"Error: {error_msg}"

    return result


def get_transcript_with_timestamps(url_or_id):
    """
    Get transcript with timestamps (useful for reference).
    Returns formatted text with [MM:SS] timestamps.
    """
    if not HAS_YT_API:
        return None, "youtube-transcript-api not installed"

    video_id = extract_video_id(url_or_id)
    if not video_id:
        return None, "Could not extract video ID"

    try:
        # Get metadata too
        meta = _fetch_video_metadata(video_id)

        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)

        parts = []
        if meta["channel"]:
            parts.append(f"Channel: {meta['channel']}")
        parts.append(f"Title: {meta['title']}")

        if meta["description"]:
            parts.append(f"\n--- Description ---\n{meta['description']}")

        if meta["chapters"]:
            chapter_lines = [f"  {ch['time']} — {ch['title']}" for ch in meta["chapters"]]
            parts.append(f"\n--- Chapters ---\n" + "\n".join(chapter_lines))

        parts.append("\n--- Transcript (timestamped) ---")

        for snippet in transcript.snippets:
            minutes = int(snippet.start // 60)
            seconds = int(snippet.start % 60)
            timestamp = f"[{minutes:02d}:{seconds:02d}]"
            parts.append(f"{timestamp} {snippet.text.strip()}")

        return "\n".join(parts), None
    except Exception as e:
        return None, str(e)
