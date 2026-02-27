"""
Training Page — Real LoRA fine-tuning + honest context injection.

Unified flow:
  1. Pick your Ollama model (auto-scanned)
  2. Auto-resolve HuggingFace source weights for training
  3. Choose method: LoRA Training (real) vs Context Injection (quick hack)
  4. Configure, generate, launch
"""
import os
import re
import json
import subprocess
import shutil
import sys
import threading

import customtkinter as ctk

from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import (
    PageHeader, InputField, ActionButton, StatusBar, Tooltip, ContentPreview,
    ProgressIndicator, PlaceholderEntry,
)
from core.database import get_all_entries, get_stats
from config import EXPORTS_DIR, DATA_DIR


# ═══════════════════════════════════════════════════════════════════
#  Ollama → HuggingFace Model Resolution
# ═══════════════════════════════════════════════════════════════════

# ── Family Mapping ─────────────────────────────────────────────
# (family_keyword, hf_pattern, unsloth_4bit_pattern)
# Ordered MOST SPECIFIC → LEAST SPECIFIC (first match wins).
# {sz} is replaced with the detected size like "14B".

_FAMILY_MAP = [
    ("qwen3-coder",       "Qwen/Qwen3-Coder-{sz}",                            "unsloth/Qwen3-{sz}-bnb-4bit"),
    ("qwen3-vl",          "Qwen/Qwen3-VL-{sz}",                               None),
    ("qwen3",             "Qwen/Qwen3-{sz}",                                   "unsloth/Qwen3-{sz}-bnb-4bit"),
    ("qwen2.5-coder",     "Qwen/Qwen2.5-Coder-{sz}-Instruct",                 "unsloth/Qwen2.5-Coder-{sz}-Instruct-bnb-4bit"),
    ("qwen2.5-vl",        "Qwen/Qwen2.5-VL-{sz}-Instruct",                    None),
    ("qwen2.5",           "Qwen/Qwen2.5-{sz}-Instruct",                        "unsloth/Qwen2.5-{sz}-bnb-4bit"),
    ("deepseek-coder-v2", "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",       None),
    ("deepseek-coder",    "deepseek-ai/deepseek-coder-{sz}-instruct-v1.5",     None),
    ("deepseek-r1",       "deepseek-ai/DeepSeek-R1-Distill-Qwen-{sz}",         None),
    ("dolphin-mixtral",   "mistralai/Mixtral-8x7B-Instruct-v0.1",              None),
    ("dolphin-llama3",    "meta-llama/Llama-3-{sz}-Instruct",                   "unsloth/llama-3-{sz}-bnb-4bit"),
    ("llama3.2",          "meta-llama/Llama-3.2-{sz}-Instruct",                 "unsloth/Llama-3.2-{sz}-Instruct-bnb-4bit"),
    ("llama3.1",          "meta-llama/Llama-3.1-{sz}-Instruct",                 "unsloth/Meta-Llama-3.1-{sz}-bnb-4bit"),
    ("llama3",            "meta-llama/Llama-3-{sz}-Instruct",                   "unsloth/llama-3-{sz}-bnb-4bit"),
    ("gemma3",            "google/gemma-3-{sz}-it",                             "unsloth/gemma-3-{sz}-it-bnb-4bit"),
    ("gemma-3",           "google/gemma-3-{sz}-it",                             "unsloth/gemma-3-{sz}-it-bnb-4bit"),
    ("gemma",             "google/gemma-2-{sz}-it",                             "unsloth/gemma-2-{sz}-it-bnb-4bit"),
    ("mixtral",           "mistralai/Mixtral-{sz}-Instruct-v0.1",               None),
    ("mistral",           "mistralai/Mistral-{sz}-Instruct-v0.3",              "unsloth/mistral-{sz}-v0.3-bnb-4bit"),
    ("phi-4",             "microsoft/phi-4",                                    "unsloth/Phi-4-bnb-4bit"),
    ("phi",               "microsoft/Phi-3-mini-4k-instruct",                   "unsloth/Phi-3-mini-4k-instruct-bnb-4bit"),
]

# ── Abliterated / Uncensored HF Repos ─────────────────────────
# When the Ollama model has -abliterated or -uncensored in its name,
# we try to find the matching abliterated HF repo for training so
# the fine-tune doesn't re-introduce censorship.  (family → HF repo pattern)

_ABLITERATED_MAP = {
    "qwen3":          "huihui-ai/Qwen3-{sz}-abliterated",
    "qwen3-vl":       "huihui-ai/Qwen3-VL-{sz}-Instruct-abliterated",
    "qwen2.5":        "huihui-ai/Qwen2.5-{sz}-Instruct-abliterated",
    "qwen2.5-coder":  "huihui-ai/Qwen2.5-Coder-{sz}-Instruct-abliterated",
    "qwen2.5-vl":     "huihui-ai/Qwen2.5-VL-{sz}-Instruct-abliterated",
    "llama3.1":       "huihui-ai/Llama-3.1-{sz}-Instruct-abliterated",
    "llama3":         "huihui-ai/Llama-3-{sz}-Instruct-abliterated",
    "gemma3":         "huihui-ai/gemma-3-{sz}-it-abliterated",
    "gemma-3":        "huihui-ai/gemma-3-{sz}-it-abliterated",
    "gemma":          "huihui-ai/gemma-2-{sz}-it-abliterated",
    "mistral":        "huihui-ai/Mistral-{sz}-Instruct-v0.3-abliterated",
    "phi-4":          "huihui-ai/phi-4-abliterated",
    "deepseek-r1":    "huihui-ai/DeepSeek-R1-Distill-Qwen-{sz}-abliterated",
}

_UNCENSORED_MAP = {
    "llama3":     "Orenguteng/Llama-3-{sz}-Lexi-Uncensored",
    "dolphin-mixtral": "cognitivecomputations/dolphin-2.7-mixtral-8x7b",
}

# VRAM estimates for 4-bit QLoRA training (model + adapter + optimizer)
_VRAM_GUIDE = {
    1: "~4 GB", 2: "~4 GB", 3: "~5 GB", 4: "~5 GB",
    7: "~8 GB", 8: "~8 GB", 9: "~10 GB", 14: "~12 GB",
    27: "~20 GB", 30: "~22 GB", 32: "~24 GB", 70: "~48 GB",
}


def _get_ollama_models():
    """Run ``ollama list`` and return [(name, size_str), ...]."""
    try:
        r = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            return []
        models = []
        for line in r.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if parts:
                name = parts[0]
                size = (parts[2] + " " + parts[3]) if len(parts) >= 4 else ""
                models.append((name, size))
        return models
    except Exception:
        return []


def _resolve_hf_model(ollama_name: str):
    """
    Map an Ollama model name to HuggingFace IDs for LoRA training.

    When the source model is abliterated/uncensored, we prefer the matching
    abliterated HF repo so training doesn't re-introduce censorship.

    Returns ``(hf_id, unsloth_id, family, size, vram, is_abliterated, note)``.
    ``hf_id`` / ``unsloth_id`` may be *None* if resolution fails.
    """
    name = ollama_name.strip()
    # Ollama names can be org/model:tag — grab the model:tag part
    short = name.split("/")[-1] if "/" in name else name
    full_lower = name.lower().replace("_", "-")
    short_lower = short.lower()

    # Split name:tag
    if ":" in short_lower:
        base, tag = short_lower.rsplit(":", 1)
    else:
        base, tag = short_lower, "latest"

    # ── detect abliterated / uncensored ────────────────────
    is_abliterated = any(kw in full_lower for kw in
                         ("abliterated", "uncensored", "lexi-uncensored"))

    # ── extract size ───────────────────────────────────────
    sz_re = r"(\d+(?:x\d+)?(?:\.\d+)?b(?:-a\d+b)?)"
    m = re.match(sz_re, tag)
    if not m:
        m = re.search(sz_re, base)
    raw = m.group(1) if m else ""
    size = raw.upper().replace("X", "x") if raw else ""

    # ── estimate VRAM ──────────────────────────────────────
    try:
        num = int(re.match(r"(\d+)", size).group(1)) if size else 0
    except Exception:
        num = 0
    vram = _VRAM_GUIDE.get(num, f"~{max(4, num)}+ GB" if num else "unknown")

    # ── clean base for family matching ─────────────────────
    clean = base.replace("_", "-")
    for sfx in ("-abliterated", "-uncensored", "-lexi-uncensored", "-lexi",
                "-instruct", "-chat", "-it", "-unsloth"):
        clean = clean.replace(sfx, "")
    if raw:
        clean = clean.replace(raw, "").replace("--", "-").strip("-")
    clean = clean.strip("-")

    # ── match family ───────────────────────────────────────
    for fam, hf_pat, us_pat in _FAMILY_MAP:
        if fam not in clean:
            continue

        is_vl = "-vl" in clean or "vl-" in clean

        if hf_pat is None:
            return (None, None, fam, size, vram, is_abliterated,
                    f"⚠ '{fam}' detected — no standard HF mapping. Enter ID manually.")

        if "{sz}" in hf_pat and not size:
            return (None, None, fam, "", vram, is_abliterated,
                    f"Detected '{fam}' but size unknown. Enter HF model ID manually.")

        # ── resolve IDs ────────────────────────────────────
        hf_id = hf_pat.replace("{sz}", size)
        us_id = us_pat.replace("{sz}", size) if (us_pat and size) else None

        # ── prefer abliterated HF repo when source is abliterated ──
        abl_id = None
        if is_abliterated:
            abl_pat = _ABLITERATED_MAP.get(fam)
            if not abl_pat:
                abl_pat = _UNCENSORED_MAP.get(fam)
            if abl_pat:
                abl_id = abl_pat.replace("{sz}", size) if "{sz}" in abl_pat else abl_pat

        # Build user-facing note
        note_parts = []
        if abl_id:
            note_parts.append(f"✅  {fam.upper()} {size} (ABLITERATED)")
            note_parts.append(f"    Training on:  {abl_id}")
            note_parts.append(f"    Base (fallback):  {hf_id}")
        else:
            note_parts.append(f"✅  {fam.upper()} {size}  →  {hf_id}")
            if is_abliterated:
                note_parts.append(
                    "⚠  No abliterated HF repo found for this family — "
                    "using base weights. The fine-tune may re-add some filters."
                )

        if us_id:
            note_parts.append(f"    Unsloth 4-bit:  {us_id}")
        if is_vl:
            note_parts.append(
                "⚠  Vision-Language model — text-only LoRA may have limited effect."
            )

        # If abliterated repo found, use it as the primary HF ID
        final_hf = abl_id if abl_id else hf_id

        return (final_hf, us_id, fam, size, vram, is_abliterated,
                "\n".join(note_parts))

    return (None, None, "unknown", size, vram, is_abliterated,
            "⚠ Could not identify model family. Enter a HuggingFace model ID manually.")


# ═══════════════════════════════════════════════════════════════════
#  Training Page
# ═══════════════════════════════════════════════════════════════════

class TrainingPage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self.ollama_models = []        # [(name, size_str), ...]
        self.resolved_hf = None        # auto-detected HF model
        self.resolved_unsloth = None   # auto-detected Unsloth 4-bit model
        self._build_ui()

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

    def _make_param(self, parent, label_text, var, tooltip_text):
        """Labelled parameter entry with tooltips on BOTH label + entry."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(side="left", padx=(0, 15))

        lbl = ctk.CTkLabel(
            frame, text=label_text,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        lbl.pack(anchor="w")

        entry = ctk.CTkEntry(
            frame, textvariable=var,
            width=85, height=30,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=6,
        )
        entry.pack(anchor="w", pady=(2, 0))

        Tooltip(lbl, tooltip_text)
        Tooltip(entry, tooltip_text)

    # ══════════════════════════════════════════════════════
    #  Build UI
    # ══════════════════════════════════════════════════════

    def _build_ui(self):
        self.container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=15)
        c = self.container

        # ─ Header ──────────────────────────────────────────
        PageHeader(
            c, icon="🧬", title="Training Launcher",
            subtitle="Pick your model → configure → train with real LoRA or inject context",
        ).pack(fill="x", pady=(0, 12))

        # ─ Data Summary ───────────────────────────────────
        data_card = self._card(c)
        self._heading(data_card, "📊  Your Data")

        stats = get_stats()
        entries = stats.get("total_entries", 0)
        words = stats.get("total_words", 0)
        tokens = int(words * 1.3)

        if words < 5_000:
            quality = "⚠ Very small — aim for 10 000+ words for decent results"
        elif words < 50_000:
            quality = "👍 Decent — good for focused fine-tuning"
        else:
            quality = "🔥 Large dataset — excellent for training"

        ctk.CTkLabel(
            data_card,
            text=f"Entries: {entries:,}  ·  Words: {words:,}  ·  ~{tokens:,} tokens\n{quality}",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_secondary"], justify="left",
        ).pack(anchor="w", pady=(4, 0))

        # ─ Model Selection ─────────────────────────────────
        model_outer = ctk.CTkFrame(c, fg_color=COLORS["bg_card"], corner_radius=10)
        model_outer.pack(fill="x", pady=(0, 12))
        model_card = ctk.CTkFrame(model_outer, fg_color="transparent")
        model_card.pack(fill="x", padx=15, pady=10)

        self._heading(model_card, "🦙  Select Your Ollama Model")
        self._hint(model_card,
            "Pick the model you want to train. We auto-detect the original "
            "HuggingFace weights needed for real LoRA fine-tuning."
        )

        # Scan row
        scan_row = ctk.CTkFrame(model_card, fg_color="transparent")
        scan_row.pack(fill="x", pady=(0, 6))

        self.ollama_menu = ctk.CTkOptionMenu(
            scan_row,
            values=["(scanning…)"],
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=440, height=35,
            command=self._on_model_selected,
        )
        self.ollama_menu.pack(side="left")

        scan_btn = ActionButton(
            scan_row, text="🔍 Scan", command=self._scan_ollama,
            style="secondary", width=90,
        )
        scan_btn.pack(side="left", padx=(8, 0))
        Tooltip(scan_btn, "Runs 'ollama list' to detect all\nlocally installed models.")

        # Resolved HF model display
        self.resolve_label = ctk.CTkLabel(
            model_card, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["accent_green"], justify="left",
            wraplength=600,
        )
        self.resolve_label.pack(anchor="w", pady=(4, 0))

        self.vram_label = ctk.CTkLabel(
            model_card, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        self.vram_label.pack(anchor="w")

        # Manual HF override (hidden by default)
        self.override_frame = ctk.CTkFrame(model_card, fg_color="transparent")

        ctk.CTkLabel(
            self.override_frame,
            text="Override HF model (leave blank to use auto-detected):",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w")

        self.hf_override = PlaceholderEntry(
            self.override_frame,
            hint_text="e.g. Qwen/Qwen3-14B  or  unsloth/Qwen3-14B-bnb-4bit",
            width=500, height=32,
        )
        self.hf_override.pack(anchor="w", pady=(2, 0))
        Tooltip(self.hf_override,
                "Enter a HuggingFace model ID to override auto-detection.\n"
                "Use unsloth/* models for faster 4-bit loading.\n"
                "Leave blank to use the auto-detected model.")

        self.show_override_var = ctk.BooleanVar(value=False)
        self.override_toggle = ctk.CTkCheckBox(
            model_card, text="Show manual HF override",
            variable=self.show_override_var,
            command=self._toggle_override,
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            checkbox_width=18, checkbox_height=18,
        )
        self.override_toggle.pack(anchor="w", pady=(4, 0))

        # Auto-scan on load
        self.after(500, self._scan_ollama)

        # ─ Training Method ─────────────────────────────────
        self.method_card_outer = ctk.CTkFrame(
            c, fg_color=COLORS["bg_card"], corner_radius=10,
        )
        self.method_card_outer.pack(fill="x", pady=(0, 12))
        method_card = ctk.CTkFrame(self.method_card_outer, fg_color="transparent")
        method_card.pack(fill="x", padx=15, pady=10)

        self._heading(method_card, "🔀  Training Method")

        self.method_var = ctk.StringVar(value="lora")
        m_row = ctk.CTkFrame(method_card, fg_color="transparent")
        m_row.pack(fill="x", pady=(4, 0))

        rb_lora = ctk.CTkRadioButton(
            m_row,
            text="🧬  LoRA Fine-Tuning  —  real training, modifies weights  (NVIDIA GPU required)",
            variable=self.method_var, value="lora",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_primary"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._on_method_change,
        )
        rb_lora.pack(anchor="w", pady=(0, 4))
        Tooltip(rb_lora,
                "Downloads the original HF weights, applies LoRA adapters,\n"
                "trains on your data, merges, converts to GGUF, imports to Ollama.\n"
                "The model actually LEARNS from your data.\n\n"
                "Requires: NVIDIA GPU with CUDA + unsloth + torch")

        rb_inject = ctk.CTkRadioButton(
            m_row,
            text="💉  Context Injection  —  instant, no GPU  (NOT real training)",
            variable=self.method_var, value="inject",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent_dim"],
            hover_color=COLORS["accent_hover"],
            command=self._on_method_change,
        )
        rb_inject.pack(anchor="w")
        Tooltip(rb_inject,
                "Pastes your data into the system prompt via a Modelfile.\n"
                "The model does NOT learn anything new — it just gets a\n"
                "bigger prompt with your data included.\n\n"
                "Quick hack, works instantly, but limited by context window.\n"
                "Only useful for small amounts of reference data.")

        self.method_warning = ctk.CTkLabel(
            method_card, text="",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["accent_orange"],
            wraplength=600, justify="left",
        )
        self.method_warning.pack(anchor="w", pady=(4, 0))

        # ─ LoRA Configuration (visible only in LoRA mode) ─
        self.lora_frame = ctk.CTkFrame(
            c, fg_color=COLORS["bg_card"], corner_radius=10,
        )
        # Packed dynamically by _on_method_change()

        lora_inner = ctk.CTkFrame(self.lora_frame, fg_color="transparent")
        lora_inner.pack(fill="x", padx=15, pady=10)

        self._heading(lora_inner, "⚙  LoRA Configuration")
        self._hint(lora_inner, "Pick a preset or customize individual values. Hover any field for details.")

        # ── Preset Buttons ──────────────────────────────
        preset_row = ctk.CTkFrame(lora_inner, fg_color="transparent")
        preset_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            preset_row, text="Presets:",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_muted"],
        ).pack(side="left", padx=(0, 8))

        self._presets = {
            "⚡ Quick":    {"rank": "8",  "alpha": "16",  "epochs": "1", "batch": "8",  "lr": "2e-4",  "seq": "1024"},
            "⚖ Balanced": {"rank": "16", "alpha": "32",  "epochs": "3", "batch": "4",  "lr": "2e-4",  "seq": "2048"},
            "🎯 Quality": {"rank": "32", "alpha": "64",  "epochs": "5", "batch": "2",  "lr": "1e-4",  "seq": "2048"},
            "🔬 Max":     {"rank": "64", "alpha": "128", "epochs": "8", "batch": "1",  "lr": "5e-5",  "seq": "4096"},
        }

        self._preset_btns = {}
        for label, vals in self._presets.items():
            btn = ctk.CTkButton(
                preset_row, text=label, width=100, height=30,
                font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
                fg_color=COLORS["bg_input"],
                hover_color=COLORS["bg_hover"],
                border_color=COLORS["border"],
                border_width=1, corner_radius=6,
                command=lambda v=vals, l=label: self._apply_preset(v, l),
            )
            btn.pack(side="left", padx=(0, 6))
            self._preset_btns[label] = btn

        # Tooltip descriptions for presets
        tips = [
            ("⚡ Quick",    "Fast test run.\nr=8  α=16  1 epoch  batch=8\nBest for: checking if training works"),
            ("⚖ Balanced", "Good default.\nr=16  α=32  3 epochs  batch=4\nBest for: most fine-tuning tasks"),
            ("🎯 Quality", "Higher quality, slower.\nr=32  α=64  5 epochs  batch=2\nBest for: important models, 16+ GB VRAM"),
            ("🔬 Max",     "Maximum capacity.\nr=64  α=128  8 epochs  batch=1\nBest for: large datasets, 24+ GB VRAM"),
        ]
        for lbl, tip in tips:
            Tooltip(self._preset_btns[lbl], tip)

        params_row = ctk.CTkFrame(lora_inner, fg_color="transparent")
        params_row.pack(fill="x")

        self.rank_var = ctk.StringVar(value="16")
        self._make_param(params_row, "Rank (r)", self.rank_var,
                         "LoRA rank — higher = more capacity but slower.\n"
                         "8 for small datasets, 16 for medium, 32 for large.")

        self.alpha_var = ctk.StringVar(value="32")
        self._make_param(params_row, "Alpha", self.alpha_var,
                         "LoRA alpha — typically 2× the rank.\n"
                         "Controls learning rate scaling for the adapter.")

        self.epochs_var = ctk.StringVar(value="3")
        self._make_param(params_row, "Epochs", self.epochs_var,
                         "How many times to loop through the entire dataset.\n"
                         "1-3 for large datasets, 3-10 for small.\n"
                         "Too many = overfitting.")

        self.batch_var = ctk.StringVar(value="4")
        self._make_param(params_row, "Batch Size", self.batch_var,
                         "Samples per training step.\n"
                         "2-4 for 8 GB VRAM, 8-16 for 24 GB.\n"
                         "Smaller = less VRAM but slower.")

        self.lr_var = ctk.StringVar(value="2e-4")
        self._make_param(params_row, "Learning Rate", self.lr_var,
                         "Step size for weight updates.\n"
                         "2e-4 is standard for LoRA.\n"
                         "Lower (1e-4) = slower but more precise.\n"
                         "Higher (5e-4) = faster but may overshoot.")

        self.seq_var = ctk.StringVar(value="2048")
        self._make_param(params_row, "Max Seq Len", self.seq_var,
                         "Max token length per sample.\n"
                         "2048 standard, 4096 for longer docs.\n"
                         "Higher = more VRAM needed.")

        # ─ Output Config ───────────────────────────────────
        out_card = self._card(c)
        self._heading(out_card, "📦  Output")

        self.model_name_field = InputField(
            out_card, label_text="Model Name (for Ollama)",
            placeholder="e.g. my-finetuned-model",
        )
        self.model_name_field.pack(fill="x", pady=(6, 0))
        self.model_name_field.set("my-finetuned-model")
        Tooltip(self.model_name_field,
                "Name used for 'ollama run <name>'.\n"
                "Keep it short, lowercase, no spaces.")

        # ─ Action Buttons ──────────────────────────────────
        btn_row = ctk.CTkFrame(c, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        self.btn_check = ActionButton(
            btn_row, text="🔍  Check Dependencies",
            command=self._check_deps, style="secondary", width=200,
        )
        self.btn_check.pack(side="left", padx=(0, 8))
        Tooltip(self.btn_check,
                "Checks GPU, torch, unsloth, CUDA, etc.\n"
                "For Context Injection: just checks Ollama.")

        btn_gen = ActionButton(
            btn_row, text="📝  Generate Script",
            command=self._generate_script, style="primary", width=180,
        )
        btn_gen.pack(side="left", padx=(0, 8))
        Tooltip(btn_gen,
                "Creates the training script (LoRA) or\n"
                "Modelfile (Context Injection).\n"
                "Review before launching.")

        self.btn_launch = ActionButton(
            btn_row, text="🚀  Launch Training",
            command=self._launch, style="success", width=180,
        )
        self.btn_launch.pack(side="left")
        Tooltip(self.btn_launch,
                "LoRA: launches training script in new console.\n"
                "Inject: runs 'ollama create' with Modelfile.")

        # ─ Output Preview ──────────────────────────────────
        self.output = ContentPreview(
            c, label_text="Generated Script / Output", height=300,
        )
        self.output.pack(fill="both", expand=True, pady=(0, 8))

        # ─ Status ──────────────────────────────────────────
        self.status = StatusBar(c)
        self.status.pack(fill="x", pady=(5, 0))

        # Set initial visibility
        self._on_method_change()

    # ══════════════════════════════════════════════════════
    #  Model Scanning & Resolution
    # ══════════════════════════════════════════════════════

    def _scan_ollama(self):
        """Scan for locally installed Ollama models."""
        self.status.set_working("Scanning Ollama models…")

        def _do():
            models = _get_ollama_models()
            self.after(0, lambda: self._populate_ollama(models))

        threading.Thread(target=_do, daemon=True).start()

    def _populate_ollama(self, models):
        self.ollama_models = models
        if not models:
            self.ollama_menu.configure(
                values=["(no models found — is Ollama running?)"],
            )
            self.ollama_menu.set("(no models found — is Ollama running?)")
            self.resolve_label.configure(text="", text_color=COLORS["text_muted"])
            self.vram_label.configure(text="")
            self.status.set_error("No Ollama models found")
            return

        display = [f"{n}  ({s})" for n, s in models]
        self.ollama_menu.configure(values=display)
        self.ollama_menu.set(display[0])
        self.status.set_success(f"Found {len(models)} Ollama model(s)")

        # Trigger auto-resolution for first model
        self._on_model_selected(display[0])

    def _get_selected_ollama(self):
        """Extract bare model name from dropdown (strip the size suffix)."""
        raw = self.ollama_menu.get()
        return raw.split("  (")[0].strip()

    def _on_model_selected(self, _value=None):
        """Auto-resolve HuggingFace model when user selects an Ollama model."""
        ollama = self._get_selected_ollama()
        if "(no models" in ollama or "(scanning" in ollama:
            return

        hf_id, us_id, _fam, _sz, vram, is_abl, note = _resolve_hf_model(ollama)
        self.resolved_hf = hf_id
        self.resolved_unsloth = us_id

        if hf_id:
            color = COLORS["accent_green"] if not is_abl else COLORS["accent_blue"]
            self.resolve_label.configure(text=note, text_color=color)
            self.vram_label.configure(
                text=f"Estimated VRAM for 4-bit LoRA training: {vram}"
                     if vram != "unknown" else "",
            )
            if not self.show_override_var.get():
                self.override_frame.pack_forget()
        else:
            self.resolve_label.configure(text=note, text_color=COLORS["accent_orange"])
            self.vram_label.configure(text="")
            # Auto-open override when we can't resolve
            self.show_override_var.set(True)
            self._toggle_override()

    def _toggle_override(self):
        if self.show_override_var.get():
            self.override_frame.pack(fill="x", pady=(6, 0))
        else:
            self.override_frame.pack_forget()

    def _get_training_model_id(self):
        """Return the final HF model ID to use for LoRA training."""
        # 1. Manual override wins
        if self.show_override_var.get():
            custom = self.hf_override.get().strip()
            if custom:
                return custom
        # 2. Prefer Unsloth pre-quantized (faster loading)
        if self.resolved_unsloth:
            return self.resolved_unsloth
        # 3. Standard HF model
        if self.resolved_hf:
            return self.resolved_hf
        return None

    # ══════════════════════════════════════════════════════
    #  LoRA Presets
    # ══════════════════════════════════════════════════════

    def _apply_preset(self, vals: dict, label: str):
        """Fill LoRA config fields from a preset."""
        self.rank_var.set(vals["rank"])
        self.alpha_var.set(vals["alpha"])
        self.epochs_var.set(vals["epochs"])
        self.batch_var.set(vals["batch"])
        self.lr_var.set(vals["lr"])
        self.seq_var.set(vals["seq"])

        # Highlight active preset button, dim others
        for btn_label, btn in self._preset_btns.items():
            if btn_label == label:
                btn.configure(
                    fg_color=COLORS["accent"],
                    text_color=COLORS["text_primary"],
                    border_color=COLORS["accent"],
                )
            else:
                btn.configure(
                    fg_color=COLORS["bg_input"],
                    text_color=COLORS["text_primary"],
                    border_color=COLORS["border"],
                )

        self.status.set_success(f"Preset applied: {label}")

    # ══════════════════════════════════════════════════════
    #  Method Toggle
    # ══════════════════════════════════════════════════════

    def _on_method_change(self):
        method = self.method_var.get()
        if method == "lora":
            self.lora_frame.pack(fill="x", pady=(0, 12),
                                 after=self.method_card_outer)
            self.btn_check.configure(text="🔍  Check Dependencies")
            self.btn_launch.configure(text="🚀  Launch Training")
            self.method_warning.configure(text="")
        else:
            self.lora_frame.pack_forget()
            self.btn_check.configure(text="🔍  Check Ollama")
            self.btn_launch.configure(text="🚀  Create in Ollama")
            self.method_warning.configure(
                text="⚠ This is NOT real training. It pastes your data into the system "
                     "prompt. The model does not learn — it just gets a bigger context. "
                     "Use LoRA Fine-Tuning above for actual learning."
            )

    # ══════════════════════════════════════════════════════
    #  Dependency Check
    # ══════════════════════════════════════════════════════

    def _check_deps(self):
        method = self.method_var.get()
        self.status.set_working("Checking dependencies…")
        self.progress.reset()
        self.btn_check.configure(state="disabled")

        def _update(frac, text):
            self.after(0, lambda: self.progress.set_progress(frac, text))

        def _do():
            results = []

            if method == "inject":
                _update(0.3, "Checking Ollama…")
                ok = shutil.which("ollama") is not None
                results.append(("Ollama CLI", ok,
                                "Available" if ok else "Not found — install from ollama.com"))
                _update(0.7, "Checking models…")
                if self.ollama_models:
                    results.append(("Local Models", True,
                                    f"{len(self.ollama_models)} model(s) detected"))
                else:
                    results.append(("Local Models", False,
                                    "No models — run 'ollama pull <model>'"))
                _update(1.0, "Done")
            else:
                # ── Full LoRA deps — fast subprocess check ──
                import importlib.metadata
                importlib.invalidate_caches()

                steps = 9
                step = 0

                # Python
                step += 1; _update(step / steps, "Checking Python…")
                import platform
                results.append(("Python", True, f"v{platform.python_version()}"))

                # CUDA GPU (subprocess to avoid stale cached torch)
                step += 1; _update(step / steps, "Checking CUDA GPU…")
                try:
                    import sys as _sys
                    r = subprocess.run(
                        [_sys.executable, "-c",
                         "import torch; "
                         "print(torch.cuda.is_available()); "
                         "print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''); "
                         "print(torch.cuda.get_device_properties(0).total_mem if torch.cuda.is_available() else 0)"],
                        capture_output=True, text=True, timeout=30,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    lines = r.stdout.strip().splitlines()
                    has_cuda = lines[0].strip() == "True" if lines else False
                    if has_cuda:
                        gn = lines[1] if len(lines) > 1 else "GPU"
                        vr = int(lines[2]) / 1e9 if len(lines) > 2 else 0
                        results.append(("CUDA GPU", True, f"{gn} ({vr:.1f} GB)"))
                    else:
                        results.append(("CUDA GPU", False,
                                        "No CUDA GPU — LoRA training requires NVIDIA GPU"))
                except Exception:
                    results.append(("CUDA GPU", False, "Could not detect — is PyTorch installed?"))

                # Package checks via metadata (fast, no import)
                for pkg, label in [("unsloth", "Unsloth"),
                                   ("peft", "PEFT"),
                                   ("transformers", "Transformers"),
                                   ("trl", "TRL"),
                                   ("datasets", "Datasets")]:
                    step += 1; _update(step / steps, f"Checking {label}…")
                    try:
                        dist = importlib.metadata.distribution(pkg)
                        results.append((label, True, f"v{dist.version}"))
                    except importlib.metadata.PackageNotFoundError:
                        results.append((label, False, f"pip install {pkg}"))

                # Ollama
                step += 1; _update(step / steps, "Checking Ollama…")
                ok = shutil.which("ollama") is not None
                results.append(("Ollama CLI", ok,
                                "Available" if ok else "Optional — needed for final import"))

                # Model
                step += 1; _update(step / steps, "Checking model…")
                mid = self._get_training_model_id()
                if mid:
                    results.append(("Training Model", True, mid))
                else:
                    results.append(("Training Model", False,
                                    "Could not resolve HF model — enter one manually"))

            self.after(0, lambda: self._show_dep_results(results))

        threading.Thread(target=_do, daemon=True).start()

    def _show_dep_results(self, results):
        self.btn_check.configure(state="normal")
        lines = ["# Dependency Check\n"]
        all_ok = True
        for name, ok, msg in results:
            lines.append(f"{'✅' if ok else '❌'}  {name}: {msg}")
            if not ok:
                all_ok = False
        if all_ok:
            lines.append("\n🎉 All good — you're ready to go!")
            self.progress.stop("All dependencies ready ✓")
        else:
            lines.append("\n⚠ Fix the items above before continuing.")
            self.progress.set_progress(1.0, "⚠ Some dependencies missing")
            self.progress.bar.configure(progress_color=COLORS["error"])
        self.output.set_text("\n".join(lines))
        if all_ok:
            self.status.set_success("All dependencies ready")
        else:
            self.status.set_error("Some dependencies missing")

    # ══════════════════════════════════════════════════════
    #  Script Generation
    # ══════════════════════════════════════════════════════

    def _generate_script(self):
        if self.method_var.get() == "lora":
            self._generate_lora_script()
        else:
            self._generate_context_injection()

    # ── Context Injection (honest name) ───────────────────

    def _generate_context_injection(self):
        """Generate a Modelfile that injects data as system-prompt context."""
        ollama_model = self._get_selected_ollama()
        model_name = self.model_name_field.get() or "my-injected-model"

        if "(no " in ollama_model or "(scanning" in ollama_model:
            self.status.set_error("Scan for Ollama models first!")
            return

        entries = get_all_entries()
        if not entries:
            self.status.set_error("No data in library — collect some data first!")
            return

        # Build context (truncated to ~8K chars for Modelfile size)
        parts, chars = [], 0
        for e in entries:
            title = e.get("title", "Untitled")
            content = e.get("content", "")
            chunk = f"--- {title} ---\n{content}\n"
            if chars + len(chunk) > 8000:
                parts.append(f"… and {len(entries) - len(parts)} more entries (truncated)")
                break
            parts.append(chunk)
            chars += len(chunk)

        context = "\n".join(parts).replace('"""', "'''")

        modelfile = (
            f"# Ollama Modelfile — Context Injection (NOT real training)\n"
            f"# Base: {ollama_model}\n"
            f"# Entries: {len(entries)}  ({chars:,} chars injected)\n\n"
            f"FROM {ollama_model}\n\n"
            f"PARAMETER temperature 0.7\n"
            f"PARAMETER top_p 0.9\n"
            f"PARAMETER num_ctx 8192\n\n"
            f'SYSTEM """\n'
            f"You are a knowledgeable assistant. You have access to the following\n"
            f"reference data. Use it to answer questions accurately.\n\n"
            f"{context}\n"
            f'"""\n'
        )

        path = os.path.join(DATA_DIR, "Modelfile")
        with open(path, "w", encoding="utf-8") as f:
            f.write(modelfile)

        preview = (
            f"# ═══ Context Injection — Modelfile ═══\n"
            f"#\n"
            f"# ⚠ This is NOT real training!\n"
            f"# Your data is pasted into the system prompt.\n"
            f"# The model does not learn — it just gets more context.\n"
            f"#\n"
            f"# Base model:  {ollama_model}\n"
            f"# New name:    {model_name}\n"
            f"# Entries:     {len(entries)} ({chars:,} chars)\n"
            f"# Saved to:    {path}\n"
            f"#\n"
            f"# Create:  ollama create {model_name} -f \"{path}\"\n"
            f"# Run:     ollama run {model_name}\n"
            f"#\n"
            f"{'=' * 60}\n\n"
            f"{modelfile}"
        )

        self.output.set_text(preview)
        self.status.set_success(f"Modelfile saved → click Launch to create '{model_name}'")

    # ── LoRA Training Script (real training) ─────────────

    def _auto_export_training_data(self):
        """Auto-export library data as Alpaca JSONL for training.

        Returns (path, sample_count) or (None, 0) on failure.
        """
        from core.exporter import export_alpaca
        from core.database import get_all_entries as _get_entries

        entries = _get_entries()
        if not entries:
            return None, 0

        data_file = os.path.join(EXPORTS_DIR, "training_data.jsonl")
        try:
            path, count = export_alpaca(
                entries, output_path=data_file,
                instruction_template="default",
                chunk_size=512,
            )
            return path, count
        except Exception:
            return None, 0

    def _generate_lora_script(self):
        """Generate a full Unsloth LoRA training script."""
        model_id = self._get_training_model_id()
        if not model_id:
            self.status.set_error(
                "No HF model resolved — select an Ollama model or enter a HF ID manually."
            )
            self.show_override_var.set(True)
            self._toggle_override()
            return

        model_name = self.model_name_field.get() or "my-finetuned-model"
        ollama_model = self._get_selected_ollama()

        rank   = self.rank_var.get()
        alpha  = self.alpha_var.get()
        epochs = self.epochs_var.get()
        batch  = self.batch_var.get()
        lr     = self.lr_var.get()
        seq_len = self.seq_var.get()

        stats = get_stats()
        if stats.get("total_entries", 0) == 0:
            self.status.set_error("No data in library — collect some data first!")
            return

        # Auto-export training data from library
        data_file, sample_count = self._auto_export_training_data()
        if not data_file or sample_count == 0:
            self.status.set_error("Export failed — check your library has data.")
            return
        adapter_dir = os.path.join(DATA_DIR, "lora_adapter")
        gguf_dir = os.path.join(DATA_DIR, f"{model_name}_gguf")
        modelfile_path = os.path.join(DATA_DIR, "Modelfile")
        download_hint = self._estimate_download(model_id)

        # Build the training script as a regular string (no nested f-strings)
        script_lines = [
            '"""',
            'LoRA Fine-Tuning Script — Generated by LoRA Data Toolkit',
            f'Model:   {model_id}',
            f'Source:  {ollama_model}',
            f'Config:  r={rank}  alpha={alpha}  epochs={epochs}  batch={batch}  lr={lr}',
            '"""',
            'from unsloth import FastLanguageModel',
            'import torch, json, os',
            '',
            '# ─── 1. Load Base Model ────────────────────────────────',
            f'print("📥 Loading model: {model_id}")',
            f'print("   (First run will download ~{download_hint})")',
            'print()',
            '',
            'model, tokenizer = FastLanguageModel.from_pretrained(',
            f'    model_name="{model_id}",',
            f'    max_seq_length={seq_len},',
            '    dtype=None,',
            '    load_in_4bit=True,',
            ')',
            '',
            '# ─── 2. Add LoRA Adapters ──────────────────────────────',
            f'print("🔧 Adding LoRA adapters (r={rank}, alpha={alpha})...")',
            '',
            'model = FastLanguageModel.get_peft_model(',
            '    model,',
            f'    r={rank},',
            f'    lora_alpha={alpha},',
            '    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",',
            '                     "gate_proj", "up_proj", "down_proj"],',
            '    lora_dropout=0,',
            '    bias="none",',
            '    use_gradient_checkpointing="unsloth",',
            ')',
            '',
            '# ─── 3. Load Training Data ─────────────────────────────',
            f'DATA_FILE = r"{data_file}"',
            '',
            'if not os.path.exists(DATA_FILE):',
            '    print("❌ Training data not found!")',
            '    print(f"   Expected: {DATA_FILE}")',
            '    print("   Go to Export page → Alpaca format → save as \'training_data.jsonl\'")',
            '    exit(1)',
            '',
            'from datasets import Dataset',
            '',
            'with open(DATA_FILE, "r", encoding="utf-8") as f:',
            '    data = [json.loads(line) for line in f if line.strip()]',
            '',
            'print(f"📊 Loaded {len(data)} training samples")',
            '',
            'alpaca_prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.',
            '',
            '### Instruction:',
            '{}',
            '',
            '### Input:',
            '{}',
            '',
            '### Response:',
            '{}"""',
            '',
            'def format_alpaca(examples):',
            '    texts = []',
            '    for inst, inp, out in zip(examples["instruction"],',
            '                               examples["input"],',
            '                               examples["output"]):',
            '        text = alpaca_prompt.format(inst, inp, out) + tokenizer.eos_token',
            '        texts.append(text)',
            '    return {"text": texts}',
            '',
            'dataset = Dataset.from_list(data)',
            'dataset = dataset.map(format_alpaca, batched=True)',
            '',
            '# ─── 4. Train ──────────────────────────────────────────',
            'from trl import SFTTrainer',
            'from transformers import TrainingArguments',
            '',
            'print()',
            f'print("🚀 Starting LoRA training...")',
            f'print(f"   Epochs: {epochs}  |  Batch: {batch}  |  LR: {lr}")',
            f'print(f"   Seq len: {seq_len}  |  Samples: {{len(data)}}")',
            'print()',
            '',
            'trainer = SFTTrainer(',
            '    model=model,',
            '    tokenizer=tokenizer,',
            '    train_dataset=dataset,',
            '    dataset_text_field="text",',
            f'    max_seq_length={seq_len},',
            '    args=TrainingArguments(',
            f'        per_device_train_batch_size={batch},',
            '        gradient_accumulation_steps=4,',
            '        warmup_steps=5,',
            f'        num_train_epochs={epochs},',
            f'        learning_rate={lr},',
            '        fp16=not torch.cuda.is_bf16_supported(),',
            '        bf16=torch.cuda.is_bf16_supported(),',
            '        logging_steps=1,',
            '        output_dir="outputs",',
            '        optim="adamw_8bit",',
            '        seed=42,',
            '    ),',
            ')',
            '',
            'train_stats = trainer.train()',
            'print()',
            'print(f"✅ Training complete!  Loss: {train_stats.training_loss:.4f}")',
            '',
            '# ─── 5. Save LoRA Adapter ──────────────────────────────',
            f'ADAPTER_DIR = r"{adapter_dir}"',
            'model.save_pretrained(ADAPTER_DIR)',
            'tokenizer.save_pretrained(ADAPTER_DIR)',
            'print(f"💾 Adapter saved: {ADAPTER_DIR}")',
            '',
            '# ─── 6. Export to GGUF ─────────────────────────────────',
            'print("🔄 Merging & converting to GGUF (Q4_K_M)...")',
            f'GGUF_DIR = r"{gguf_dir}"',
            'model.save_pretrained_gguf(GGUF_DIR, tokenizer, quantization_method="q4_k_m")',
            'print(f"✅ GGUF saved: {GGUF_DIR}")',
            '',
            '# ─── 7. Write Modelfile ────────────────────────────────',
            f'MODELFILE = r"{modelfile_path}"',
            'sys_prompt = "You are a knowledgeable assistant fine-tuned with specialized training data."',
            'mf_lines = [',
            '    "FROM ./" + os.path.basename(GGUF_DIR) + "/unsloth.Q4_K_M.gguf",',
            '    "",',
            '    "PARAMETER temperature 0.7",',
            '    "PARAMETER top_p 0.9",',
            '    "",',
            '    \'SYSTEM """\'  + sys_prompt + \'"""\',',
            ']',
            'with open(MODELFILE, "w") as f:',
            '    f.write("\\n".join(mf_lines) + "\\n")',
            'print(f"📄 Modelfile written: {MODELFILE}")',
            '',
            'print()',
            'print("═" * 50)',
            'print("🎉  ALL DONE!")',
            'print("═" * 50)',
            'print()',
            f'print("Next steps:")',
            f'print(f"  1. cd {DATA_DIR}")',
            f'print(f"  2. ollama create {model_name} -f Modelfile")',
            f'print(f"  3. ollama run {model_name}")',
            'print()',
            'input("Press Enter to exit...")',
        ]

        script = "\n".join(script_lines) + "\n"

        # Save script
        script_path = os.path.join(DATA_DIR, "train_lora.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        preview = (
            f"# ═══ LoRA Fine-Tuning Script (REAL TRAINING) ═══\n"
            f"#\n"
            f"# Ollama model:  {ollama_model}\n"
            f"# HF source:     {model_id}\n"
            f"# LoRA:          r={rank}  α={alpha}  epochs={epochs}"
            f"  batch={batch}  lr={lr}\n"
            f"# Output name:   {model_name}\n"
            f"#\n"
            f"# Saved:  {script_path}\n"
            f"#\n"
            f"# Steps:\n"
            f"#   1. ✅ Data auto-exported ({sample_count} samples"
            f" → training_data.jsonl)\n"
            f"#   2. Click Launch  (or: python \"{script_path}\")\n"
            f"#   3. After training: ollama create {model_name} -f Modelfile\n"
            f"#   4. ollama run {model_name}\n"
            f"#\n"
            f"{'=' * 60}\n\n"
            f"{script}"
        )

        self.output.set_text(preview)
        self.status.set_success(
            f"Training script saved — {sample_count} samples exported"
            f" → click Launch!"
        )

    def _estimate_download(self, model_id):
        """Rough download-size estimate for display purposes."""
        mid = model_id.lower()
        if "bnb-4bit" in mid or "4bit" in mid:
            return "2–8 GB (pre-quantized)"
        for pattern, est in [("70b", "35–40 GB"), ("72b", "35–40 GB"),
                             ("30b", "15–20 GB"), ("32b", "16–20 GB"),
                             ("27b", "14–18 GB"), ("14b", "8–10 GB"),
                             ("13b", "8–10 GB"),  ("8b", "4–5 GB"),
                             ("7b", "4–5 GB"),    ("9b", "5–6 GB"),
                             ("4b", "2–3 GB"),    ("3b", "2–3 GB"),
                             ("1b", "1–2 GB"),    ("2b", "1–2 GB")]:
            if pattern in mid:
                return est
        return "varies"

    # ══════════════════════════════════════════════════════
    #  Launch
    # ══════════════════════════════════════════════════════

    def _launch(self):
        if self.method_var.get() == "lora":
            self._launch_lora()
        else:
            self._launch_inject()

    def _launch_inject(self):
        """Run ``ollama create`` with the generated Modelfile."""
        modelfile_path = os.path.join(DATA_DIR, "Modelfile")
        model_name = self.model_name_field.get() or "my-injected-model"

        if not os.path.exists(modelfile_path):
            self.status.set_error("Generate the Modelfile first!")
            return

        self.status.set_working(f"Creating '{model_name}' in Ollama…")

        def _do():
            try:
                r = subprocess.run(
                    ["ollama", "create", model_name, "-f", modelfile_path],
                    capture_output=True, text=True, timeout=120,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if r.returncode == 0:
                    self.after(0, lambda: self.status.set_success(
                        f"✅ '{model_name}' created!  Run: ollama run {model_name}",
                    ))
                    self.after(0, lambda: self.output.set_text(
                        self.output.get_text()
                        + f"\n\n{'=' * 60}\n"
                        + f"# ✅ SUCCESS — model '{model_name}' is ready in Ollama\n"
                        + f"#   ollama run {model_name}\n"
                        + f"{'=' * 60}\n"
                        + (r.stdout or "")
                    ))
                else:
                    err = (r.stderr or r.stdout).strip()[:120]
                    self.after(0, lambda: self.status.set_error(f"Failed: {err}"))
            except FileNotFoundError:
                self.after(0, lambda: self.status.set_error(
                    "Ollama not found — install from ollama.com",
                ))
            except Exception as exc:
                self.after(0, lambda: self.status.set_error(f"Error: {exc}"))

        threading.Thread(target=_do, daemon=True).start()

    def _launch_lora(self):
        """Launch the LoRA training script in a new console window."""
        script_path = os.path.join(DATA_DIR, "train_lora.py")

        if not os.path.exists(script_path):
            self.status.set_error("Generate the training script first!")
            return

        data_path = os.path.join(EXPORTS_DIR, "training_data.jsonl")
        if not os.path.exists(data_path):
            # Auto-export before launching
            data_path, count = self._auto_export_training_data()
            if not data_path or count == 0:
                self.status.set_error(
                    "No data to train on — collect some data first!"
                )
                return

        self.status.set_working("Launching training in new console…")

        # Use the same venv Python that is running this app
        venv_python = sys.executable

        def _do():
            try:
                # Wrap in cmd /K so the console stays open on error
                # cmd /K runs the command then keeps the window open
                subprocess.Popen(
                    [
                        "cmd", "/K",
                        f'"{venv_python}" "{script_path}" & '
                        f'if errorlevel 1 (echo. & echo '
                        f'[ERROR] Training crashed — see above. & pause)'
                    ],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                    cwd=DATA_DIR,
                )
                self.after(0, lambda: self.status.set_success(
                    "Training launched in new console — watch it for progress!",
                ))
            except Exception as exc:
                self.after(0, lambda: self.status.set_error(
                    f"Launch failed: {exc}",
                ))

        threading.Thread(target=_do, daemon=True).start()
