"""
Data Quality Scorer - Rate entries for training data quality.
Flags junk, scores readability, checks content richness.
"""
import re
import math


def score_entry(content, title=""):
    """
    Score a text entry for LoRA training quality.
    Returns dict with scores and flags:
        - overall: 0-100 quality score
        - word_count: total words
        - grade: "excellent", "good", "okay", "poor", "junk"
        - issues: list of problem descriptions
        - details: individual score breakdown
    """
    if not content or not content.strip():
        return {
            "overall": 0,
            "word_count": 0,
            "grade": "junk",
            "emoji": "🗑️",
            "issues": ["Empty content"],
            "details": {},
        }

    words = content.split()
    word_count = len(words)
    sentences = _split_sentences(content)
    sentence_count = max(len(sentences), 1)

    issues = []
    scores = {}

    # ─── 1. Length Score (0-25) ────────────────────────────
    if word_count < 20:
        scores["length"] = 0
        issues.append("Very short (<20 words)")
    elif word_count < 50:
        scores["length"] = 8
        issues.append("Short content (<50 words)")
    elif word_count < 100:
        scores["length"] = 15
    elif word_count < 2000:
        scores["length"] = 25  # Sweet spot
    else:
        scores["length"] = 20  # Very long, might be noisy
        issues.append("Very long (>2000 words) — may need chunking")

    # ─── 2. Readability Score (0-25) ───────────────────────
    avg_sentence_len = word_count / sentence_count
    if avg_sentence_len < 5:
        scores["readability"] = 8
        issues.append("Very short sentences (fragments?)")
    elif avg_sentence_len < 10:
        scores["readability"] = 18
    elif avg_sentence_len < 25:
        scores["readability"] = 25  # Good range
    elif avg_sentence_len < 40:
        scores["readability"] = 15
        issues.append("Sentences are very long (hard to learn from)")
    else:
        scores["readability"] = 5
        issues.append("Extremely long sentences (wall of text)")

    # ─── 3. Vocabulary Diversity (0-25) ────────────────────
    unique_words = set(w.lower() for w in words if len(w) > 2)
    if word_count > 0:
        diversity = len(unique_words) / word_count
    else:
        diversity = 0

    if diversity < 0.15:
        scores["diversity"] = 5
        issues.append("Very repetitive vocabulary")
    elif diversity < 0.30:
        scores["diversity"] = 15
    elif diversity < 0.60:
        scores["diversity"] = 25  # Good diversity
    else:
        scores["diversity"] = 20  # Could be too scattered

    # ─── 4. Content Quality Checks (0-25) ─────────────────
    quality = 25

    # Check for boilerplate / junk patterns
    boilerplate_phrases = [
        "cookie", "privacy policy", "terms of service", "subscribe",
        "click here", "sign up", "log in", "copyright ©",
        "all rights reserved", "newsletter", "advertisement",
    ]
    lower_content = content.lower()
    boilerplate_hits = sum(1 for p in boilerplate_phrases if p in lower_content)
    if boilerplate_hits >= 4:
        quality -= 15
        issues.append(f"Looks like boilerplate/navigation ({boilerplate_hits} patterns)")
    elif boilerplate_hits >= 2:
        quality -= 5

    # Check for excessive URLs/links
    url_count = len(re.findall(r'https?://\S+', content))
    url_ratio = url_count / max(sentence_count, 1)
    if url_ratio > 0.5:
        quality -= 10
        issues.append("Too many URLs (link dump?)")

    # Check for excessive special characters / code noise
    alpha_chars = sum(1 for c in content if c.isalpha())
    total_chars = max(len(content), 1)
    alpha_ratio = alpha_chars / total_chars
    if alpha_ratio < 0.4:
        quality -= 10
        issues.append("Low alphabetic content (code/symbols heavy)")

    # Check for mostly numbers
    digit_chars = sum(1 for c in content if c.isdigit())
    if digit_chars / total_chars > 0.3:
        quality -= 8
        issues.append("High number density (data table?)")

    scores["quality"] = max(quality, 0)

    # ─── Calculate Overall ─────────────────────────────────
    overall = sum(scores.values())
    overall = max(0, min(100, overall))

    # Grade
    if overall >= 80:
        grade, emoji = "excellent", "🟢"
    elif overall >= 60:
        grade, emoji = "good", "🔵"
    elif overall >= 40:
        grade, emoji = "okay", "🟡"
    elif overall >= 20:
        grade, emoji = "poor", "🟠"
    else:
        grade, emoji = "junk", "🔴"

    return {
        "overall": overall,
        "word_count": word_count,
        "grade": grade,
        "emoji": emoji,
        "issues": issues,
        "details": scores,
    }


def score_entry_quick(content):
    """Quick score — returns just (overall_score, emoji, grade)."""
    result = score_entry(content)
    return result["overall"], result["emoji"], result["grade"]


def _split_sentences(text):
    """Simple sentence splitter."""
    # Split on sentence-ending punctuation followed by space/newline
    sentences = re.split(r'[.!?]+[\s\n]+', text)
    return [s.strip() for s in sentences if s.strip()]


def get_quality_summary(entries):
    """Score a batch of entries and return summary stats."""
    if not entries:
        return {"total": 0, "avg_score": 0, "by_grade": {}}

    grades = {"excellent": 0, "good": 0, "okay": 0, "poor": 0, "junk": 0}
    total_score = 0

    for entry in entries:
        result = score_entry(entry.get("content", ""))
        total_score += result["overall"]
        grades[result["grade"]] += 1

    return {
        "total": len(entries),
        "avg_score": round(total_score / len(entries)),
        "by_grade": grades,
    }
