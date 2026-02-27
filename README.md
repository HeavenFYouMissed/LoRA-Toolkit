# LoRA-Toolkit

**All-in-one local GUI for building high-quality LoRA models** — scrape data, organize it, AI-clean with local Ollama, train with Unsloth (GPU or CPU fallback), merge models, and export ready-to-use LoRAs or Ollama Modelfiles.

No cloud, no complicated setup, no stitching 5 tools together.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![GPU](https://img.shields.io/badge/GPU-Optional-orange?logo=nvidia&logoColor=white)

<p align="center">
  <img width="800" alt="LoRA Toolkit - Main Window" src="https://github.com/user-attachments/assets/2415a7c7-286e-4fa4-97bf-d4e22075062c" />
</p>

---

## Why This Exists

Most LoRA tools are either:
- **Training-only** (Kohya_ss, OneTrainer) — no built-in data collection
- **Scraping-only** — no training or merging
- **Cloud/paywalled** — slow, expensive, censored
- **pain-in-the-ass** — might as well get a degree in a specialty. This solves the headaches and nightmares for AI training and data collection.

This is a **single local app** that does the full workflow: collect dirty web/YouTube/forum data -> AI-clean & organize -> export formats -> train LoRA (fast Unsloth or CPU context injection) -> merge models -> deploy to Ollama.

Built for people who want quick, private, offline custom models (characters, art styles, anticheat research, game mods, etc.). I built this for myself because I was tired of the BS, and figured I would make it more complete so others could use it.

I hope it helps the newbies to data and training. It's honestly a pain in the \*\*\*\*. I hope this helps or makes your life easier. I like to see the data, and give clean data to the models instead of just random whatever.

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

<details>
<summary>📸 <b>Data Source Screenshots</b> (click to expand)</summary>
<br>

<img width="700" alt="Web Scraper" src="https://github.com/user-attachments/assets/362acfdf-3b2d-4bb2-8867-505a699b5a37" />

<img width="700" alt="Bulk Scraper" src="https://github.com/user-attachments/assets/6fa3c6f5-946d-4043-b1bd-325493cad581" />

<img width="700" alt="Site Crawler" src="https://github.com/user-attachments/assets/db1e0773-b56d-4774-9619-504526cc64d4" />

<img width="700" alt="YouTube Transcripts" src="https://github.com/user-attachments/assets/a8c04577-9e4e-4d04-91c4-f24dc224b85b" />

<img width="700" alt="Paste Text" src="https://github.com/user-attachments/assets/527acd5d-5ba0-4d31-80ca-bc8cf0b9ab39" />

<img width="700" alt="Import Files" src="https://github.com/user-attachments/assets/d427be68-1bf9-41fc-863e-fd7ed5a6f162" />

</details>

### AI Cleaner (Ollama-Powered)
Clean & polish your training data with local AI — no cloud, no API keys.
- Side-by-side diff review (original vs cleaned) with color-coded changes
- **Live streaming** — see AI output token-by-token as it generates
- Content-type-aware prompts (code, forum, technical, transcript, general)
- Batch mode: processes selected entries one-by-one with Keep / Skip / Regenerate / Edit
- Green ● / gray ○ indicators show which entries have been cleaned
- Dynamic token budget — fast cleaning even with 7B+ models
- Supports uncensored models (Dolphin series) for sensitive topics

<!-- 📸 ADD SCREENSHOT: AI Cleaner page showing side-by-side diff review with streaming -->
<img width="700" alt="AI Cleaner" src="" />

### AI Chat
Chat with your local Ollama models directly in the app.
- **Live streaming** — see tokens appear in real-time
- Model selector + system prompt customization
- Styled chat bubbles (user / assistant / system)
- Conversation history + export to .txt
- Multi-turn conversations via Ollama `/api/chat`

<!-- 📸 ADD SCREENSHOT: AI Chat page showing a conversation -->
<img width="700" alt="AI Chat" src="" />

### 💬 Chat with Data (NEW)
Select entries in the Data Library → click **Chat** → talk to the AI about your actual files.
- **Attach library entries** as context — no copy-pasting walls of text
- Ask: "Explain this script line by line", "Compare file 3 vs file 7", "Generate 20 Q&A pairs"
- File sidebar shows attached entries, word counts, and estimated tokens
- **Save Reply to Library** — capture AI output as a new training entry
- Export entire conversation to .txt
- Works on **CPU or GPU** — any Ollama model, no NVIDIA required
- Smart token budgeting: auto-truncates huge files, splits context evenly

<!-- 📸 ADD SCREENSHOT: Data Chat popup with files loaded in sidebar and conversation -->
<img width="700" alt="Chat with Data" src="" />

### Ollama Integration (Setup Page)
Built-in Ollama management — no terminal needed.
- One-click Ollama download & silent install
- Start Ollama directly from the app
- Pull models from a curated list: fast, balanced, uncensored 🔓, code-focused
- 14 recommended models with VRAM requirements
- Model preloading — keeps model warm in VRAM for instant cleaning

<!-- 📸 ADD SCREENSHOT: Setup page Ollama section with model pull dropdown -->
<img width="700" alt="Ollama Setup" src="" />

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

<img width="700" alt="Training Page" src="https://github.com/user-attachments/assets/4ee326a5-f8bc-4b23-8933-8cf8681627c7" />

### Model Merging ("Forge")
- Mergekit integration (SLERP, Linear, TIES, DARE-TIES, Passthrough)
- Auto YAML config
- Converts to GGUF + Ollama Modelfile

<img width="700" alt="Model Merging Page" src="https://github.com/user-attachments/assets/6125ab81-9c6f-4f9c-b447-1989e4828744" />

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

<img width="700" alt="Setup Page" src="https://github.com/user-attachments/assets/1cb3d966-06b8-4206-894d-7e976e4b1c9d" />

### Offline & Private
Everything runs locally. No telemetry, no cloud, no accounts. Simple settings with basics so it doesn't overwhelm.

<img width="700" alt="Settings Page" src="https://github.com/user-attachments/assets/2b18c8eb-68fb-437e-94a0-47a96f6b2f16" />

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
Scrape/collect data -> Library -> AI Clean -> Export -> Train -> Merge -> Done
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

## Training Workflow

1. **Collect data** using any of the 7 sources
2. **Review** in the Data Library — edit, score, remove low-quality entries
3. **AI Clean** — run entries through the AI Cleaner to polish formatting, remove noise, fix grammar
4. **Export** as Alpaca JSONL format
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
│   ├── database.py         # SQLite CRUD + cleaned_at tracking
│   ├── ai_cleaner.py       # Ollama AI cleaning + chat backend
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
│   └── pages/              # 16 page views + 1 popup
│       ├── scraper_page.py
│       ├── bulk_scraper_page.py
│       ├── site_crawler_page.py
│       ├── youtube_page.py
│       ├── paste_page.py
│       ├── ocr_page.py
│       ├── import_page.py
│       ├── library_page.py
│       ├── cleaner_page.py     # AI Cleaner — side-by-side diff review
│       ├── chat_page.py        # AI Chat with Ollama models
│       ├── data_chat_popup.py  # Chat with Data — files as context
│       ├── export_page.py
│       ├── training_page.py    # LoRA training + HF auto-resolution
│       ├── merge_page.py       # Model merging
│       ├── setup_page.py       # GPU detection + installer + Ollama mgmt
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
- **Ollama** — Local AI for cleaning + chat (pure HTTP, no pip dep)
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
