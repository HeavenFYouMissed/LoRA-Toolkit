"""
Model Merger Page — Merge 2+ models using mergekit.

Pick Ollama models or HuggingFace IDs, choose a merge method,
set blend weights, generate the config, run the merge, and
import the result to Ollama.
"""
import os
import subprocess
import threading
import customtkinter as ctk
from gui.theme import COLORS, FONT_FAMILY, FONT_SIZES
from gui.widgets import (
    PageHeader, InputField, ActionButton, StatusBar,
    Tooltip, ContentPreview,
)
from core.merger import (
    MERGE_METHODS, MERGE_DIR,
    generate_merge_config, run_merge, generate_modelfile,
)
from config import DATA_DIR


def _get_ollama_models():
    """Run `ollama list` and return [(name, size), ...]."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return []
        models = []
        for line in result.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if parts:
                name = parts[0]
                size = (parts[2] + " " + parts[3]) if len(parts) >= 4 else ""
                models.append((name, size))
        return models
    except Exception:
        return []


class MergePage(ctk.CTkFrame):
    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        self.app = app
        self.ollama_models = []       # [(name, size), ...]
        self.model_slots = []         # list of slot widget dicts
        self._cancel_flag = False
        self._build_ui()

    # ── helpers ─────────────────────────────────────────────

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
            wraplength=680, justify="left",
        ).pack(anchor="w", pady=(2, 6))

    # ── build ──────────────────────────────────────────────

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)
        self.container = container

        # Header
        PageHeader(
            container, icon="🔀", title="Model Merger",
            subtitle="Merge 2+ models together — SLERP, TIES, DARE, Linear, Frankenmerge"
        ).pack(fill="x", pady=(0, 12))

        # ─ Important info card ──────────────────────────────
        info_card = self._card(container)
        self._heading(info_card, "ℹ️  How Model Merging Works")
        self._hint(info_card,
            "Model merging combines the weights of two or more models into a single model. "
            "The merged model inherits capabilities from all source models.\n\n"
            "⚠ Important rules:\n"
            "• Models MUST be the same architecture (e.g. all Qwen, all Llama)\n"
            "• For SLERP/Linear/TIES: models must be the same size (e.g. two 14Bs)\n"
            "• Passthrough (Frankenmerge) can combine different sizes but is experimental\n"
            "• Models need to be in HuggingFace safetensors format (not GGUF)\n\n"
            "💡 Tip: For Ollama models, mergekit needs the original HF weights.\n"
            "Enter the HuggingFace model ID (e.g. 'Qwen/Qwen2.5-14B-Instruct')."
        )

        # ─ Model Slots ─────────────────────────────────────
        models_card = self._card(container)
        self._heading(models_card, "🤖 Models to Merge")
        self._hint(models_card,
            "Add 2+ models. Enter HuggingFace model IDs or local paths to safetensors directories. "
            "Set the weight/influence for each model (0.0 to 1.0)."
        )

        # Ollama reference row
        ref_row = ctk.CTkFrame(models_card, fg_color="transparent")
        ref_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            ref_row, text="Your Ollama models (for reference):",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        ).pack(side="left")

        scan_btn = ActionButton(
            ref_row, text="🔍 Scan", command=self._scan_ollama,
            style="secondary", width=80,
        )
        scan_btn.pack(side="left", padx=(8, 0))

        self.ollama_ref_label = ctk.CTkLabel(
            models_card, text="(click Scan to see installed models)",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
            wraplength=650, justify="left",
        )
        self.ollama_ref_label.pack(anchor="w", pady=(0, 8))

        # Model slots container
        self.slots_frame = ctk.CTkFrame(models_card, fg_color="transparent")
        self.slots_frame.pack(fill="x")

        # Add initial 2 slots
        self._add_model_slot()
        self._add_model_slot()

        # Add model button
        add_row = ctk.CTkFrame(models_card, fg_color="transparent")
        add_row.pack(fill="x", pady=(8, 0))

        add_btn = ActionButton(
            add_row, text="➕  Add Model", command=self._add_model_slot,
            style="secondary", width=140,
        )
        add_btn.pack(side="left")
        Tooltip(add_btn, "Add another model to the merge.\nSLERP only supports exactly 2 models.")

        # ─ Merge Method ────────────────────────────────────
        method_card = self._card(container)
        self._heading(method_card, "⚗️ Merge Method")

        self.method_var = ctk.StringVar(value="slerp")

        for method_key, method_info in MERGE_METHODS.items():
            row = ctk.CTkFrame(method_card, fg_color="transparent")
            row.pack(fill="x", pady=(0, 2))

            radio = ctk.CTkRadioButton(
                row,
                text=method_info["name"],
                variable=self.method_var,
                value=method_key,
                font=(FONT_FAMILY, FONT_SIZES["body"]),
                text_color=COLORS["text_primary"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
            )
            radio.pack(side="left")
            Tooltip(radio, method_info["description"])

            # Short inline description
            ctk.CTkLabel(
                row,
                text=f"  —  {method_info['description'].split(chr(10))[0]}",
                font=(FONT_FAMILY, FONT_SIZES["small"]),
                text_color=COLORS["text_muted"],
            ).pack(side="left", padx=(4, 0))

        # ─ Parameters ──────────────────────────────────────
        params_card = self._card(container)
        self._heading(params_card, "⚙ Parameters")

        params_row = ctk.CTkFrame(params_card, fg_color="transparent")
        params_row.pack(fill="x")

        # SLERP t / blend factor
        t_frame = ctk.CTkFrame(params_row, fg_color="transparent")
        t_frame.pack(side="left", padx=(0, 20))
        t_lbl = ctk.CTkLabel(t_frame, text="Blend (t)",
                    font=(FONT_FAMILY, FONT_SIZES["small"]),
                    text_color=COLORS["text_muted"])
        t_lbl.pack(anchor="w")
        self.t_var = ctk.StringVar(value="0.5")
        t_entry = ctk.CTkEntry(t_frame, textvariable=self.t_var,
                    width=80, height=30,
                    font=(FONT_FAMILY, FONT_SIZES["body"]),
                    fg_color=COLORS["bg_input"],
                    text_color=COLORS["text_primary"],
                    border_color=COLORS["border"], border_width=1,
                    corner_radius=6)
        t_entry.pack(anchor="w", pady=(2, 0))
        Tooltip(t_lbl, "SLERP blend factor (0.0 to 1.0).\n0.0 = 100% model A, 1.0 = 100% model B.\n0.5 = equal blend of both.")
        Tooltip(t_entry, "SLERP blend factor (0.0 to 1.0).\n0.0 = 100% model A, 1.0 = 100% model B.\n0.5 = equal blend of both.")

        # DARE density
        d_frame = ctk.CTkFrame(params_row, fg_color="transparent")
        d_frame.pack(side="left", padx=(0, 20))
        d_lbl = ctk.CTkLabel(d_frame, text="Density",
                    font=(FONT_FAMILY, FONT_SIZES["small"]),
                    text_color=COLORS["text_muted"])
        d_lbl.pack(anchor="w")
        self.density_var = ctk.StringVar(value="0.5")
        d_entry = ctk.CTkEntry(d_frame, textvariable=self.density_var,
                    width=80, height=30,
                    font=(FONT_FAMILY, FONT_SIZES["body"]),
                    fg_color=COLORS["bg_input"],
                    text_color=COLORS["text_primary"],
                    border_color=COLORS["border"], border_width=1,
                    corner_radius=6)
        d_entry.pack(anchor="w", pady=(2, 0))
        Tooltip(d_lbl, "TIES/DARE density (0.0 to 1.0).\nFraction of weights to keep.\nHigher = more parameters retained.\n0.5 is a good default.")
        Tooltip(d_entry, "TIES/DARE density (0.0 to 1.0).\nFraction of weights to keep.\nHigher = more parameters retained.\n0.5 is a good default.")

        # dtype
        dt_frame = ctk.CTkFrame(params_row, fg_color="transparent")
        dt_frame.pack(side="left", padx=(0, 20))
        dt_lbl = ctk.CTkLabel(dt_frame, text="Dtype",
                    font=(FONT_FAMILY, FONT_SIZES["small"]),
                    text_color=COLORS["text_muted"])
        dt_lbl.pack(anchor="w")
        self.dtype_menu = ctk.CTkOptionMenu(
            dt_frame,
            values=["float16", "bfloat16", "float32"],
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            width=120, height=30,
        )
        self.dtype_menu.set("float16")
        self.dtype_menu.pack(anchor="w", pady=(2, 0))
        Tooltip(dt_lbl, "Data type for merged weights.\nfloat16 = standard, saves disk space.\nbfloat16 = better for newer models.\nfloat32 = highest precision, 2× size.")
        Tooltip(self.dtype_menu, "Data type for merged weights.\nfloat16 = standard, saves disk space.\nbfloat16 = better for newer models.\nfloat32 = highest precision, 2× size.")

        # ─ Output ──────────────────────────────────────────
        out_card = self._card(container)
        self._heading(out_card, "📦 Output")

        self.output_name_field = InputField(
            out_card, label_text="Merged Model Name",
            placeholder="e.g. qwen14b-merged"
        )
        self.output_name_field.pack(fill="x", pady=(6, 0))
        self.output_name_field.set("merged-model")
        Tooltip(self.output_name_field,
                "Name for the merged output.\nUsed for the output directory and Ollama model name.")

        # ─ Action Buttons ──────────────────────────────────
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        btn_check = ActionButton(
            btn_row, text="🔍  Check mergekit", command=self._check_deps,
            style="secondary", width=170,
        )
        btn_check.pack(side="left", padx=(0, 8))
        Tooltip(btn_check, "Checks if mergekit is installed\nand ready for model merging.")

        btn_generate = ActionButton(
            btn_row, text="📝  Generate Config", command=self._generate_config,
            style="primary", width=170,
        )
        btn_generate.pack(side="left", padx=(0, 8))
        Tooltip(btn_generate, "Generates the mergekit YAML config file.\nYou can review it before running the merge.")

        self.btn_merge = ActionButton(
            btn_row, text="🔀  Run Merge", command=self._run_merge,
            style="success", width=150,
        )
        self.btn_merge.pack(side="left", padx=(0, 8))
        Tooltip(self.btn_merge, "Runs mergekit to merge the models.\nThis can take a while depending on model size.\nRequires enough disk space for all models + output.")

        btn_cancel = ActionButton(
            btn_row, text="⛔ Cancel", command=self._cancel_merge,
            style="secondary", width=100,
        )
        btn_cancel.pack(side="left")

        # ─ Output Preview ──────────────────────────────────
        self.output = ContentPreview(
            container, label_text="Config / Merge Output", height=280,
        )
        self.output.pack(fill="both", expand=True, pady=(0, 8))

        # ─ Status ──────────────────────────────────────────
        self.status = StatusBar(container)
        self.status.pack(fill="x", pady=(5, 0))

        # Auto-scan
        self.after(500, self._scan_ollama)

    # ── model slot management ──────────────────────────────

    def _add_model_slot(self):
        idx = len(self.model_slots)
        slot_frame = ctk.CTkFrame(self.slots_frame, fg_color=COLORS["bg_input"],
                                   corner_radius=8)
        slot_frame.pack(fill="x", pady=(0, 6))

        inner = ctk.CTkFrame(slot_frame, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=8)

        # Model label
        lbl = ctk.CTkLabel(
            inner, text=f"Model {idx + 1}",
            font=(FONT_FAMILY, FONT_SIZES["small"], "bold"),
            text_color=COLORS["text_secondary"],
            width=65,
        )
        lbl.pack(side="left")

        # Model ID entry
        model_var = ctk.StringVar(value="")
        entry = ctk.CTkEntry(
            inner, textvariable=model_var,
            placeholder_text="HuggingFace ID (e.g. Qwen/Qwen2.5-14B-Instruct) or local path",
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"], border_width=1,
            corner_radius=6, height=30,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(8, 8))

        # Weight
        weight_lbl = ctk.CTkLabel(
            inner, text="Weight:",
            font=(FONT_FAMILY, FONT_SIZES["small"]),
            text_color=COLORS["text_muted"],
        )
        weight_lbl.pack(side="left")

        weight_var = ctk.StringVar(value="0.5" if idx == 0 else "0.5")
        weight_entry = ctk.CTkEntry(
            inner, textvariable=weight_var,
            width=55, height=30,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"], border_width=1,
            corner_radius=6,
        )
        weight_entry.pack(side="left", padx=(4, 8))
        Tooltip(weight_lbl, f"Influence weight for Model {idx+1}.\n0.0 = no influence, 1.0 = full influence.\nFor SLERP, Model 1's weight is the 't' blend factor.")
        Tooltip(weight_entry, f"Influence weight for Model {idx+1}.\n0.0 = no influence, 1.0 = full influence.\nFor SLERP, Model 1's weight is the 't' blend factor.")

        # Remove button (only if > 2 slots)
        remove_btn = ctk.CTkButton(
            inner, text="✕", width=30, height=30,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
            fg_color=COLORS["bg_hover"],
            hover_color=COLORS["accent"],
            text_color=COLORS["text_muted"],
            corner_radius=6,
            command=lambda f=slot_frame, s=None: self._remove_model_slot(f),
        )
        remove_btn.pack(side="left")

        slot = {
            "frame": slot_frame,
            "model_var": model_var,
            "weight_var": weight_var,
            "entry": entry,
        }
        self.model_slots.append(slot)

    def _remove_model_slot(self, frame):
        if len(self.model_slots) <= 2:
            self.status.set_error("Need at least 2 models to merge")
            return
        # Find and remove
        for i, slot in enumerate(self.model_slots):
            if slot["frame"] is frame:
                frame.destroy()
                self.model_slots.pop(i)
                # Relabel remaining
                for j, s in enumerate(self.model_slots):
                    for w in s["frame"].winfo_children():
                        for child in w.winfo_children():
                            if isinstance(child, ctk.CTkLabel) and hasattr(child, 'cget'):
                                try:
                                    txt = child.cget("text")
                                    if txt.startswith("Model "):
                                        child.configure(text=f"Model {j+1}")
                                except Exception:
                                    pass
                break

    def _get_models_list(self):
        """Collect model entries as list of dicts."""
        models = []
        for slot in self.model_slots:
            name = slot["model_var"].get().strip()
            if not name:
                continue
            try:
                weight = float(slot["weight_var"].get())
            except ValueError:
                weight = 0.5
            models.append({"name": name, "weight": weight})
        return models

    # ── Ollama scanning ────────────────────────────────────

    def _scan_ollama(self):
        self.status.set_working("Scanning Ollama models...")

        def do_scan():
            models = _get_ollama_models()
            self.after(0, lambda: self._show_ollama(models))

        threading.Thread(target=do_scan, daemon=True).start()

    def _show_ollama(self, models):
        self.ollama_models = models
        if not models:
            self.ollama_ref_label.configure(
                text="No Ollama models found. Enter HuggingFace model IDs directly."
            )
            self.status.set_error("No Ollama models detected")
            return

        # Show as compact list
        lines = []
        for name, size in models:
            lines.append(f"• {name} ({size})")

        display = "\n".join(lines[:12])
        if len(models) > 12:
            display += f"\n... and {len(models) - 12} more"

        self.ollama_ref_label.configure(text=display)
        self.status.set_success(f"Found {len(models)} Ollama models (use their HF source IDs for merging)")

    # ── dependency check ───────────────────────────────────

    def _check_deps(self):
        self.status.set_working("Checking mergekit...")

        def do_check():
            results = []

            # Check mergekit
            try:
                import mergekit
                results.append(("mergekit", True, f"v{getattr(mergekit, '__version__', 'installed')}"))
            except ImportError:
                results.append(("mergekit", False, "Not installed. Run: pip install mergekit"))

            # Check PyYAML
            try:
                import yaml
                results.append(("PyYAML", True, f"v{yaml.__version__}"))
            except ImportError:
                results.append(("PyYAML", False, "pip install pyyaml"))

            # Check torch
            try:
                import torch
                cuda = torch.cuda.is_available()
                if cuda:
                    gn = torch.cuda.get_device_name(0)
                    vram = torch.cuda.get_device_properties(0).total_mem / 1e9
                    results.append(("CUDA GPU", True, f"{gn} ({vram:.1f} GB)"))
                else:
                    results.append(("CUDA", False, "No GPU — merging works on CPU but is slower"))
            except ImportError:
                results.append(("PyTorch", False, "pip install torch (needed for mergekit)"))

            # Check disk space
            try:
                import shutil
                total, used, free = shutil.disk_usage(MERGE_DIR)
                free_gb = free / (1024**3)
                results.append(("Disk Space", free_gb > 30,
                                f"{free_gb:.1f} GB free" + (" ⚠ may need 50+ GB for large models" if free_gb < 50 else "")))
            except Exception:
                pass

            self.after(0, lambda: self._show_dep_results(results))

        threading.Thread(target=do_check, daemon=True).start()

    def _show_dep_results(self, results):
        lines = ["# Merge Dependencies\n"]
        all_ok = True
        for name, ok, msg in results:
            lines.append(f"{'✅' if ok else '❌'} {name}: {msg}")
            if not ok:
                all_ok = False

        if all_ok:
            lines.append("\n🎉 Ready to merge!")
        else:
            lines.append("\n⚠ Install missing dependencies:")
            lines.append("  pip install mergekit torch pyyaml")

        self.output.set_text("\n".join(lines))
        if all_ok:
            self.status.set_success("All merge dependencies ready")
        else:
            self.status.set_error("Some dependencies missing")

    # ── config generation ──────────────────────────────────

    def _generate_config(self):
        models = self._get_models_list()
        method = self.method_var.get()
        output_name = self.output_name_field.get() or "merged-model"

        method_info = MERGE_METHODS.get(method, {})
        min_m = method_info.get("min_models", 2)
        max_m = method_info.get("max_models", 10)

        if len(models) < min_m:
            self.status.set_error(f"Need at least {min_m} models for {method_info.get('name', method)}")
            return
        if len(models) > max_m:
            self.status.set_error(f"{method_info.get('name', method)} supports max {max_m} models")
            return

        # For SLERP, use the t parameter
        if method == "slerp":
            try:
                t = float(self.t_var.get())
            except ValueError:
                t = 0.5
            models[0]["weight"] = t

        params = {
            "dtype": self.dtype_menu.get(),
        }
        if method in ("ties", "dare_ties"):
            try:
                params["density"] = float(self.density_var.get())
            except ValueError:
                params["density"] = 0.5

        try:
            yaml_str, config_path = generate_merge_config(
                models=models,
                method=method,
                base_model=models[0]["name"],
                output_name=output_name,
                parameters=params,
            )
        except Exception as e:
            self.status.set_error(f"Config error: {e}")
            return

        # Show preview
        model_list = "\n".join(f"#   {i+1}. {m['name']} (weight: {m['weight']})" for i, m in enumerate(models))
        merge_cmd = f"mergekit-yaml {config_path} {os.path.join(MERGE_DIR, output_name)} --copy-tokenizer --allow-crimes --lazy-unpickle"

        preview = (
            f"# ═══ Merge Config: {MERGE_METHODS[method]['name']} ═══\n"
            f"#\n"
            f"# Method:  {method}\n"
            f"# Models:\n{model_list}\n"
            f"# Output:  {output_name}\n"
            f"# Config:  {config_path}\n"
            f"#\n"
            f"# To merge manually:\n"
            f"#   {merge_cmd}\n"
            f"#\n"
            f"{'='*60}\n\n"
            f"{yaml_str}\n"
            f"{'='*60}\n"
            f"# After merge completes:\n"
            f"#   1. Convert to GGUF:  python convert_hf_to_gguf.py {os.path.join(MERGE_DIR, output_name)}\n"
            f"#   2. Quantize:         llama-quantize model.gguf model.q4_k_m.gguf q4_k_m\n"
            f"#   3. Create Modelfile: FROM ./model.q4_k_m.gguf\n"
            f"#   4. Import:           ollama create {output_name} -f Modelfile\n"
            f"#   5. Run:              ollama run {output_name}\n"
        )

        self.output.set_text(preview)
        self.status.set_success(f"Config saved to {config_path}")

    # ── run merge ──────────────────────────────────────────

    def _run_merge(self):
        output_name = self.output_name_field.get() or "merged-model"
        config_path = os.path.join(MERGE_DIR, f"{output_name}_config.yaml")

        if not os.path.exists(config_path):
            self.status.set_error("Generate the config first!")
            return

        self._cancel_flag = False
        self.status.set_working("Running merge... this may take a while")
        self.btn_merge.configure(state="disabled")

        def on_progress(line):
            self.after(0, lambda l=line: self._append_log(l))

        def should_cancel():
            return self._cancel_flag

        def do_merge():
            result = run_merge(
                config_path=config_path,
                output_name=output_name,
                on_progress=on_progress,
                should_cancel=should_cancel,
            )

            def finish():
                self.btn_merge.configure(state="normal")
                if result["success"]:
                    out_dir = result["output_dir"]
                    # Generate Modelfile
                    mf_path = generate_modelfile(
                        model_path=f"./{output_name}.gguf",
                        output_name=output_name,
                    )
                    self._append_log(f"\n{'='*60}")
                    self._append_log(f"✅ Merge complete!")
                    self._append_log(f"Output: {out_dir}")
                    self._append_log(f"Modelfile: {mf_path}")
                    self._append_log(f"\nNext steps:")
                    self._append_log(f"  1. Convert to GGUF (see commands above)")
                    self._append_log(f"  2. ollama create {output_name} -f {mf_path}")
                    self._append_log(f"  3. ollama run {output_name}")
                    self.status.set_success(f"Merge complete! Output in {out_dir}")
                else:
                    self._append_log(f"\n❌ Merge failed: {result.get('error', 'Unknown error')}")
                    self.status.set_error(f"Merge failed: {result.get('error', '')[:100]}")

            self.after(0, finish)

        threading.Thread(target=do_merge, daemon=True).start()

    def _cancel_merge(self):
        self._cancel_flag = True
        self.status.set_error("Cancelling merge...")

    def _append_log(self, text):
        """Append text to the output preview."""
        current = self.output.get_text()
        self.output.set_text(current + "\n" + text if current else text)
        # Auto-scroll to bottom
        self.output.textbox.see("end")
