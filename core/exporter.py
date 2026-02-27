"""
Exporter - Convert collected data into LoRA-ready training files.
Supports multiple formats: Alpaca, ShareGPT, Completion, Raw Chunks.
"""
import json
import os
from datetime import datetime
from config import EXPORTS_DIR, DEFAULT_CHUNK_SIZE, DEFAULT_SYSTEM_PROMPT


def chunk_text(text, max_words=DEFAULT_CHUNK_SIZE, overlap=50):
    """Split text into chunks of max_words with overlap."""
    words = text.split()
    if len(words) <= max_words:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = start + max_words
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap  # Overlap for context continuity
        if start < 0:
            start = 0

    return chunks


def export_alpaca(entries, output_path=None, system_prompt=DEFAULT_SYSTEM_PROMPT,
                  instruction_template="default", chunk_size=DEFAULT_CHUNK_SIZE):
    """
    Export as Alpaca format JSONL.
    Each entry becomes one or more instruction/input/output pairs.
    Format: {"instruction": "...", "input": "...", "output": "..."}
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(EXPORTS_DIR, f"alpaca_{timestamp}.jsonl")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    templates = {
        "default": {
            "instruction": "Provide detailed information about the following topic based on your training data.",
            "input_prefix": "Topic: "
        },
        "qa": {
            "instruction": "Answer the following question accurately and thoroughly.",
            "input_prefix": "Question: What do you know about "
        },
        "explain": {
            "instruction": "Explain the following concept or information in detail.",
            "input_prefix": ""
        },
        "summarize": {
            "instruction": "Provide a comprehensive summary of the following information.",
            "input_prefix": ""
        },
    }

    template = templates.get(instruction_template, templates["default"])
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            title = entry.get("title", "")
            content = entry.get("content", "")
            tags = entry.get("tags", "")

            if not content.strip():
                continue

            # Chunk long content
            chunks = chunk_text(content, max_words=chunk_size)

            for i, chunk in enumerate(chunks):
                record = {
                    "instruction": template["instruction"],
                    "input": f"{template['input_prefix']}{title}",
                    "output": chunk,
                }
                if system_prompt:
                    record["system"] = system_prompt

                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    return output_path, count


def export_sharegpt(entries, output_path=None, system_prompt=DEFAULT_SYSTEM_PROMPT,
                    chunk_size=DEFAULT_CHUNK_SIZE):
    """
    Export as ShareGPT format JSONL.
    Format: {"conversations": [{"from": "system", ...}, {"from": "human", ...}, {"from": "gpt", ...}]}
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(EXPORTS_DIR, f"sharegpt_{timestamp}.jsonl")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            title = entry.get("title", "")
            content = entry.get("content", "")

            if not content.strip():
                continue

            chunks = chunk_text(content, max_words=chunk_size)

            for chunk in chunks:
                conversations = []

                if system_prompt:
                    conversations.append({"from": "system", "value": system_prompt})

                conversations.append({
                    "from": "human",
                    "value": f"Tell me everything you know about: {title}"
                })
                conversations.append({
                    "from": "gpt",
                    "value": chunk
                })

                record = {"conversations": conversations}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    return output_path, count


def export_completion(entries, output_path=None, chunk_size=DEFAULT_CHUNK_SIZE):
    """
    Export as completion format JSONL (for continued pretraining).
    Format: {"text": "content..."}
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(EXPORTS_DIR, f"completion_{timestamp}.jsonl")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            content = entry.get("content", "")
            title = entry.get("title", "")

            if not content.strip():
                continue

            chunks = chunk_text(content, max_words=chunk_size)

            for chunk in chunks:
                # Prepend title as context
                text = f"# {title}\n\n{chunk}" if title else chunk
                record = {"text": text}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    return output_path, count


def export_chatml(entries, output_path=None, system_prompt=DEFAULT_SYSTEM_PROMPT,
                  chunk_size=DEFAULT_CHUNK_SIZE):
    """
    Export as ChatML format JSONL.
    Format: {"text": "<|im_start|>system\\n...\\n<|im_end|>\\n<|im_start|>user\\n..."}
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(EXPORTS_DIR, f"chatml_{timestamp}.jsonl")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            title = entry.get("title", "")
            content = entry.get("content", "")

            if not content.strip():
                continue

            chunks = chunk_text(content, max_words=chunk_size)

            for chunk in chunks:
                parts = []
                if system_prompt:
                    parts.append(f"<|im_start|>system\n{system_prompt}<|im_end|>")
                parts.append(f"<|im_start|>user\nProvide detailed information about: {title}<|im_end|>")
                parts.append(f"<|im_start|>assistant\n{chunk}<|im_end|>")

                text = "\n".join(parts)
                record = {"text": text}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    return output_path, count


def export_raw_json(entries, output_path=None):
    """
    Export as a raw JSON array (all entry data as-is).
    Useful for backup or custom processing.
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(EXPORTS_DIR, f"raw_{timestamp}.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Clean entries for export
    clean = []
    for entry in entries:
        clean.append({
            "title": entry.get("title", ""),
            "content": entry.get("content", ""),
            "source_type": entry.get("source_type", ""),
            "source_url": entry.get("source_url", ""),
            "tags": entry.get("tags", ""),
            "category": entry.get("category", ""),
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)

    return output_path, len(clean)


# Convenience map for GUI
EXPORT_FORMATS = {
    "Alpaca (Instruction/Input/Output)": export_alpaca,
    "ShareGPT (Conversations)": export_sharegpt,
    "Completion (Raw Text)": export_completion,
    "ChatML": export_chatml,
    "Raw JSON (Backup)": export_raw_json,
}
