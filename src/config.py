"""Shared local model and database settings."""

from __future__ import annotations

import os
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get("RAG_DB_DIR", PROJECT_ROOT / "chroma_db"))
MODEL_NAME = "BAAI/bge-small-en-v1.5"
OLLAMA_MODEL = "qwen2.5-coder:7b"
COLLECTION_NAME = "engineering_knowledge"


def make_embeddings(*, offline: bool) -> HuggingFaceEmbeddings:
    """Load the same normalized embedding model for indexing and querying."""
    cache_dir = Path(os.environ.get("RAG_MODEL_CACHE", PROJECT_ROOT / "model_cache"))
    os.environ.setdefault("HF_HOME", str(cache_dir))
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return HuggingFaceEmbeddings(
        model=MODEL_NAME,
        cache_folder=str(cache_dir),
        model_kwargs={"local_files_only": offline},
        encode_kwargs={"normalize_embeddings": True},
    )
