"""
Setup / GPU page -- System detection + numbered step-by-step installer.

Step 1: Core  (app basics -- scraping, OCR, GUI)
Step 2: PyTorch + CUDA  (GPU compute layer)
Step 3: Training stack  (Unsloth, PEFT, TRL, etc.)

Basic users only need Step 1.  Steps 2-3 are for LoRA fine-tuning.
"""

from __future__ import annotations
import os, platform, subprocess, sys, threading, re
import customtkinter as ctk

from gui.theme  import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, ActionButton, StatusBar, Tooltip


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
        self._heading(ollama_card, "\U0001f999  Ollama")

        self.ollama_label = ctk.CTkLabel(
            ollama_card, text="Checking...",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
            justify="left", wraplength=600,
        )
        self.ollama_label.pack(anchor="w", pady=(4, 0))

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
        else:
            self.ollama_label.configure(
                text="\u274c  Ollama not found -- install from https://ollama.com\n"
                     "    Needed for running and importing models.",
                text_color=COLORS["accent_orange"],
            )

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
        """Return (installed_set, missing_set) for a list of pip names."""
        ok, miss = set(), set()
        for pkg in pkgs:
            mod = self._IMPORT_ALIASES.get(
                pkg.lower(), pkg.replace("-", "_").lower(),
            )
            try:
                __import__(mod)
                ok.add(pkg)
            except ImportError:
                miss.add(pkg)
        return ok, miss

    def _probe_torch(self):
        """Check that torch is installed AND has CUDA."""
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    def _show_dep_status(self, core_ok, core_miss, torch_ok, train_ok, train_miss):
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
        if torch_ok:
            import torch
            self.lbl_step2.configure(
                text=f"\u2705  PyTorch {torch.__version__}  |  CUDA {torch.version.cuda}",
                text_color=COLORS["accent_green"],
            )
            self._step_states[2] = "done"
        else:
            try:
                import torch
                self.lbl_step2.configure(
                    text=f"\u26a0  PyTorch {torch.__version__} but NO CUDA",
                    text_color=COLORS["accent_orange"],
                )
            except ImportError:
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
            out = (r.stdout or "") + (r.stderr or "")
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

        def _do():
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
        names = {
            1: "\u2460  Install Core",
            2: "\u2461  Install PyTorch + CUDA",
            3: "\u2462  Install Training Stack",
        }
        btns[step].configure(state="normal", text=names[step])

        if ok:
            self._log(f"\n\u2705  Step {step} complete!\n")
            self.status.set_success(f"Step {step} installed successfully!")
        else:
            self._log(f"\n\u274c  Step {step} had errors -- scroll up for details.\n")
            self.status.set_error(f"Step {step} had errors -- check the log above")

        # Re-check everything
        self.after(500, self._check_deps)

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
