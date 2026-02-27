"""
Model Merger — Merges two+ models using mergekit.

Supports:
  - SLERP (Spherical Linear Interpolation) — smooth blend of two models
  - Linear — weighted average of model weights
  - TIES — Task-Informed Expert Selection (resolves interference)
  - DARE — Drop And REscale (sparse merge, keeps best of both)
  - Passthrough (Frankenmerge) — stack layers from different models

Flow:
  1. User picks 2+ models (Ollama names or HF model IDs)
  2. We generate a mergekit YAML config
  3. Run mergekit-yaml to produce merged model
  4. Convert to GGUF with llama.cpp
  5. Import to Ollama via Modelfile

Requirements:
  pip install mergekit
  (optionally) llama.cpp for GGUF conversion
"""
import os
import subprocess
import shutil
import yaml
import threading
from config import DATA_DIR


MERGE_DIR = os.path.join(DATA_DIR, "merges")
os.makedirs(MERGE_DIR, exist_ok=True)

# ─── Merge method descriptions ─────────────────────────────

MERGE_METHODS = {
    "slerp": {
        "name": "SLERP",
        "description": (
            "Spherical Linear Interpolation — the gold standard for merging two models.\n"
            "Smoothly blends the weight spaces. Great for combining a base model\n"
            "with a fine-tuned variant. Only works with exactly 2 models."
        ),
        "min_models": 2,
        "max_models": 2,
    },
    "linear": {
        "name": "Linear",
        "description": (
            "Weighted average of model weights. Simple but effective.\n"
            "Works with 2+ models. Each model gets a weight (e.g. 0.6 / 0.4).\n"
            "Good when you want a bit of everything."
        ),
        "min_models": 2,
        "max_models": 10,
    },
    "ties": {
        "name": "TIES",
        "description": (
            "Task-Informed Expert Selection — resolves interference between models.\n"
            "Trims redundant changes, resolves sign conflicts, then merges.\n"
            "Best when merging models that were fine-tuned for different tasks."
        ),
        "min_models": 2,
        "max_models": 10,
    },
    "dare_ties": {
        "name": "DARE-TIES",
        "description": (
            "Drop And REscale + TIES — randomly drops some delta weights\n"
            "before merging, then rescales. Produces cleaner merges with\n"
            "less interference. Good for combining specialized models."
        ),
        "min_models": 2,
        "max_models": 10,
    },
    "passthrough": {
        "name": "Passthrough (Frankenmerge)",
        "description": (
            "Stack layers from different models sequentially.\n"
            "Can create a larger model from smaller ones (e.g. two 7Bs → ~14B).\n"
            "Experimental — results vary. Same architecture required."
        ),
        "min_models": 2,
        "max_models": 5,
    },
}


def get_ollama_model_path(model_name: str) -> str | None:
    """Find the local file path for an Ollama model's weights."""
    try:
        result = subprocess.run(
            ["ollama", "show", model_name, "--modelfile"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("FROM ") and not line.startswith("FROM http"):
                    path = line[5:].strip()
                    if os.path.exists(path):
                        return path
    except Exception:
        pass
    return None


def generate_merge_config(
    models: list[dict],
    method: str = "slerp",
    base_model: str | None = None,
    output_name: str = "merged_model",
    parameters: dict | None = None,
) -> tuple[str, str]:
    """
    Generate a mergekit YAML config.

    Args:
        models: List of dicts with 'name' (HF ID or path) and 'weight' (0.0-1.0)
        method: One of the MERGE_METHODS keys
        base_model: For TIES/DARE — the reference base model
        output_name: Name for the output
        parameters: Extra params (e.g. density for DARE)

    Returns:
        (yaml_string, config_path) — the config content and where it was saved
    """
    if parameters is None:
        parameters = {}

    config = {"merge_method": method, "models": []}

    if method == "slerp":
        # SLERP takes exactly 2 models with a 't' parameter (blend factor)
        t = models[0].get("weight", 0.5) if models else 0.5
        config["parameters"] = {"t": t}
        config["base_model"] = models[0]["name"]
        config["models"] = [
            {"model": models[0]["name"]},
            {"model": models[1]["name"]},
        ]

    elif method == "linear":
        for m in models:
            config["models"].append({
                "model": m["name"],
                "parameters": {"weight": m.get("weight", 1.0 / len(models))},
            })

    elif method in ("ties", "dare_ties"):
        config["base_model"] = base_model or models[0]["name"]
        config["parameters"] = {
            "density": parameters.get("density", 0.5),
            "normalize": True,
        }
        for m in models:
            config["models"].append({
                "model": m["name"],
                "parameters": {"weight": m.get("weight", 1.0)},
            })

    elif method == "passthrough":
        config["models"] = []
        for m in models:
            config["models"].append({
                "model": m["name"],
            })

    config["dtype"] = parameters.get("dtype", "float16")

    yaml_str = yaml.dump(config, default_flow_style=False, sort_keys=False)

    config_path = os.path.join(MERGE_DIR, f"{output_name}_config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(yaml_str)

    return yaml_str, config_path


def run_merge(
    config_path: str,
    output_name: str = "merged_model",
    on_progress=None,
    should_cancel=None,
) -> dict:
    """
    Run mergekit-yaml to merge models.

    Returns:
        dict with 'success', 'output_dir', 'error'
    """
    output_dir = os.path.join(MERGE_DIR, output_name)
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "mergekit-yaml", config_path, output_dir,
        "--copy-tokenizer",
        "--allow-crimes",  # allow experimental merges
        "--lazy-unpickle",
    ]

    if on_progress:
        on_progress(f"Running: {' '.join(cmd)}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        output_lines = []
        for line in process.stdout:
            line = line.rstrip()
            output_lines.append(line)
            if on_progress:
                on_progress(line)
            if should_cancel and should_cancel():
                process.kill()
                return {"success": False, "error": "Cancelled by user", "output_dir": output_dir}

        process.wait()

        if process.returncode == 0:
            return {"success": True, "output_dir": output_dir, "error": None}
        else:
            return {
                "success": False,
                "output_dir": output_dir,
                "error": "\n".join(output_lines[-10:]),
            }

    except FileNotFoundError:
        return {
            "success": False,
            "output_dir": output_dir,
            "error": "mergekit not found. Install with: pip install mergekit",
        }
    except Exception as e:
        return {"success": False, "output_dir": output_dir, "error": str(e)}


def convert_to_gguf(
    model_dir: str,
    output_name: str = "merged",
    quantization: str = "q4_k_m",
    on_progress=None,
) -> dict:
    """Convert a merged model to GGUF format using llama.cpp's convert script."""
    gguf_dir = os.path.join(MERGE_DIR, f"{output_name}_gguf")
    os.makedirs(gguf_dir, exist_ok=True)
    gguf_path = os.path.join(gguf_dir, f"{output_name}.{quantization}.gguf")

    # Try llama-quantize or python convert
    # First: convert to f16 gguf
    convert_cmd = ["python", "-m", "llama_cpp.convert", model_dir, "--outfile",
                   os.path.join(gguf_dir, f"{output_name}.f16.gguf")]

    if on_progress:
        on_progress(f"Converting to GGUF: {output_name}")

    # The user will likely need to handle this step manually
    # since llama.cpp setup varies. Generate the commands.
    commands = {
        "convert": f"python convert_hf_to_gguf.py {model_dir} --outfile {gguf_path}",
        "quantize": f"llama-quantize {gguf_dir}/{output_name}.f16.gguf {gguf_path} {quantization}",
    }

    return {
        "gguf_dir": gguf_dir,
        "gguf_path": gguf_path,
        "commands": commands,
    }


def generate_modelfile(
    model_path: str,
    output_name: str = "merged_model",
    system_prompt: str = "",
) -> str:
    """Generate an Ollama Modelfile for the merged model."""
    modelfile = f"""# Ollama Modelfile — Merged Model
# Generated by LoRA Data Toolkit Model Merger

FROM {model_path}

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 8192
"""
    if system_prompt:
        modelfile += f'\nSYSTEM """{system_prompt}"""\n'

    modelfile_path = os.path.join(MERGE_DIR, f"{output_name}_Modelfile")
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(modelfile)

    return modelfile_path
