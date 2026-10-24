"""Check the Python environment and local Ollama model for CiteFjord."""

from __future__ import annotations

import importlib
import json
import sys
import urllib.error
import urllib.request


PACKAGES = {
    "typer": "typer",
    "rich": "rich",
    "chromadb": "chromadb",
    "langchain": "langchain",
    "langchain-community": "langchain_community",
    "langchain-huggingface": "langchain_huggingface",
    "langchain-chroma": "langchain_chroma",
    "langchain-text-splitters": "langchain_text_splitters",
    "pymupdf": "pymupdf",
    "sentence-transformers": "sentence_transformers",
}

MODEL = "qwen2.5-coder:7b"


def main() -> int:
    print(f"Python: {sys.version.split()[0]}")
    missing = []
    for package, module in PACKAGES.items():
        try:
            importlib.import_module(module)
            print(f"[OK] {package}")
        except Exception as exc:
            print(f"[MISSING] {package}: {exc}")
            missing.append(package)

    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            models = json.load(response).get("models", [])
        names = {name for model in models for name in (model.get("name"), model.get("model")) if name}
        if MODEL in names:
            print(f"[OK] Ollama model: {MODEL}")
        else:
            print(f"[PENDING] Ollama is running; {MODEL} is not listed yet")
            return 1
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"[MISSING] Ollama API: {exc}")
        return 1

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
