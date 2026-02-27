"""
Setup Page — GPU detection + one-click training dependency installer.

Detects the user's GPU, shows specs, and offers to install everything
needed for LoRA fine-tuning (torch+CUDA, unsloth, peft, trl, datasets).
If no NVIDIA GPU is detected, clearly explains that only context injection
is available.
"""
import os
import re
import subprocess
import threading
import platform

import customtkinter as ctk

from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import PageHeader, ActionButton, StatusBar, Tooltip


# ═══════════════════════════════════════════════════════════════════
#  GPU Detection (no torch dependency — works before install)
# ═══════════════════════════════════════════════════════════════════

def _detect_gpu_wmi():
    """Use Windows WMI to detect GPUs without needing torch installed."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "Select-Object Name, AdapterRAM, DriverVersion | "
             "ConvertTo-Json"],
            capture_output=True, text=True, timeout=15,
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
            # AdapterRAM from WMI is often capped at 4GB (32-bit overflow)
            # so we estimate from GPU name if possible
            vram_gb = _estimate_vram_from_name(name, vram_bytes)
            gpus.append({
                "name": name,
                "vram_gb": vram_gb,
                "driver": driver,
                "is_nvidia": "nvidia" in name.lower() or "geforce" in name.lower() or "rtx" in name.lower() or "gtx" in name.lower(),
            })
        return gpus
    except Exception:
        return []


def _detect_gpu_nvidia_smi():
    """Try nvidia-smi for more accurate VRAM info."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            return []
        gpus = []
        for line in r.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                name = parts[0]
                vram_mb = float(parts[1])
                driver = parts[2]
                gpus.append({
                    "name": name,
                    "vram_gb": round(vram_mb / 1024, 1),
                    "driver": driver,
                    "is_nvidia": True,
                })
        return gpus
    except Exception:
        return []


def _estimate_vram_from_name(name, wmi_bytes):
    """Estimate VRAM from GPU name since WMI caps at 4GB."""
    name_lower = name.lower()
    # Known VRAM sizes by card name
    known = {
        "5090": 32, "5080": 16, "5070 ti": 16, "5070": 12,
        "5060 ti": 16, "5060": 8,
        "4090": 24, "4080": 16, "4070 ti super": 16,
        "4070 ti": 12, "4070 super": 12, "4070": 12,
        "4060 ti": 16, "4060": 8,
        "3090 ti": 24, "3090": 24, "3080 ti": 12, "3080": 10,
        "3070 ti": 8, "3070": 8, "3060 ti": 8, "3060": 12,
        "a100": 80, "a6000": 48, "a5000": 24, "a4000": 16,
        "a40": 48, "l40": 48, "h100": 80,
    }
    for pattern, gb in known.items():
        if pattern in name_lower:
            return gb

    # Fall back to WMI value (often wrong for >4GB cards)
    if wmi_bytes and wmi_bytes > 0:
        gb = round(wmi_bytes / (1024 ** 3), 1)
        if gb > 0.5:
            return gb

    return 0


def _detect_gpu():
    """Best-effort GPU detection. Returns list of gpu dicts."""
    # Try nvidia-smi first (most accurate)
    gpus = _detect_gpu_nvidia_smi()
    if gpus:
        return gpus
    # Fall back to WMI
    return _detect_gpu_wmi()


# ═══════════════════════════════════════════════════════════════════
#  Dependency Definitions
# ═══════════════════════════════════════════════════════════════════

# Core app dependencies (always needed)
CORE_DEPS = [
    "customtkinter", "beautifulsoup4", "requests",
    "youtube-transcript-api", "pytesseract", "Pillow",
    "PyMuPDF", "trafilatura", "lxml", "pystray", "keyboard",
    "pyyaml", "windnd",
]

# Training dependencies (only needed for LoRA fine-tuning)
TRAINING_DEPS = [
    "torch", "unsloth", "peft", "transformers", "trl",
    "datasets", "accelerate", "bitsandbytes", "sentencepiece",
    "protobuf",
]

# The special pip command for torch with CUDA 12.4
TORCH_CUDA_INSTALL = (
    "pip install torch torchvision torchaudio "
    "--index-url https://download.pytorch.org/whl/cu124"
)

# Unsloth install (has its own requirements)
UNSLOTH_INSTALL = 'pip install "unsloth[cu124-torch250] @ git+https://github.com/unslothai/unsloth.git"'


# ═══════════════════════════════════════════════════════════════════
#  Setup Page
# ═══════════════════════════════════════════════════════════════════

class SetupPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self.gpus = []
        self._build_ui()
        # Auto-detect on load
        self.after(300, self._detect_system)

    # ── helpers ────────────────────────────────────────────

    def _card(self, parent):
        f = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        f.pack(fill="x", pady=(0, 12))
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

    # ══════════════════════════════════════════════════════
    #  Build UI
    # ══════════════════════════════════════════════════════

    def _build_ui(self):
        self.container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=15)
        c = self.container

        PageHeader(
            c, icon="🖥️", title="System Setup",
            subtitle="GPU detection + one-click training dependency installer",
        ).pack(fill="x", pady=(0, 12))

        # ─ System Info ─────────────────────────────────────
        sys_card = self._card(c)
        self._heading(sys_card, "💻  System Info")

        self.sys_label = ctk.CTkLabel(
            sys_card, text="Detecting...",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
            justify="left", wraplength=600,
        )
        self.sys_label.pack(anchor="w", pady=(4, 0))

        # ─ GPU Card ────────────────────────────────────────
        gpu_card = self._card(c)
        self._heading(gpu_card, "🎮  GPU Detection")
        self._hint(gpu_card,
            "LoRA fine-tuning requires an NVIDIA GPU with CUDA support. "
            "We detect your hardware automatically."
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

        rescan_btn = ActionButton(
            gpu_card, text="🔄  Re-scan GPU", command=self._detect_system,
            style="secondary", width=150,
        )
        rescan_btn.pack(anchor="w", pady=(8, 0))

        # ─ Dependency Status ───────────────────────────────
        dep_card = self._card(c)
        self._heading(dep_card, "📦  Dependencies")
        self._hint(dep_card,
            "Core dependencies are needed to run the app. "
            "Training dependencies are only needed for LoRA fine-tuning."
        )

        self.dep_text = ctk.CTkTextbox(
            dep_card, height=220,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_secondary"],
            corner_radius=8,
        )
        self.dep_text.pack(fill="x", pady=(4, 0))

        dep_btn_row = ctk.CTkFrame(dep_card, fg_color="transparent")
        dep_btn_row.pack(fill="x", pady=(8, 0))

        check_btn = ActionButton(
            dep_btn_row, text="🔍  Check All",
            command=self._check_deps, style="secondary", width=140,
        )
        check_btn.pack(side="left", padx=(0, 8))
        Tooltip(check_btn, "Check which packages are installed\nand which are missing.")

        self.install_core_btn = ActionButton(
            dep_btn_row, text="📥  Install Core",
            command=self._install_core, style="primary", width=150,
        )
        self.install_core_btn.pack(side="left", padx=(0, 8))
        Tooltip(self.install_core_btn,
                "Install all core app dependencies.\n"
                "pip install customtkinter, trafilatura, etc.")

        self.install_training_btn = ActionButton(
            dep_btn_row, text="🧬  Install Training",
            command=self._install_training, style="success", width=180,
        )
        self.install_training_btn.pack(side="left")
        Tooltip(self.install_training_btn,
                "Install everything for LoRA fine-tuning:\n"
                "• PyTorch with CUDA 12.4\n"
                "• Unsloth (fast LoRA)\n"
                "• Transformers, PEFT, TRL, Datasets\n\n"
                "⚠ Requires NVIDIA GPU. ~5 GB download.")

        # ─ VRAM Guide ──────────────────────────────────────
        guide_card = self._card(c)
        self._heading(guide_card, "📊  What Can You Train?")

        guide_text = (
            "VRAM          Model Size        Examples\n"
            "─────────────────────────────────────────────────\n"
            " 4 GB         1B-3B             Phi-3 Mini, Qwen2.5-3B\n"
            " 6 GB         3B-4B             Llama 3.2-3B, Qwen3-4B\n"
            " 8 GB         7B-8B             Mistral-7B, Llama 3.1-8B\n"
            "12 GB         9B-14B            Gemma-3-12B, Qwen3-14B\n"
            "16 GB         14B-27B           Qwen3-14B, Gemma-3-27B  ← your 5080!\n"
            "24 GB         30B-32B           Qwen2.5-32B, Qwen3-30B-A3B\n"
            "48 GB         70B               Llama 3.1-70B (tight)\n\n"
            "All sizes assume 4-bit QLoRA with gradient checkpointing.\n"
            "Batch size 2-4 for tighter VRAM. Reduce max_seq_len if OOM."
        )

        ctk.CTkLabel(
            guide_card, text=guide_text,
            font=("Consolas", FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
            justify="left",
        ).pack(anchor="w")

        # ─ Ollama Check ───────────────────────────────────
        ollama_card = self._card(c)
        self._heading(ollama_card, "🦙  Ollama")

        self.ollama_label = ctk.CTkLabel(
            ollama_card, text="Checking...",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"],
            justify="left", wraplength=600,
        )
        self.ollama_label.pack(anchor="w", pady=(4, 0))

        # ─ Status ──────────────────────────────────────────
        self.status = StatusBar(c)
        self.status.pack(fill="x", pady=(5, 0))

    # ══════════════════════════════════════════════════════
    #  System Detection
    # ══════════════════════════════════════════════════════

    def _detect_system(self):
        self.status.set_working("Detecting system hardware...")

        def _do():
            # System info
            py_ver = platform.python_version()
            os_name = platform.platform()
            cpu = platform.processor() or "Unknown CPU"

            sys_text = (
                f"Python:  {py_ver}\n"
                f"OS:      {os_name}\n"
                f"CPU:     {cpu}"
            )

            # GPU
            gpus = _detect_gpu()

            # Ollama
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

        # System info
        self.sys_label.configure(text=sys_text)

        # GPU
        if not gpus:
            self.gpu_label.configure(
                text="No GPUs detected (or detection failed).",
                text_color=COLORS["text_muted"],
            )
            self.gpu_verdict.configure(
                text="❌  No NVIDIA GPU — only Context Injection available (no real training)",
                text_color=COLORS["error"],
            )
        else:
            lines = []
            has_nvidia = False
            best_vram = 0
            for g in gpus:
                vram_str = f"{g['vram_gb']} GB" if g['vram_gb'] else "? GB"
                nvidia_tag = "  ✅ NVIDIA" if g['is_nvidia'] else "  ⚠ Not NVIDIA"
                lines.append(f"• {g['name']}  —  {vram_str}  (Driver: {g['driver']}){nvidia_tag}")
                if g['is_nvidia']:
                    has_nvidia = True
                    best_vram = max(best_vram, g['vram_gb'])

            self.gpu_label.configure(
                text="\n".join(lines),
                text_color=COLORS["text_primary"],
            )

            if has_nvidia:
                if best_vram >= 8:
                    self.gpu_verdict.configure(
                        text=f"🔥  {best_vram} GB VRAM — you can train LoRA models!",
                        text_color=COLORS["accent_green"],
                    )
                elif best_vram >= 4:
                    self.gpu_verdict.configure(
                        text=f"👍  {best_vram} GB VRAM — can train small models (1B-3B)",
                        text_color=COLORS["accent_yellow"],
                    )
                else:
                    self.gpu_verdict.configure(
                        text=f"⚠  {best_vram} GB VRAM — very tight, may struggle with training",
                        text_color=COLORS["accent_orange"],
                    )
            else:
                self.gpu_verdict.configure(
                    text="❌  No NVIDIA GPU found — LoRA training needs CUDA. Context Injection still works.",
                    text_color=COLORS["error"],
                )

        # Ollama
        if ollama_ver:
            self.ollama_label.configure(
                text=f"✅  Ollama installed: {ollama_ver}",
                text_color=COLORS["accent_green"],
            )
        else:
            self.ollama_label.configure(
                text="❌  Ollama not found — install from https://ollama.com\n"
                     "    Needed for running models locally and for final import after training.",
                text_color=COLORS["accent_orange"],
            )

        self.status.set_success("System detection complete")
        # Auto-check deps too
        self._check_deps()

    # ══════════════════════════════════════════════════════
    #  Dependency Checking
    # ══════════════════════════════════════════════════════

    def _check_deps(self):
        self.status.set_working("Checking installed packages...")

        def _do():
            results = []

            # Core deps
            results.append(("═══ CORE (app) ═══", None, ""))
            for pkg in CORE_DEPS:
                # Import name might differ from pip name
                import_name = pkg.replace("-", "_").lower()
                aliases = {
                    "pillow": "PIL",
                    "pymupdf": "fitz",
                    "beautifulsoup4": "bs4",
                    "youtube_transcript_api": "youtube_transcript_api",
                    "pyyaml": "yaml",
                }
                mod = aliases.get(import_name, import_name)
                try:
                    m = __import__(mod)
                    ver = getattr(m, "__version__", "✓")
                    results.append((pkg, True, ver))
                except ImportError:
                    results.append((pkg, False, "not installed"))

            # Training deps
            results.append(("", None, ""))
            results.append(("═══ TRAINING (LoRA) ═══", None, ""))

            for pkg in TRAINING_DEPS:
                import_name = pkg.replace("-", "_").lower()
                try:
                    m = __import__(import_name)
                    ver = getattr(m, "__version__", "✓")

                    # Extra info for torch
                    if pkg == "torch":
                        import torch
                        cuda_avail = torch.cuda.is_available()
                        cuda_ver = torch.version.cuda if cuda_avail else "N/A"
                        ver = f"{ver}  (CUDA: {cuda_ver}, GPU: {'✅' if cuda_avail else '❌'})"

                    results.append((pkg, True, ver))
                except ImportError:
                    results.append((pkg, False, "not installed"))

            self.after(0, lambda: self._show_dep_results(results))

        threading.Thread(target=_do, daemon=True).start()

    def _show_dep_results(self, results):
        self.dep_text.configure(state="normal")
        self.dep_text.delete("1.0", "end")

        missing_core = 0
        missing_training = 0
        section = "core"

        for name, ok, info in results:
            if ok is None:
                self.dep_text.insert("end", f"\n{name}\n")
                if "TRAINING" in name:
                    section = "training"
                continue

            icon = "✅" if ok else "❌"
            self.dep_text.insert("end", f"  {icon}  {name:24s}  {info}\n")
            if not ok:
                if section == "core":
                    missing_core += 1
                else:
                    missing_training += 1

        # Summary
        self.dep_text.insert("end", "\n" + "─" * 50 + "\n")
        if missing_core == 0 and missing_training == 0:
            self.dep_text.insert("end", "🎉  Everything installed! Ready to train.\n")
            self.status.set_success("All dependencies installed")
        elif missing_core == 0:
            self.dep_text.insert(
                "end",
                f"✅  Core OK  |  ❌  {missing_training} training package(s) missing\n"
                f"Click 'Install Training' to set up LoRA fine-tuning.\n"
            )
            self.status.set_success(f"Core OK — {missing_training} training deps missing")
        else:
            self.dep_text.insert(
                "end",
                f"❌  {missing_core} core + {missing_training} training package(s) missing\n"
                f"Click 'Install Core' first, then 'Install Training'.\n"
            )
            self.status.set_error(f"{missing_core + missing_training} packages missing")

        self.dep_text.configure(state="disabled")

    # ══════════════════════════════════════════════════════
    #  Installers
    # ══════════════════════════════════════════════════════

    def _install_core(self):
        """Install core app dependencies in a background thread."""
        self.status.set_working("Installing core dependencies...")
        self.install_core_btn.configure(state="disabled", text="⏳  Installing...")

        def _do():
            try:
                cmd = ["pip", "install"] + CORE_DEPS
                r = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                ok = r.returncode == 0
                out = r.stdout + "\n" + r.stderr
                self.after(0, lambda: self._install_done("Core", ok, out))
            except Exception as e:
                self.after(0, lambda: self._install_done("Core", False, str(e)))

        threading.Thread(target=_do, daemon=True).start()

    def _install_training(self):
        """Install training dependencies (torch+CUDA, unsloth, etc)."""
        # Check if they have a GPU first
        nvidia_gpus = [g for g in self.gpus if g.get("is_nvidia")]
        if not nvidia_gpus:
            self.status.set_error(
                "No NVIDIA GPU detected — training deps need CUDA. "
                "Install anyway by running the commands manually."
            )
            self.dep_text.configure(state="normal")
            self.dep_text.insert("end",
                f"\n\n# Manual install (if you know you have a GPU):\n"
                f"# 1. {TORCH_CUDA_INSTALL}\n"
                f"# 2. {UNSLOTH_INSTALL}\n"
                f"# 3. pip install peft transformers trl datasets accelerate "
                f"bitsandbytes sentencepiece protobuf\n"
            )
            self.dep_text.configure(state="disabled")
            return

        self.status.set_working("Installing training dependencies (this takes a few minutes)...")
        self.install_training_btn.configure(state="disabled", text="⏳  Installing...")

        def _do():
            steps = []

            # Step 1: PyTorch with CUDA
            self.after(0, lambda: self.status.set_working(
                "Step 1/3: Installing PyTorch with CUDA 12.4..."
            ))
            r1 = subprocess.run(
                TORCH_CUDA_INSTALL, shell=True,
                capture_output=True, text=True, timeout=600,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            steps.append(("PyTorch+CUDA", r1.returncode == 0, r1.stderr[-500:] if r1.stderr else ""))

            if r1.returncode != 0:
                self.after(0, lambda: self._install_done("Training", False,
                    "PyTorch+CUDA install failed. Check your internet connection.\n" + r1.stderr[-1000:]))
                return

            # Step 2: Unsloth
            self.after(0, lambda: self.status.set_working(
                "Step 2/3: Installing Unsloth..."
            ))
            r2 = subprocess.run(
                UNSLOTH_INSTALL, shell=True,
                capture_output=True, text=True, timeout=600,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            steps.append(("Unsloth", r2.returncode == 0, r2.stderr[-500:] if r2.stderr else ""))

            # Step 3: Remaining packages
            self.after(0, lambda: self.status.set_working(
                "Step 3/3: Installing remaining packages..."
            ))
            remaining = ["peft", "transformers", "trl", "datasets",
                         "accelerate", "bitsandbytes", "sentencepiece", "protobuf"]
            r3 = subprocess.run(
                ["pip", "install"] + remaining,
                capture_output=True, text=True, timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            steps.append(("Other packages", r3.returncode == 0, r3.stderr[-500:] if r3.stderr else ""))

            all_ok = all(ok for _, ok, _ in steps)
            summary = "\n".join(
                f"{'✅' if ok else '❌'}  {name}: {'OK' if ok else err[:200]}"
                for name, ok, err in steps
            )
            self.after(0, lambda: self._install_done("Training", all_ok, summary))

        threading.Thread(target=_do, daemon=True).start()

    def _install_done(self, category, ok, output):
        if category == "Core":
            self.install_core_btn.configure(state="normal", text="📥  Install Core")
        else:
            self.install_training_btn.configure(state="normal", text="🧬  Install Training")

        if ok:
            self.status.set_success(f"{category} dependencies installed!")
        else:
            self.status.set_error(f"{category} install had errors — check output")

        self.dep_text.configure(state="normal")
        self.dep_text.insert("end", f"\n\n{'═' * 50}\n# {category} Install Result\n{'═' * 50}\n{output}\n")
        self.dep_text.configure(state="disabled")

        # Re-check everything
        self.after(500, self._check_deps)
