# LoRA-Toolkit

**All-in-one local GUI for building high-quality LoRA models** — scrape data, organize it, clean/tag/preview, train with Unsloth (GPU or CPU fallback), merge models, and export ready-to-use LoRAs or Ollama Modelfiles.

No cloud, no complicated setup, no stitching 5 tools together.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![GPU](https://img.shields.io/badge/GPU-Optional-orange?logo=nvidia&logoColor=white)

![Demo Screenshot](screenshots/demo-main.png)
*(Add a 10-15 sec GIF here showing scrape -> preview -> train -> merge)*

---

## Why This Exists

Most LoRA tools are either:
- **Training-only** (Kohya_ss, OneTrainer) — no built-in data collection
- **Scraping-only** — no training or merging
- **Cloud/paywalled** — slow, expensive, censored

This is a **single local app** that does the full workflow: collect dirty web/YouTube/forum data -> clean/score/organize -> export formats -> train LoRA (fast Unsloth or CPU context injection) -> merge models -> deploy to Ollama.

Built for people who want quick, private, offline custom models (characters, art styles, anticheat research, game mods, etc.).

---

## Features

### 7 Data Sources in One GUI

| Source | Description |
|--------|------------|
| Web Scraper | Single page + trafilatura extraction |
| Bulk URL Scraper | Paste 100+ URLs, scrape them all at once |
| Site Crawler | BFS depth-controlled, rate-limited |
| YouTube Transcripts | Pull transcripts + metadata from any video |
| Paste Text | Manually paste text, notes, documentation |
| Screenshot OCR | Extract text from images (Tesseract) |
| File Import | Drag-and-drop PDF, TXT, MD, HTML, JSON, CSV, code |

### Smart Data Management
- SQLite database + quality auto-scoring (0-100)
- Duplicate detection & removal
- Edit, tag, category, search, delete
- Real-time content preview + word/char count

### Multiple Export Formats (ready for training)
Alpaca - ShareGPT - Completion - ChatML - Raw JSONL

### LoRA Training
- **Unsloth** (fast QLoRA on NVIDIA GPU)
- **CPU fallback** (context injection via long-context models)
- Auto-resolves Ollama names -> Hugging Face repos (prefers uncensored/abliterated variants)
- VRAM-aware model recommendations

### Model Merging ("Forge")
- Mergekit integration (SLERP, Linear, TIES, DARE-TIES, Passthrough)
- Auto YAML config
- Converts to GGUF + Ollama Modelfile

### Beautiful Dark GUI
- CustomTkinter + Mica titlebar (Windows 11)
- Sidebar navigation, reusable widgets, status bar
- System tray + hotkeys

### Step-by-Step Setup Page
- GPU auto-detection (nvidia-smi + WMI fallback)
- **3 numbered install buttons** — basic users only need Step 1
  - **Step 1:** Core app deps (scraping, OCR, GUI)
  - **Step 2:** PyTorch + CUDA 12.4 (GPU compute)
  - **Step 3:** Training stack (Unsloth, PEFT, TRL)
- Smart guards — Step 3 blocks until Step 2 is done, Step 2 warns without NVIDIA GPU

### Offline & Private
Everything runs locally. No telemetry, no cloud, no accounts.

---

## Quick Start (Windows)

### 1. Clone & run setup
```bash
git clone https://github.com/HeavenFYouMissed/LoRA-Toolkit.git
cd LoRA-Toolkit
setup.bat
```

### 2. Launch
```bash
python main.py
```

### 3. Use
```
Scrape/collect data -> Library -> Export -> Train -> Merge -> Done
```

### Manual install (if you prefer)
```bash
git clone https://github.com/HeavenFYouMissed/LoRA-Toolkit.git
cd LoRA-Toolkit
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### For LoRA Training (optional)
If you have an **NVIDIA GPU**, open the app and go to **Setup / GPU** page.
Click the 3 buttons in order:

1. **Install Core** — app basics
2. **Install PyTorch + CUDA** — GPU compute (~2.5 GB download)
3. **Install Training Stack** — Unsloth, PEFT, TRL (~2 GB download)

Or install manually:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install "unsloth[cu124-torch250] @ git+https://github.com/unslothai/unsloth.git"
pip install peft transformers trl datasets accelerate bitsandbytes sentencepiece protobuf
```

---

## Screenshots

*(Add 4-6 images here — main window, scraper page, library, training config, merge result, setup page)*

---

## Training Workflow

1. **Collect data** using any of the 7 sources
2. **Review** in the Data Library — edit, score, remove low-quality entries
3. **Export** as Alpaca JSONL format
4. Go to **Train Model** page
5. **Select your Ollama model** (e.g. `huihui_ai/qwen3-abliterated:14b`)
6. App auto-resolves to the correct HuggingFace repo (prefers abliterated variants!)
7. **Configure** LoRA params (rank, alpha, epochs, etc.)
8. **Generate + Launch** — training runs in a new console
9. After training -> **import to Ollama** and run your fine-tuned model

### Supported Model Families
Auto-mapping works for: **Qwen3, Qwen2.5, Llama 3/3.1/3.2, Gemma 2/3, Mistral, Mixtral, DeepSeek, Phi-3/4, Dolphin** — including abliterated/uncensored variants.

---

## VRAM Requirements (4-bit QLoRA)

| VRAM | Model Size | Examples |
|------|-----------|----------|
| 4 GB | 1B-3B | Phi-3 Mini, Qwen2.5-3B |
| 6 GB | 3B-4B | Llama 3.2-3B, Qwen3-4B |
| 8 GB | 7B-8B | Mistral-7B, Llama 3.1-8B |
| 12 GB | 9B-14B | Gemma-3-12B, Qwen3-14B |
| 16 GB | 14B-27B | Qwen3-14B, Gemma-3-27B |
| 24 GB | 30B-32B | Qwen2.5-32B, Qwen3-30B-A3B |
| 48 GB | 70B | Llama 3.1-70B (tight) |

---

## Requirements

- **Python 3.10+** (3.12 recommended)
- **Windows** (primary), Linux/Mac supported
- **GPU** (NVIDIA 6GB+ VRAM) for fast training — CPU works fine for everything else
- **~10-20 GB** disk for models/datasets
- **Ollama** installed ([ollama.com](https://ollama.com)) for running local models

See `requirements.txt` for full Python package list.

---

## Project Structure

```
LoRA-Toolkit/
├── main.py                 # Entry point
├── config.py               # App configuration
├── requirements.txt        # Core dependencies
├── setup.bat               # Windows setup script
│
├── core/                   # Backend logic
│   ├── database.py         # SQLite CRUD
│   ├── scraper.py          # Web scraping (trafilatura + BS4)
│   ├── github_scraper.py   # GitHub-specific scraper
│   ├── youtube.py          # YouTube transcript extraction
│   ├── site_crawler.py     # BFS depth crawler
│   ├── exporter.py         # 5 LoRA export formats
│   ├── merger.py           # Model merging (mergekit wrapper)
│   ├── quality.py          # Training data quality scoring
│   ├── file_reader.py      # PDF, TXT, MD, HTML, JSON, CSV reader
│   ├── ocr.py              # Screenshot OCR (Tesseract)
│   ├── settings.py         # JSON settings manager
│   ├── tray.py             # System tray
│   └── hotkeys.py          # Global hotkeys
│
├── gui/                    # Frontend
│   ├── app.py              # Main window + sidebar navigation
│   ├── theme.py            # OLED dark theme colors/fonts
│   ├── widgets.py          # Reusable widgets (Tooltip, StatusBar, etc.)
│   └── pages/              # 14 page views
│       ├── scraper_page.py
│       ├── bulk_scraper_page.py
│       ├── site_crawler_page.py
│       ├── youtube_page.py
│       ├── paste_page.py
│       ├── ocr_page.py
│       ├── import_page.py
│       ├── library_page.py
│       ├── export_page.py
│       ├── training_page.py    # LoRA training + HF auto-resolution
│       ├── merge_page.py       # Model merging
│       ├── setup_page.py       # GPU detection + step-by-step installer
│       └── settings_page.py
│
└── data/                   # Runtime data (gitignored)
    ├── toolkit.db          # SQLite database
    ├── exports/            # Exported training files
    └── settings.json       # User preferences
```

---

## Tech Stack

- **Python 3.12** + **CustomTkinter** — Native-feeling dark UI
- **SQLite** — Local database, zero config
- **trafilatura** + **BeautifulSoup4** — Web scraping
- **youtube-transcript-api** — YouTube transcripts
- **Tesseract OCR** — Screenshot text extraction
- **Unsloth** — Fast LoRA fine-tuning
- **mergekit** — Model merging
- **pystray** — System tray
- **Windows 11 Mica** — Dark titlebar via DWM API

---

## Contributing

Issues, PRs, feature requests welcome! Especially:

- More data sources (Reddit, Discord export, etc.)
- Better CPU training (llama.cpp integration?)
- Auto-captioning with LLaVA/CLIP
- Linux/Mac testing

---

## License & Commercial Use

MIT licensed — free to use, modify, distribute (even commercially), as long as you keep the copyright notice.

If you're thinking of building a paid product around this: go for it! Just give credit in your docs/about page.

---

Made with ❤️ in Connecticut

If this saves you hours stitching tools together — star it or buy me a coffee ☕
