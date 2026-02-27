"""
Setup / GPU page -- System detection + numbered step-by-step installer.

Step 1: Core  (app basics -- scraping, OCR, GUI)
Step 2: PyTorch + CUDA  (GPU compute layer)
Step 3: Training stack  (Unsloth, PEFT, TRL, etc.)

Basic users only need Step 1.  Steps 2-3 are for LoRA fine-tuning.
"""

from __future__ import annotations
import importlib, importlib.metadata
import os, platform, subprocess, sys, threading, re
import customtkinter as ctk

from gui.theme  import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, ActionButton, StatusBar, Tooltip, ProgressIndicator


# ---------------------------------------------------------------
#  GPU Detection Helpers
# ---------------------------------------------------------------

def _detect_gpu_wmi():
    """Fallback: query GPU info via PowerShell WMI."""
    try:
        ps = (
            'Get-CimInstance Win32_VideoController | '
            'Select-Object Name, AdapterRAM, DriverVersion | '
            'ConvertTo-Json'
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            return []

        import json
        data = json.loads(r.stdout)
        if isinstance(data, dict):
            data = [data]

        gpus = []
        for g in data:
            name = g.get("Name", "Unknown")
            vram_bytes = g.get("AdapterRAM", 0) or 0
            driver = g.get("DriverVersion", "?")
            is_nvidia = "nvidia" in name.lower()
            vram_gb = _estimate_vram_from_name(name, vram_bytes)
            gpus.append({
                "name": name, "vram_gb": vram_gb,
                "driver": driver, "is_nvidia": is_nvidia,
            })
        return gpus
    except Exception:
        return []


def _detect_gpu_nvidia_smi():
    """Preferred: use nvidia-smi for accurate VRAM on NVIDIA cards."""
    try:
        r = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            return []
        gpus = []
        for line in r.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            name   = parts[0]
            vram   = round(float(parts[1]) / 1024, 1)   # MiB -> GB
            driver = parts[2]
            gpus.append({
                "name": name, "vram_gb": vram,
                "driver": driver, "is_nvidia": True,
            })
        return gpus
    except Exception:
        return []


def _estimate_vram_from_name(name: str, wmi_bytes: int = 0) -> float:
    """Map GPU name -> VRAM (GB).  WMI often reports 4 GB for big cards."""
    name_lower = name.lower()
    known = {
        "5090": 32, "5080": 16, "5070 ti": 16, "5070": 12,
        "5060 ti": 16, "5060": 8,
        "4090": 24, "4080 super": 16, "4080": 16,
        "4070 ti super": 16, "4070 ti": 12,
        "4070 super": 12, "4070": 12,
        "4060 ti": 16, "4060": 8,
        "3090 ti": 24, "3090": 24, "3080 ti": 12, "3080": 10,
        "3070 ti": 8, "3070": 8, "3060 ti": 8, "3060": 12,
        "a100": 80, "a6000": 48, "a5000": 24, "a4000": 16,
        "a40": 48, "l40": 48, "h100": 80,
    }
    for pattern, gb in known.items():
        if pattern in name_lower:
            return gb

    if wmi_bytes and wmi_bytes > 0:
        gb = round(wmi_bytes / (1024 ** 3), 1)
        if gb > 0.5:
            return gb
    return 0


def _detect_gpu():
    """Best-effort GPU detection.  Returns list of gpu dicts."""
    gpus = _detect_gpu_nvidia_smi()
    if gpus:
        return gpus
    return _detect_gpu_wmi()


# ---------------------------------------------------------------
#  Dependency Definitions
# ---------------------------------------------------------------

CORE_DEPS = [
    "customtkinter", "beautifulsoup4", "requests",
    "youtube-transcript-api", "pytesseract", "Pillow",
    "PyMuPDF", "trafilatura", "lxml", "pystray", "keyboard",
    "pyyaml", "windnd",
]

TRAINING_PKGS = [
    "peft", "transformers", "trl",
    "datasets", "accelerate", "bitsandbytes",
    "sentencepiece", "protobuf",
]

def _pip_cmd(*args: str) -> list[str]:
    """Build a pip command list using the active Python interpreter."""
    return [sys.executable, "-m", "pip", "install"] + list(args)

TORCH_CUDA_CMD = (
    f'"{sys.executable}" -m pip install torch torchvision torchaudio '
    f'--index-url https://download.pytorch.org/whl/cu124'
)

UNSLOTH_CMD = (
    f'"{sys.executable}" -m pip install "unsloth[cu124-torch250] @ '
    f'git+https://github.com/unslothai/unsloth.git"'
)


# ---------------------------------------------------------------
#  Setup Page
# ---------------------------------------------------------------

class SetupPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self.gpus: list[dict] = []
        self._step_states = {1: "unknown", 2: "unknown", 3: "unknown"}
        self._build_ui()
        self.after(300, self._detect_system)

    # -- small helpers -----------------------------------------

    def _card(self, parent, *, pad_bottom=12):
        f = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        f.pack(fill="x", pady=(0, pad_bottom))
        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=10)
        return inner

    def _heading(self, parent, text):
        ctk.CTkLabel(
            parent, text=text,
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w")

    def _hint(self, parent, text):
        ctk.CTkLabel(
            parent, text=text,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            wraplength=650, justify="left",
        ).pack(anchor="w", pady=(2, 6))

    # ==========================================================
    #  Build UI
    # ==========================================================

    def _build_ui(self):
        self.container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=15)
        c = self.container

        PageHeader(
            c, icon="\U0001f5a5\ufe0f", title="System Setup",
            subtitle="GPU detection  +  step-by-step dependency installer",
        ).pack(fill="x", pady=(0, 12))

        # -- System Info ---------------------------------------
        sys_card = self._card(c)
        self._heading(sys_card, "\U0001f4bb  System Info")

        self.sys_label = ctk.CTkLabel(
            sys_card, text="Detecting...",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
            justify="left", wraplength=600,
        )
        self.sys_label.pack(anchor="w", pady=(4, 0))

        # -- GPU -----------------------------------------------
        gpu_card = self._card(c)
        self._heading(gpu_card, "\U0001f3ae  GPU Detection")
        self._hint(gpu_card,
            "LoRA fine-tuning requires an NVIDIA GPU with CUDA. "
            "We detect your hardware automatically.",
        )

        self.gpu_label = ctk.CTkLabel(
            gpu_card, text="Scanning...",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
            justify="left", wraplength=600,
        )
        self.gpu_label.pack(anchor="w", pady=(4, 0))

        self.gpu_verdict = ctk.CTkLabel(
            gpu_card, text="",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["accent_green"],
            justify="left", wraplength=600,
        )
        self.gpu_verdict.pack(anchor="w", pady=(6, 0))

        ActionButton(
            gpu_card, text="\U0001f504  Re-scan GPU",
            command=self._detect_system,
            style="secondary", width=150,
        ).pack(anchor="w", pady=(8, 0))

        # -- Ollama --------------------------------------------
        ollama_card = self._card(c)
        self._heading(ollama_card, "\U0001f999  Ollama  (Local AI)")
        self._hint(ollama_card,
            "Ollama runs AI models locally on your machine.  "
            "Needed for the AI Cleaner and AI Chat features."
        )

        self.ollama_label = ctk.CTkLabel(
            ollama_card, text="Checking...",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
            justify="left", wraplength=600,
        )
        self.ollama_label.pack(anchor="w", pady=(4, 0))

        ollama_btn_row = ctk.CTkFrame(ollama_card, fg_color="transparent")
        ollama_btn_row.pack(fill="x", pady=(8, 0))

        self.btn_install_ollama = ActionButton(
            ollama_btn_row, text="\U0001f4e5  Download Ollama",
            command=self._install_ollama,
            style="primary", width=190,
        )
        self.btn_install_ollama.pack(side="left", padx=(0, 8))
        Tooltip(self.btn_install_ollama,
                "Download and install Ollama from ollama.com.\n"
                "~100 MB installer — runs silently.")

        self.btn_start_ollama = ActionButton(
            ollama_btn_row, text="\u25b6  Start Ollama",
            command=self._start_ollama,
            style="secondary", width=140,
        )
        self.btn_start_ollama.pack(side="left", padx=(0, 8))
        Tooltip(self.btn_start_ollama, "Start the Ollama background service\nso AI features work.")

        self.btn_recheck_ollama = ActionButton(
            ollama_btn_row, text="\U0001f504  Re-check",
            command=self._recheck_ollama,
            style="secondary", width=120,
        )
        self.btn_recheck_ollama.pack(side="left")

        self.prog_ollama = ProgressIndicator(ollama_card)
        self.prog_ollama.pack(fill="x", pady=(6, 0))

        # -- Model Pull ----------------------------------------
        model_card = self._card(c)
        self._heading(model_card, "\U0001f4e6  Pull AI Models")
        self._hint(model_card,
            "Download a model to use with AI Cleaner and AI Chat.  "
            "You need at least ONE model pulled."
        )

        # Recommended models list — includes uncensored options
        RECOMMENDED_MODELS = [
            # ── Fast / Small (best for cleaning speed) ──
            ("llama3.2:3b",           "2 GB",   "⚡ Fast cleaning — best bang-for-buck"),
            ("phi3:mini",             "2.3 GB", "⚡ Microsoft Phi-3 — tiny but smart"),
            ("qwen2.5:3b",           "2 GB",   "⚡ Fast multilingual cleaning"),
            # ── Balanced (good quality, reasonable speed) ──
            ("llama3.1:8b",           "4.7 GB", "Balanced quality & speed"),
            ("mistral:7b",            "4.1 GB", "Strong general-purpose"),
            ("qwen2.5:7b",           "4.7 GB", "Excellent multilingual"),
            ("gemma2:9b",             "5.4 GB", "Google — very capable"),
            # ── Uncensored (won't refuse topics) ──
            ("dolphin-mistral:7b",    "4.1 GB", "🔓 Uncensored Mistral — great for cleaning"),
            ("dolphin-llama3:8b",     "4.7 GB", "🔓 Uncensored Llama 3 — recommended"),
            ("dolphin-phi:2.7b",      "1.6 GB", "🔓 Uncensored + tiny — fastest uncensored"),
            ("nous-hermes2:10.7b",    "6.1 GB", "🔓 Less filtered — high quality"),
            # ── Code-focused ──
            ("codellama:7b",          "3.8 GB", "Code cleaning specialist"),
            ("deepseek-coder:6.7b",   "3.8 GB", "Great for code-heavy data"),
        ]

        self._pulled_models: list[str] = []

        # Pulled models display
        self.pulled_label = ctk.CTkLabel(
            model_card, text="Checking installed models...",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            justify="left", wraplength=600,
        )
        self.pulled_label.pack(anchor="w", pady=(2, 6))

        # Model selector + pull button
        pull_row = ctk.CTkFrame(model_card, fg_color="transparent")
        pull_row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            pull_row, text="Model to pull:",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 8))

        self.pull_model_menu = ctk.CTkOptionMenu(
            pull_row,
            values=[m[0] for m in RECOMMENDED_MODELS],
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=200, height=30,
        )
        self.pull_model_menu.pack(side="left", padx=(0, 8))

        self.btn_pull = ActionButton(
            pull_row, text="\u2b07  Pull Model",
            command=self._pull_model,
            style="success", width=140,
        )
        self.btn_pull.pack(side="left", padx=(0, 8))
        Tooltip(self.btn_pull, "Download the selected model.\nFirst pull takes a while (2-5 GB).\nSubsequent pulls are quick (cached layers).")

        # Custom model name
        ctk.CTkLabel(
            pull_row, text="or custom:",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        ).pack(side="left", padx=(8, 4))

        self.custom_model_entry = ctk.CTkEntry(
            pull_row, width=160, height=30,
            placeholder_text="e.g. llama3:70b",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=6,
        )
        self.custom_model_entry.pack(side="left")
        Tooltip(self.custom_model_entry,
                "Type any model name from ollama.com/library.\n"
                "Examples: llama3:70b, mixtral:8x7b, solar:10.7b")

        self.prog_pull = ProgressIndicator(model_card)
        self.prog_pull.pack(fill="x", pady=(6, 0))

        # Recommended table
        rec_label = ctk.CTkLabel(
            model_card,
            text="\U0001f4a1  Recommended Models",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_secondary"],
        )
        rec_label.pack(anchor="w", pady=(8, 2))

        rec_text = "Model                    Size      Notes\n" + "\u2500" * 68 + "\n"
        for name, size, note in RECOMMENDED_MODELS:
            rec_text += f"{name:<25}{size:<10}{note}\n"
        rec_text += (
            "\n\U0001f9f9  BEST FOR CLEANING:\n"
            "   \u2022 Fastest: llama3.2:3b, phi3:mini, dolphin-phi:2.7b\n"
            "   \u2022 Quality: dolphin-mistral:7b, qwen2.5:7b\n"
            "   \u2022 Uncensored (won't refuse): dolphin-mistral:7b, dolphin-llama3:8b\n"
            "\n\U0001f4be  VRAM GUIDE:\n"
            "   \u2022 8 GB: llama3.2:3b, phi3:mini, dolphin-phi:2.7b\n"
            "   \u2022 12-16 GB: dolphin-mistral:7b, llama3.1:8b, qwen2.5:7b\n"
            "   \u2022 24+ GB: gemma2:9b, nous-hermes2:10.7b, or bigger\n"
            "\n\U0001f512  UNCENSORED = model won't refuse sensitive topics\n"
            "   Important for security research, medical data, adult content, etc."
        )

        ctk.CTkLabel(
            model_card, text=rec_text,
            font=("Consolas", FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
            justify="left",
        ).pack(anchor="w")

        # ======================================================
        #  INSTALL STEPS -- big numbered cards
        # ======================================================

        ctk.CTkLabel(
            c,
            text="\U0001f4e6  Install Dependencies -- follow the steps in order",
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", pady=(6, 2))

        ctk.CTkLabel(
            c,
            text=(
                "Basic users only need Step 1.  "
                "Steps 2 + 3 are for LoRA fine-tuning and require an NVIDIA GPU."
            ),
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            wraplength=650, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        # -- Step 1: Core --------------------------------------
        s1 = self._card(c)
        self._step_header(s1, "1", "Core App Dependencies",
                          "Everything the app needs to run -- scraping, OCR, YouTube, "
                          "import/export.  No GPU required.")
        self._hint(s1,
            "Packages:  " + ", ".join(CORE_DEPS),
        )

        s1_row = ctk.CTkFrame(s1, fg_color="transparent")
        s1_row.pack(fill="x", pady=(4, 0))

        self.btn_step1 = ActionButton(
            s1_row, text="\u2460  Install Core",
            command=self._install_step1,
            style="primary", width=180,
        )
        self.btn_step1.pack(side="left", padx=(0, 10))
        Tooltip(self.btn_step1,
                "pip install customtkinter, trafilatura, etc.\n"
                "Quick download -- a few MB.")

        self.lbl_step1 = ctk.CTkLabel(
            s1_row, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.lbl_step1.pack(side="left")

        self.prog_step1 = ProgressIndicator(s1)
        self.prog_step1.pack(fill="x", pady=(6, 0))

        # -- Step 2: PyTorch + CUDA ----------------------------
        s2 = self._card(c)
        self._step_header(s2, "2", "PyTorch + CUDA 12.4",
                          "GPU compute layer -- lets Python talk to your NVIDIA GPU.  "
                          "Skip this if you only need basic features.")
        self._hint(s2, "\u26a0  ~2.5 GB download.  Requires NVIDIA GPU.")

        s2_row = ctk.CTkFrame(s2, fg_color="transparent")
        s2_row.pack(fill="x", pady=(4, 0))

        self.btn_step2 = ActionButton(
            s2_row, text="\u2461  Install PyTorch + CUDA",
            command=self._install_step2,
            style="primary", width=230,
        )
        self.btn_step2.pack(side="left", padx=(0, 10))
        Tooltip(self.btn_step2,
                "Runs:\n" + TORCH_CUDA_CMD + "\n\n"
                "Large download -- be patient.")

        self.lbl_step2 = ctk.CTkLabel(
            s2_row, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.lbl_step2.pack(side="left")

        self.prog_step2 = ProgressIndicator(s2)
        self.prog_step2.pack(fill="x", pady=(6, 0))

        # -- Step 3: Training stack ----------------------------
        s3 = self._card(c)
        self._step_header(s3, "3", "Training Stack  (Unsloth + Friends)",
                          "Everything for LoRA fine-tuning -- Unsloth, PEFT, TRL, "
                          "Transformers, Datasets, etc.")
        self._hint(s3, "\u26a0  ~2 GB download.  Requires Step 2 first.")

        s3_row = ctk.CTkFrame(s3, fg_color="transparent")
        s3_row.pack(fill="x", pady=(4, 0))

        self.btn_step3 = ActionButton(
            s3_row, text="\u2462  Install Training Stack",
            command=self._install_step3,
            style="success", width=230,
        )
        self.btn_step3.pack(side="left", padx=(0, 10))
        Tooltip(self.btn_step3,
                "Installs Unsloth (fast LoRA) + remaining\n"
                "training libraries (PEFT, TRL, etc.).\n\n"
                "Run Step 2 first!")

        self.lbl_step3 = ctk.CTkLabel(
            s3_row, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.lbl_step3.pack(side="left")

        self.prog_step3 = ProgressIndicator(s3)
        self.prog_step3.pack(fill="x", pady=(6, 0))

        # -- Check All button ----------------------------------
        chk_row = ctk.CTkFrame(c, fg_color="transparent")
        chk_row.pack(fill="x", pady=(4, 10))

        ActionButton(
            chk_row, text="\U0001f50d  Check All Dependencies",
            command=self._check_deps,
            style="secondary", width=220,
        ).pack(side="left")

        # -- Install log ---------------------------------------
        log_card = self._card(c)
        self._heading(log_card, "\U0001f4dd  Install Log")
        self._hint(log_card, "Output from install commands appears here.")

        self.log_text = ctk.CTkTextbox(
            log_card, height=200,
            font=("Consolas", FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_secondary"],
            corner_radius=8,
        )
        self.log_text.pack(fill="x", pady=(4, 0))

        # -- VRAM Guide ----------------------------------------
        guide_card = self._card(c)
        self._heading(guide_card, "\U0001f4ca  What Can You Train?")

        guide = (
            "VRAM          Model Size        Examples\n"
            "-----------------------------------------------------\n"
            " 4 GB         1B-3B             Phi-3 Mini, Qwen2.5-3B\n"
            " 6 GB         3B-4B             Llama 3.2-3B, Qwen3-4B\n"
            " 8 GB         7B-8B             Mistral-7B, Llama 3.1-8B\n"
            "12 GB         9B-14B            Gemma-3-12B, Qwen3-14B\n"
            "16 GB         14B-27B           Qwen3-14B, Gemma-3-27B\n"
            "24 GB         30B-32B           Qwen2.5-32B, Qwen3-30B-A3B\n"
            "48 GB         70B               Llama 3.1-70B (tight)\n\n"
            "All sizes assume 4-bit QLoRA + gradient checkpointing.\n"
            "Use batch size 2-4 for tighter VRAM.  Reduce max_seq_len if OOM."
        )

        ctk.CTkLabel(
            guide_card, text=guide,
            font=("Consolas", FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
            justify="left",
        ).pack(anchor="w")

        # -- Toolkit Log Viewer ---------------------------------
        tlog_card = self._card(c)
        self._heading(tlog_card, "\U0001f4cb  Toolkit Log")
        self._hint(tlog_card,
            "Recent app log entries (errors, warnings, info).  "
            "Useful for troubleshooting."
        )

        tlog_btn_row = ctk.CTkFrame(tlog_card, fg_color="transparent")
        tlog_btn_row.pack(fill="x", pady=(0, 6))

        ActionButton(
            tlog_btn_row, text="\U0001f504  Refresh Log",
            command=self._load_toolkit_log,
            style="secondary", width=150,
        ).pack(side="left", padx=(0, 8))

        ActionButton(
            tlog_btn_row, text="\U0001f4c2  Open Log File",
            command=self._open_log_file,
            style="secondary", width=160,
        ).pack(side="left")

        self.tlog_text = ctk.CTkTextbox(
            tlog_card, height=220,
            font=("Consolas", FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_secondary"],
            corner_radius=8,
        )
        self.tlog_text.pack(fill="x", pady=(0, 0))

        # Auto-load log on page build
        self.after(600, self._load_toolkit_log)

        # -- Status bar ----------------------------------------
        self.status = StatusBar(c)
        self.status.pack(fill="x", pady=(5, 0))

    # -- step header helper ------------------------------------

    def _step_header(self, parent, number: str, title: str, desc: str):
        """Render a big circled number + title + description."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")

        # Big circle number
        circle = ctk.CTkFrame(
            row, width=38, height=38,
            corner_radius=19,
            fg_color=COLORS["accent_blue"],
        )
        circle.pack(side="left", padx=(0, 10))
        circle.pack_propagate(False)

        ctk.CTkLabel(
            circle, text=number,
            font=(FONT_FAMILY, 18, "bold"),
            text_color="#ffffff",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Title + desc
        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            col, text=title,
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            col, text=desc,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
            wraplength=550, justify="left",
        ).pack(anchor="w")

    # ==========================================================
    #  System Detection
    # ==========================================================

    def _detect_system(self):
        self.status.set_working("Detecting system hardware...")

        def _do():
            py_ver  = platform.python_version()
            os_name = platform.platform()
            cpu     = platform.processor() or "Unknown CPU"
            sys_text = f"Python:  {py_ver}\nOS:      {os_name}\nCPU:     {cpu}"

            gpus = _detect_gpu()

            try:
                r = subprocess.run(
                    ["ollama", "--version"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                ollama_ver = r.stdout.strip() if r.returncode == 0 else None
            except Exception:
                ollama_ver = None

            self.after(0, lambda: self._show_detection(sys_text, gpus, ollama_ver))

        threading.Thread(target=_do, daemon=True).start()

    def _show_detection(self, sys_text, gpus, ollama_ver):
        self.gpus = gpus

        # System
        self.sys_label.configure(text=sys_text)

        # GPU
        if not gpus:
            self.gpu_label.configure(
                text="No GPUs detected (or detection failed).",
                text_color=COLORS["text_muted"],
            )
            self.gpu_verdict.configure(
                text="\u274c  No NVIDIA GPU -- only Context Injection available (no real training)",
                text_color=COLORS["error"],
            )
        else:
            lines = []
            has_nvidia = False
            best_vram = 0
            for g in gpus:
                vram_str  = f"{g['vram_gb']} GB" if g['vram_gb'] else "? GB"
                nv_tag    = "  \u2705 NVIDIA" if g['is_nvidia'] else "  \u26a0 Not NVIDIA"
                lines.append(
                    f"  {g['name']}  --  {vram_str}  (Driver: {g['driver']}){nv_tag}"
                )
                if g['is_nvidia']:
                    has_nvidia = True
                    best_vram = max(best_vram, g['vram_gb'])

            self.gpu_label.configure(
                text="\n".join(lines), text_color=COLORS["text_primary"],
            )

            if has_nvidia:
                if best_vram >= 8:
                    self.gpu_verdict.configure(
                        text=f"\U0001f525  {best_vram} GB VRAM -- you can train LoRA models!",
                        text_color=COLORS["accent_green"],
                    )
                elif best_vram >= 4:
                    self.gpu_verdict.configure(
                        text=f"\U0001f44d  {best_vram} GB VRAM -- can train small models (1B-3B)",
                        text_color=COLORS["accent_yellow"],
                    )
                else:
                    self.gpu_verdict.configure(
                        text=f"\u26a0  {best_vram} GB VRAM -- very tight, may struggle",
                        text_color=COLORS["accent_orange"],
                    )
            else:
                self.gpu_verdict.configure(
                    text="\u274c  No NVIDIA GPU -- LoRA training needs CUDA. "
                         "Context Injection still works.",
                    text_color=COLORS["error"],
                )

        # Ollama
        if ollama_ver:
            self.ollama_label.configure(
                text=f"\u2705  Ollama installed: {ollama_ver}",
                text_color=COLORS["accent_green"],
            )
            self.btn_install_ollama.configure(state="disabled")
        else:
            self.ollama_label.configure(
                text="\u274c  Ollama not found — click 'Download Ollama' to install,\n"
                     "    or get it manually from https://ollama.com",
                text_color=COLORS["accent_orange"],
            )

        # Check pulled models
        self._refresh_pulled_models()

        self.status.set_success("System detection complete")
        self._check_deps()

    # ==========================================================
    #  Dependency Check
    # ==========================================================

    _IMPORT_ALIASES = {
        "pillow": "PIL", "pymupdf": "fitz", "beautifulsoup4": "bs4",
        "youtube-transcript-api": "youtube_transcript_api", "pyyaml": "yaml",
    }

    def _check_deps(self):
        self.status.set_working("Checking installed packages...")

        def _do():
            core_ok, core_miss   = self._probe_list(CORE_DEPS)
            torch_ok             = self._probe_torch()
            train_ok, train_miss = self._probe_list(
                ["unsloth"] + TRAINING_PKGS,
            )
            self.after(0, lambda: self._show_dep_status(
                core_ok, core_miss, torch_ok, train_ok, train_miss,
            ))

        threading.Thread(target=_do, daemon=True).start()

    def _probe_list(self, pkgs):
        """Return (installed_set, missing_set) for a list of pip names.

        Uses importlib.metadata (pip's package registry) instead of
        __import__ so that packages installed mid-session are detected
        without needing a restart.
        """
        # Flush finder caches so newly-installed packages are visible
        importlib.invalidate_caches()

        ok, miss = set(), set()
        for pkg in pkgs:
            try:
                importlib.metadata.distribution(pkg)
                ok.add(pkg)
            except importlib.metadata.PackageNotFoundError:
                miss.add(pkg)
        return ok, miss

    def _probe_torch(self):
        """Check torch + CUDA via subprocess so mid-session installs are seen.

        Returns (has_cuda: bool, version: str|None, cuda_ver: str|None).
        """
        try:
            r = subprocess.run(
                [sys.executable, "-c",
                 "import torch; print(torch.__version__); "
                 "print(torch.version.cuda or ''); "
                 "print(torch.cuda.is_available())"],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if r.returncode != 0:
                return False, None, None
            lines = r.stdout.strip().splitlines()
            version  = lines[0] if len(lines) > 0 else None
            cuda_ver = lines[1] if len(lines) > 1 and lines[1] else None
            has_cuda = lines[2].strip() == "True" if len(lines) > 2 else False
            return has_cuda, version, cuda_ver
        except Exception:
            return False, None, None

    def _show_dep_status(self, core_ok, core_miss, torch_ok, train_ok, train_miss):
        torch_has_cuda, torch_ver, cuda_ver = torch_ok

        # Step 1
        if not core_miss:
            self.lbl_step1.configure(
                text="\u2705  All core packages installed",
                text_color=COLORS["accent_green"],
            )
            self._step_states[1] = "done"
        else:
            self.lbl_step1.configure(
                text=f"\u274c  {len(core_miss)} missing:  " + ", ".join(sorted(core_miss)),
                text_color=COLORS["error"],
            )
            self._step_states[1] = "missing"

        # Step 2
        if torch_has_cuda:
            self.lbl_step2.configure(
                text=f"\u2705  PyTorch {torch_ver}  |  CUDA {cuda_ver}",
                text_color=COLORS["accent_green"],
            )
            self._step_states[2] = "done"
        elif torch_ver:
            self.lbl_step2.configure(
                text=f"\u26a0  PyTorch {torch_ver} but NO CUDA",
                text_color=COLORS["accent_orange"],
            )
            self._step_states[2] = "missing"
        else:
            self.lbl_step2.configure(
                text="\u274c  Not installed",
                text_color=COLORS["error"],
            )
            self._step_states[2] = "missing"

        # Step 3
        if not train_miss:
            self.lbl_step3.configure(
                text="\u2705  Training stack installed",
                text_color=COLORS["accent_green"],
            )
            self._step_states[3] = "done"
        else:
            self.lbl_step3.configure(
                text=f"\u274c  {len(train_miss)} missing:  " + ", ".join(sorted(train_miss)),
                text_color=COLORS["error"],
            )
            self._step_states[3] = "missing"

        # Overall
        done = sum(1 for v in self._step_states.values() if v == "done")
        if done == 3:
            self.status.set_success("All dependencies installed -- ready to train!")
        elif self._step_states[1] == "done":
            self.status.set_success(
                f"Core OK -- {3 - done} training step(s) remaining"
            )
        else:
            self.status.set_error("Core deps missing -- click  \u2460  Install Core")

    # ==========================================================
    #  Step Installers
    # ==========================================================

    def _log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    @staticmethod
    def _clean_pip_output(raw: str) -> str:
        """Strip pip [notice] lines (e.g. 'a new release of pip is available')."""
        return "\n".join(
            ln for ln in raw.splitlines()
            if not ln.strip().startswith("[notice]")
        )

    def _run_pip(self, label: str, cmd, *, shell=False, timeout=600):
        """Run a pip command, log output, return True on success."""
        self._log(f"\n--- {label} ---")
        self._log(f"> {cmd if isinstance(cmd, str) else ' '.join(cmd)}\n")

        try:
            r = subprocess.run(
                cmd, shell=shell,
                capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out = self._clean_pip_output(
                (r.stdout or "") + (r.stderr or "")
            )
            # Trim huge output but keep last chunk
            if len(out) > 3000:
                out = out[:500] + "\n... (trimmed) ...\n" + out[-1500:]
            self.after(0, lambda: self._log(out))
            return r.returncode == 0
        except subprocess.TimeoutExpired:
            self.after(0, lambda: self._log(f"\u23f1  Timed out after {timeout}s"))
            return False
        except Exception as e:
            self.after(0, lambda: self._log(f"Error: {e}"))
            return False

    # -- Step 1 ------------------------------------------------

    def _install_step1(self):
        self.btn_step1.configure(state="disabled", text="\u23f3  Installing...")
        self.status.set_working("Step 1 -- Installing core dependencies...")
        self.prog_step1.start_indeterminate("Upgrading pip & installing core packages\u2026")

        def _do():
            # Silently upgrade pip itself first so "[notice]" never appears
            self._run_pip(
                "Upgrading pip",
                [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                timeout=60,
            )
            self.after(0, lambda: self.prog_step1.set_phase("Installing core packages\u2026"))
            ok = self._run_pip(
                "Step 1: Core Dependencies",
                _pip_cmd(*CORE_DEPS),
                timeout=300,
            )
            self.after(0, lambda: self._step_done(1, ok))

        threading.Thread(target=_do, daemon=True).start()

    # -- Step 2 ------------------------------------------------

    def _install_step2(self):
        # Warn if no NVIDIA GPU
        nvidia = [g for g in self.gpus if g.get("is_nvidia")]
        if not nvidia:
            self.status.set_error(
                "No NVIDIA GPU detected -- PyTorch CUDA won't work without one."
            )
            self._log(
                "\n\u26a0  No NVIDIA GPU detected.  If you're sure you have one,\n"
                "   re-scan GPU above, then try again.\n"
                f"\n   Manual command:\n   {TORCH_CUDA_CMD}\n"
            )
            return

        self.btn_step2.configure(state="disabled", text="\u23f3  Installing...")
        self.status.set_working("Step 2 -- Installing PyTorch + CUDA 12.4  (large download)...")
        self.prog_step2.start_indeterminate("Downloading PyTorch + CUDA (~2.5 GB)\u2026")

        def _do():
            ok = self._run_pip(
                "Step 2: PyTorch + CUDA 12.4",
                TORCH_CUDA_CMD, shell=True, timeout=900,
            )
            self.after(0, lambda: self._step_done(2, ok))

        threading.Thread(target=_do, daemon=True).start()

    # -- Step 3 ------------------------------------------------

    def _install_step3(self):
        # Warn if step 2 not done
        if self._step_states[2] != "done":
            self.status.set_error(
                "Run Step 2 first -- Unsloth needs PyTorch with CUDA."
            )
            self._log(
                "\n\u26a0  Step 2 (PyTorch + CUDA) must be installed before Step 3.\n"
            )
            return

        self.btn_step3.configure(state="disabled", text="\u23f3  Installing...")
        self.status.set_working("Step 3 -- Installing Unsloth + training libraries...")
        self.prog_step3.start_indeterminate("Installing Unsloth from GitHub\u2026")

        def _do():
            # 3a: Unsloth from git
            self.after(0, lambda: self.status.set_working(
                "Step 3a -- Installing Unsloth from GitHub..."
            ))
            ok_us = self._run_pip(
                "Step 3a: Unsloth",
                UNSLOTH_CMD, shell=True, timeout=600,
            )

            # 3b: remaining packages
            self.after(0, lambda: self.status.set_working(
                "Step 3b -- Installing PEFT, TRL, Transformers..."
            ))
            self.after(0, lambda: self.prog_step3.set_phase("Installing PEFT, TRL, Transformers\u2026"))
            ok_rest = self._run_pip(
                "Step 3b: PEFT + TRL + Transformers + more",
                _pip_cmd(*TRAINING_PKGS),
                timeout=300,
            )

            ok = ok_us and ok_rest
            self.after(0, lambda: self._step_done(3, ok))

        threading.Thread(target=_do, daemon=True).start()

    # -- Post-install ------------------------------------------

    def _step_done(self, step: int, ok: bool):
        btns  = {1: self.btn_step1, 2: self.btn_step2, 3: self.btn_step3}
        progs = {1: self.prog_step1, 2: self.prog_step2, 3: self.prog_step3}
        names = {
            1: "\u2460  Install Core",
            2: "\u2461  Install PyTorch + CUDA",
            3: "\u2462  Install Training Stack",
        }
        btns[step].configure(state="normal", text=names[step])

        if ok:
            progs[step].stop(f"Step {step} installed \u2713")
            self._log(f"\n\u2705  Step {step} complete!\n")
            self.status.set_success(f"Step {step} installed successfully!")
        else:
            progs[step].set_progress(1.0, f"Step {step} had errors")
            progs[step].bar.configure(progress_color=COLORS["error"])
            self._log(f"\n\u274c  Step {step} had errors -- scroll up for details.\n")
            self.status.set_error(f"Step {step} had errors -- check the log above")

        # Re-check everything
        self.after(500, self._check_deps)

    # ==========================================================
    #  Ollama Install / Pull / Start
    # ==========================================================

    def _install_ollama(self):
        """Download and silently install Ollama from ollama.com."""
        self.btn_install_ollama.configure(state="disabled", text="\u23f3  Downloading...")
        self.status.set_working("Downloading Ollama installer...")
        self.prog_ollama.start_indeterminate("Downloading Ollama installer (~100 MB)\u2026")

        def _do():
            import urllib.request, tempfile
            url = "https://ollama.com/download/OllamaSetup.exe"
            tmp = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
            try:
                self.after(0, lambda: self._log("--- Downloading Ollama ---"))
                self.after(0, lambda: self._log(f"> {url}\n"))
                urllib.request.urlretrieve(url, tmp)
                self.after(0, lambda: self.prog_ollama.set_phase("Running installer\u2026"))
                self.after(0, lambda: self._log("Download complete. Running installer...\n"))

                # Silent install
                r = subprocess.run(
                    [tmp, "/VERYSILENT", "/NORESTART"],
                    capture_output=True, text=True, timeout=300,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                success = r.returncode == 0
                if success:
                    self.after(0, lambda: self._log("\u2705  Ollama installed successfully!\n"))
                else:
                    out = (r.stdout or "") + (r.stderr or "")
                    self.after(0, lambda: self._log(f"Installer output:\n{out}\n"))
            except Exception as e:
                success = False
                self.after(0, lambda: self._log(f"Error: {e}\n"))

            def _finish():
                self.prog_ollama.stop("Done" if success else "Error")
                self.btn_install_ollama.configure(
                    state="normal", text="\U0001f4e5  Download Ollama"
                )
                if success:
                    self.status.set_success("Ollama installed! Click 'Start Ollama' to begin.")
                    self.ollama_label.configure(
                        text="\u2705  Ollama installed — click 'Start Ollama' to run",
                        text_color=COLORS["accent_green"],
                    )
                    self.btn_install_ollama.configure(state="disabled")
                else:
                    self.status.set_error("Ollama install failed — check log")
            self.after(0, _finish)

        threading.Thread(target=_do, daemon=True).start()

    def _start_ollama(self):
        """Start the Ollama background service."""
        self.status.set_working("Starting Ollama...")

        def _do():
            try:
                # Try 'ollama serve' in background
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                )
                import time
                time.sleep(3)

                # Verify it's running
                from core.ai_cleaner import is_ollama_running
                if is_ollama_running():
                    self.after(0, lambda: self.status.set_success("Ollama is running!"))
                    self.after(0, lambda: self.ollama_label.configure(
                        text="\u2705  Ollama running",
                        text_color=COLORS["accent_green"],
                    ))
                    self.after(0, self._refresh_pulled_models)
                else:
                    self.after(0, lambda: self.status.set_error(
                        "Ollama started but not responding — try again in a moment"
                    ))
            except FileNotFoundError:
                self.after(0, lambda: self.status.set_error(
                    "Ollama not found — install it first"
                ))
            except Exception as e:
                self.after(0, lambda: self.status.set_error(f"Error starting Ollama: {e}"))

        threading.Thread(target=_do, daemon=True).start()

    def _recheck_ollama(self):
        """Re-run Ollama detection."""
        self.ollama_label.configure(text="Checking...", text_color=COLORS["text_muted"])
        self.pulled_label.configure(text="Checking...", text_color=COLORS["text_muted"])

        def _do():
            try:
                r = subprocess.run(
                    ["ollama", "--version"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                ver = r.stdout.strip() if r.returncode == 0 else None
            except Exception:
                ver = None

            def _update():
                if ver:
                    self.ollama_label.configure(
                        text=f"\u2705  Ollama installed: {ver}",
                        text_color=COLORS["accent_green"],
                    )
                    self.btn_install_ollama.configure(state="disabled")
                else:
                    self.ollama_label.configure(
                        text="\u274c  Ollama not found",
                        text_color=COLORS["accent_orange"],
                    )
                    self.btn_install_ollama.configure(state="normal")
                self._refresh_pulled_models()
            self.after(0, _update)

        threading.Thread(target=_do, daemon=True).start()

    def _refresh_pulled_models(self):
        """Check which models are already pulled in Ollama."""
        def _do():
            from core.ai_cleaner import list_models
            models = list_models()
            self._pulled_models = models

            def _update():
                if models:
                    self.pulled_label.configure(
                        text=f"\u2705  {len(models)} model{'s' if len(models) != 1 else ''} installed:  "
                             + ", ".join(models[:8])
                             + ("..." if len(models) > 8 else ""),
                        text_color=COLORS["accent_green"],
                    )
                else:
                    self.pulled_label.configure(
                        text="\u26a0  No models pulled yet — pull at least one below",
                        text_color=COLORS["accent_orange"],
                    )
            self.after(0, _update)

        threading.Thread(target=_do, daemon=True).start()

    def _pull_model(self):
        """Pull (download) the selected model from Ollama."""
        # Use custom entry if filled, otherwise dropdown
        custom = self.custom_model_entry.get().strip()
        model_name = custom if custom else self.pull_model_menu.get()
        if not model_name:
            self.status.set_error("No model selected")
            return

        self.btn_pull.configure(state="disabled", text="\u23f3  Pulling...")
        self.status.set_working(f"Pulling {model_name}...")
        self.prog_pull.start_indeterminate(f"Downloading {model_name}\u2026")
        self._log(f"\n--- Pulling model: {model_name} ---\n")

        def _do():
            try:
                r = subprocess.run(
                    ["ollama", "pull", model_name],
                    capture_output=True, text=True, timeout=1800,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                out = (r.stdout or "") + (r.stderr or "")
                if len(out) > 2000:
                    out = out[:400] + "\n... (trimmed) ...\n" + out[-1000:]
                self.after(0, lambda: self._log(out))
                success = r.returncode == 0
            except subprocess.TimeoutExpired:
                self.after(0, lambda: self._log("\u23f1  Timed out (30 min limit)\n"))
                success = False
            except FileNotFoundError:
                self.after(0, lambda: self._log(
                    "\u274c  'ollama' command not found — install Ollama first\n"
                ))
                success = False
            except Exception as e:
                self.after(0, lambda: self._log(f"Error: {e}\n"))
                success = False

            def _finish():
                self.btn_pull.configure(state="normal", text="\u2b07  Pull Model")
                if success:
                    self.prog_pull.stop(f"{model_name} pulled \u2713")
                    self._log(f"\u2705  {model_name} ready!\n")
                    self.status.set_success(f"Model {model_name} pulled successfully!")
                    self._refresh_pulled_models()
                else:
                    self.prog_pull.set_progress(1.0, "Pull failed")
                    self.prog_pull.bar.configure(progress_color=COLORS["error"])
                    self.status.set_error(f"Failed to pull {model_name} — check log")
            self.after(0, _finish)

        threading.Thread(target=_do, daemon=True).start()

    # ==========================================================
    #  Toolkit Log Viewer
    # ==========================================================

    def _get_log_path(self):
        from core.logger import LOG_PATH
        return LOG_PATH

    def _load_toolkit_log(self):
        """Read the last ~200 lines of toolkit.log into the viewer."""
        path = self._get_log_path()
        try:
            if not os.path.exists(path):
                content = "(No log file yet -- it appears after the first app run.)"
            else:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                # Show last 200 lines
                tail = lines[-200:] if len(lines) > 200 else lines
                content = "".join(tail)
                if len(lines) > 200:
                    content = f"... ({len(lines) - 200} earlier lines hidden) ...\n\n" + content
        except Exception as e:
            content = f"Error reading log: {e}"

        self.tlog_text.configure(state="normal")
        self.tlog_text.delete("1.0", "end")
        self.tlog_text.insert("1.0", content)
        self.tlog_text.see("end")
        self.tlog_text.configure(state="disabled")

    def _open_log_file(self):
        """Open toolkit.log in the system default text editor."""
        path = self._get_log_path()
        if os.path.exists(path):
            os.startfile(path)
        else:
            self.status.set_error("No log file yet -- run the app first.")
