# LoRA Data Toolkit

A **dead-simple Windows desktop app** for collecting training data from multiple sources and fine-tuning local LLMs with LoRA — all from one interface.

Built with Python + CustomTkinter. Dark OLED theme. No cloud, no subscriptions — everything runs locally.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What It Does

```
Collect Data  →  Organize  →  Export  →  Train LoRA  →  Import to Ollama
```

### 📥 Data Collection (7 sources)
| Source | Description |
|--------|------------|
| 🌐 **Web Scraper** | Extract clean text from any URL (trafilatura + BS4 fallback) |
| ⚡ **Bulk Scraper** | Paste 100+ URLs, scrape them all at once |
| 🕷 **Site Crawler** | BFS depth crawler — crawl entire sites with rate limiting |
| 📺 **YouTube** | Pull transcripts + metadata from YouTube videos |
| 📋 **Paste Text** | Manually paste text, notes, documentation |
| 📸 **Screenshot OCR** | Extract text from images/screenshots (Tesseract) |
| 📁 **Import Files** | Drag-and-drop PDF, TXT, MD, HTML, JSON, CSV, code files |

### 📚 Data Management
- **Library** — Browse, search, edit, score, and delete entries
- **Quality Scoring** — Auto-score entries 0-100 for LoRA training quality
- **Duplicate Detection** — Finds similar titles before adding
- **Export** — 5 LoRA-ready formats: Alpaca, ShareGPT, Completion, ChatML, Raw JSON

### 🧬 Training
- **LoRA Fine-Tuning** — Real training with Unsloth on your NVIDIA GPU
- **Auto Model Resolution** — Pick your Ollama model → auto-detects the HuggingFace source weights
- **Abliterated Model Support** — Prefers abliterated HF repos when source model is abliterated (huihui-ai, etc.)
- **Context Injection** — Quick hack: paste data into system prompt (honest about what it is)
- **VRAM Guide** — Shows what models fit your GPU

### 🔀 Model Merging
- **5 merge methods** — SLERP, Linear, TIES, DARE-TIES, Passthrough
- **mergekit** wrapper with YAML config generation
- **GGUF conversion** + Ollama Modelfile generation

### 🖥️ System Setup
- **GPU Auto-Detection** — Finds your NVIDIA GPU, shows VRAM, driver info
- **One-Click Dependency Install** — Installs PyTorch+CUDA, Unsloth, and all training deps
- **Smart Messaging** — If no GPU, explains that only context injection is available

---

## Screenshots

*Dark OLED theme with Windows 11 Mica titlebar*

---

## Quick Start

### Prerequisites
- **Python 3.11+** (3.12 recommended)
- **Windows 10/11**
- **Ollama** installed ([ollama.com](https://ollama.com)) for running local models

### Option 1: Setup Script
```bat
git clone https://github.com/YOUR_USERNAME/lora-data-toolkit.git
cd lora-data-toolkit
setup.bat
```

### Option 2: Manual
```bash
git clone https://github.com/YOUR_USERNAME/lora-data-toolkit.git
cd lora-data-toolkit
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### For LoRA Training (optional)
If you have an **NVIDIA GPU**, go to **Setup / GPU** page in the app and click **"Install Training"** to auto-install:
- PyTorch with CUDA 12.4
- Unsloth (fast LoRA)
- Transformers, PEFT, TRL, Datasets, etc.

Or install manually:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install "unsloth[cu124-torch250] @ git+https://github.com/unslothai/unsloth.git"
pip install peft transformers trl datasets accelerate bitsandbytes sentencepiece protobuf
```

---

## Project Structure

```
lora-data-toolkit/
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
│       ├── setup_page.py       # GPU detection + dep installer
│       └── settings_page.py
│
└── data/                   # Runtime data (gitignored)
    ├── toolkit.db          # SQLite database
    ├── exports/            # Exported training files
    └── settings.json       # User preferences
```

---

## Training Workflow

1. **Collect data** using any of the 7 sources
2. **Review** in the Data Library — edit, score, remove low-quality entries
3. **Export** as Alpaca JSONL format → `data/exports/training_data.jsonl`
4. Go to **Train Model** page
5. **Select your Ollama model** (e.g. `huihui_ai/qwen3-abliterated:14b`)
6. App auto-resolves → `huihui-ai/Qwen3-14B-abliterated` (abliterated HF repo!)
7. **Configure** LoRA params (rank, alpha, epochs, etc.)
8. **Generate + Launch** → training runs in a new console
9. After training → **import to Ollama** and run your fine-tuned model

### Supported Model Families
Auto-mapping works for: **Qwen3, Qwen2.5, Llama 3/3.1/3.2, Gemma 2/3, Mistral, Mixtral, DeepSeek, Phi-3/4, Dolphin** — including abliterated/uncensored variants.

---

## VRAM Requirements (4-bit QLoRA)

| VRAM | Model Size | Examples |
|------|-----------|----------|
| 4 GB | 1B-3B | Phi-3 Mini, Qwen2.5-3B |
| 8 GB | 7B-8B | Mistral-7B, Llama 3.1-8B |
| 12 GB | 9B-14B | Gemma-3-12B, Qwen3-14B |
| 16 GB | 14B-27B | Qwen3-14B ✓, Gemma-3-27B |
| 24 GB | 30B-32B | Qwen2.5-32B, Qwen3-30B-A3B |
| 48 GB | 70B | Llama 3.1-70B |

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

## License

MIT — do whatever you want with it.

---

## Contributing

Pull requests welcome. This started as a personal tool for collecting game security / cheat detection training data, but it works for any domain.
