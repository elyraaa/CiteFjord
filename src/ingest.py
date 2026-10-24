r"""Incrementally index local text, source code, and PDFs in ChromaDB.

Run from the project directory:
    .venv\Scripts\python.exe -m src.ingest PATH_TO_DOCUMENTS
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
import pymupdf

from .config import COLLECTION_NAME, DEFAULT_DB, MODEL_NAME, make_embeddings
from .file_types import TEXT_SUFFIXES
from .index_schema import INDEX_FORMAT_VERSION

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
BATCH_SIZE = 32

CODE_LANGUAGES = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".jsx": Language.JS,
    ".ts": Language.TS,
    ".tsx": Language.TS,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".java": Language.JAVA,
    ".kt": Language.KOTLIN,
    ".c": Language.C,
    ".h": Language.C,
    ".cpp": Language.CPP,
    ".hpp": Language.CPP,
    ".cs": Language.CSHARP,
    ".php": Language.PHP,
    ".rb": Language.RUBY,
    ".ps1": Language.POWERSHELL,
    ".html": Language.HTML,
}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "chroma_db", "model_cache"}


@dataclass(frozen=True)
class IngestResult:
    scanned: int = 0
    indexed: int = 0
    unchanged: int = 0
    removed: int = 0
    chunks_added: int = 0


def _source(path: Path) -> str:
    """Use one stable key for a file regardless of relative input spelling."""
    return os.path.normcase(str(path.resolve()))


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    value = f"{INDEX_FORMAT_VERSION}\0{_source(path)}\0{stat.st_mtime_ns}\0{stat.st_size}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pdf_documents(path: Path) -> list[Document]:
    """Read native PDF text and OCR only pages whose text is image based."""
    documents = PyMuPDFLoader(str(path)).load()
    sparse = [document for document in documents if len(document.page_content.strip()) < 40]
    if not sparse:
        return documents
    packaged_root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    tessdata = Path(os.environ.get("RAG_TESSDATA", packaged_root / "tessdata"))
    if not (tessdata / "eng.traineddata").is_file():
        raise FileNotFoundError(f"English OCR data is missing from {tessdata}")
    with pymupdf.open(path) as pdf:
        for document in sparse:
            page_number = document.metadata.get("page")
            if not isinstance(page_number, int):
                continue
            page = pdf[page_number]
            if not page.get_images():
                continue
            raw_ocr = page.get_textpage_ocr(language="eng", dpi=240, full=True, tessdata=str(tessdata)).extractText()
            recognized = "\n".join(
                line.strip() for line in raw_ocr.splitlines()
                if len(re.findall(r"\w", line, flags=re.UNICODE)) >= 4
            )
            if len(recognized.strip()) > len(document.page_content.strip()):
                document.page_content = recognized
    return documents


def _is_indexable(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return not any(part.startswith(".") or part in SKIP_DIRS for part in relative.parts[:-1]) and not relative.name.startswith(".")


def _splitter(path: Path) -> RecursiveCharacterTextSplitter:
    options = dict(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True)
    language = CODE_LANGUAGES.get(path.suffix.lower())
    if language is not None:
        return RecursiveCharacterTextSplitter.from_language(language, **options)
    return RecursiveCharacterTextSplitter(**options)


def _chunks(path: Path, root: Path, fingerprint: str, documents: list[Document]) -> list[Document]:
    split = _splitter(path).split_documents(documents)
    source = _source(path)
    source_root = _source(root)
    result = []
    for index, document in enumerate(split):
        if not document.page_content.strip():
            continue
        metadata = {
            "source": source,
            "source_root": source_root,
            "file_name": path.name,
            "file_fingerprint": fingerprint,
            "chunk_index": index,
            "start_index": document.metadata.get("start_index", 0),
        }
        if isinstance(document.metadata.get("page"), int):
            metadata["page"] = document.metadata["page"]
        result.append(Document(page_content=document.page_content, metadata=metadata))
    for document in result:
        document.metadata["chunk_count"] = len(result)
    return result


def _is_complete(entries: list[tuple[str, dict]], fingerprint: str) -> bool:
    if not entries:
        return False
    count = len(entries)
    return all(meta.get("file_fingerprint") == fingerprint and meta.get("chunk_count") == count for _, meta in entries) and {
        meta.get("chunk_index") for _, meta in entries
    } == set(range(count))


def _existing_by_source(store: Chroma, root: Path) -> dict[str, list[tuple[str, dict]]]:
    found = store.get(where={"source_root": _source(root)}, include=["metadatas"])
    grouped: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for chunk_id, metadata in zip(found["ids"], found["metadatas"]):
        if metadata and metadata.get("source"):
            grouped[metadata["source"]].append((chunk_id, metadata))
    return grouped


def ingest_folder(folder: Path, db_path: Path = DEFAULT_DB, *, offline: bool = False) -> IngestResult:
    root = folder.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    db_path = db_path.expanduser().resolve()
    if db_path == root:
        raise ValueError("The database directory must differ from the document folder")

    embeddings = make_embeddings(offline=offline)
    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(db_path),
        collection_metadata={"hnsw:space": "cosine", "embedding_model": MODEL_NAME},
    )
    collection_metadata = store._collection.metadata or {}
    if collection_metadata.get("embedding_model") != MODEL_NAME or collection_metadata.get("hnsw:space") != "cosine":
        raise ValueError("Existing Chroma collection uses a different embedding model or distance metric")
    old_by_source = _existing_by_source(store, root)
    seen: set[str] = set()
    scanned = indexed = unchanged = removed = chunks_added = 0

    def process(path: Path, documents: list[Document]) -> None:
        nonlocal scanned, indexed, unchanged, chunks_added
        if not _is_indexable(path, root):
            return
        source = _source(path)
        if source in seen:
            return
        seen.add(source)
        scanned += 1
        fingerprint = _fingerprint(path)
        old_entries = old_by_source.get(source, [])
        if _is_complete(old_entries, fingerprint):
            unchanged += 1
            return

        chunks = _chunks(path, root, fingerprint, documents)
        if path.suffix.lower() == ".pdf" and not chunks:
            raise ValueError(f"No extractable text in {path.name}. This PDF may require OCR before indexing.")
        new_ids = [hashlib.sha256(f"{source}\0{fingerprint}\0{i}".encode("utf-8")).hexdigest() for i in range(len(chunks))]
        for offset in range(0, len(chunks), BATCH_SIZE):
            store.add_documents(chunks[offset : offset + BATCH_SIZE], ids=new_ids[offset : offset + BATCH_SIZE])
        new_id_set = set(new_ids)
        stale_ids = [chunk_id for chunk_id, _ in old_entries if chunk_id not in new_id_set]
        if stale_ids:
            store.delete(ids=stale_ids)
        indexed += 1
        chunks_added += len(chunks)

    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and _is_indexable(path, root):
            source = _source(path)
            fingerprint = _fingerprint(path)
            old_entries = old_by_source.get(source, [])
            if _is_complete(old_entries, fingerprint):
                seen.add(source)
                scanned += 1
                unchanged += 1
                continue
            process(path, TextLoader(str(path), encoding="utf-8", autodetect_encoding=True).load())

    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() == ".pdf" and _is_indexable(path, root):
            source = _source(path)
            fingerprint = _fingerprint(path)
            old_entries = old_by_source.get(source, [])
            if _is_complete(old_entries, fingerprint):
                seen.add(source)
                scanned += 1
                unchanged += 1
                continue
            try:
                process(path, _pdf_documents(path))
            except Exception as exc:
                raise RuntimeError(f"Could not index {path.name}: {exc}") from exc

    for source, entries in old_by_source.items():
        if source not in seen:
            store.delete(ids=[chunk_id for chunk_id, _ in entries])
            removed += 1

    return IngestResult(scanned, indexed, unchanged, removed, chunks_added)


def main() -> None:
    parser = argparse.ArgumentParser(description="Index a local folder in ChromaDB")
    parser.add_argument("folder", type=Path, help="Folder of Markdown, text, code, and PDF files")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="ChromaDB directory")
    parser.add_argument("--offline", action="store_true", help="Use only the cached embedding model")
    args = parser.parse_args()
    result = ingest_folder(args.folder, args.db, offline=args.offline)
    print(
        f"Scanned {result.scanned} files: indexed {result.indexed}, "
        f"unchanged {result.unchanged}, removed {result.removed}; "
        f"stored {result.chunks_added} new chunks."
    )


if __name__ == "__main__":
    main()
