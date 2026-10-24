"""Manage the desktop application's private document library."""

from __future__ import annotations

import os
import shutil
import tempfile
import json
from dataclasses import dataclass
from pathlib import Path

from .file_types import TEXT_SUFFIXES
from .index_schema import INDEX_FORMAT_VERSION

SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {".pdf"}
MAX_IMPORT_BYTES = 50 * 1024 * 1024
MAX_EDIT_BYTES = 5 * 1024 * 1024
APP_NAME = "CiteFjord"


@dataclass(frozen=True)
class BatchDeleteResult:
    deleted: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]


def app_home() -> Path:
    configured = os.environ.get("RAG_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        current, legacy = base / APP_NAME, base / "LocalRAGKnowledgeBase"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        current, legacy = base / "citefjord", base / "local-rag-knowledge-base"
    # Continue using an existing private library so the rename does not strand its index.
    return legacy if legacy.is_dir() and not current.exists() else current


def document_dir() -> Path:
    location = app_home() / "documents"
    location.mkdir(parents=True, exist_ok=True)
    return location


def database_dir() -> Path:
    return app_home() / "chroma_db"


def _snapshot() -> dict:
    return {
        "index_format": INDEX_FORMAT_VERSION,
        "files": {path.name: [path.stat().st_size, path.stat().st_mtime_ns] for path in list_documents()},
    }


def index_is_current() -> bool:
    if not (database_dir() / "chroma.sqlite3").is_file():
        return False
    try:
        saved = json.loads((app_home() / "index-state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return saved == _snapshot()


def mark_index_current() -> None:
    home = app_home()
    home.mkdir(parents=True, exist_ok=True)
    target = home / "index-state.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=home, prefix=".index-state-", delete=False) as output:
            temporary = Path(output.name)
            json.dump(_snapshot(), output)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_name(name: str, *, editable: bool = False) -> str:
    if not name or name in {".", ".."} or name.startswith("."):
        raise ValueError("Choose a visible file name")
    if name != Path(name).name or "/" in name or "\\" in name or ":" in name:
        raise ValueError("File name cannot contain a path")
    if len(name) > 200 or any(ord(char) < 32 for char in name):
        raise ValueError("Invalid file name")
    suffix = Path(name).suffix.lower()
    allowed = TEXT_SUFFIXES if editable else SUPPORTED_SUFFIXES
    if suffix not in allowed:
        raise ValueError(f"Unsupported file type: {suffix or '(none)'}")
    return name


def _target(name: str, *, editable: bool = False) -> Path:
    path = document_dir() / validate_name(name, editable=editable)
    if path.is_symlink():
        raise ValueError("Symbolic links are not supported")
    return path


def list_documents() -> list[Path]:
    return sorted(
        (path for path in document_dir().iterdir()
         if path.is_file() and not path.is_symlink() and path.suffix.lower() in SUPPORTED_SUFFIXES),
        key=lambda path: path.name.lower(),
    )


def import_document(source: Path, *, overwrite: bool = False) -> Path:
    source = Path(source).expanduser()
    if source.is_symlink():
        raise ValueError("Choose a regular file")
    source = source.resolve(strict=True)
    if not source.is_file():
        raise ValueError("Choose a regular file")
    target = _target(source.name)
    if source == target:
        return target
    if target.exists() and not overwrite:
        raise FileExistsError(target.name)
    if source.stat().st_size > MAX_IMPORT_BYTES:
        raise ValueError("Files must be 50 MB or smaller")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".import-", delete=False) as output:
            temporary = Path(output.name)
            with source.open("rb") as incoming:
                shutil.copyfileobj(incoming, output)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def read_document(name: str) -> str:
    path = _target(name, editable=True)
    if not path.is_file():
        raise FileNotFoundError(name)
    if path.stat().st_size > MAX_EDIT_BYTES:
        raise ValueError("Files larger than 5 MB cannot be edited in the app")
    return path.read_text(encoding="utf-8")


def save_document(name: str, content: str, *, create: bool = False) -> Path:
    path = _target(name, editable=True)
    if create and path.exists():
        raise FileExistsError(name)
    if not create and not path.is_file():
        raise FileNotFoundError(name)
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_EDIT_BYTES:
        raise ValueError("Files edited in the app must be 5 MB or smaller")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".edit-", delete=False) as output:
            temporary = Path(output.name)
            output.write(encoded)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def delete_document(name: str) -> None:
    path = _target(name)
    path.unlink()


def delete_documents(names: list[str]) -> BatchDeleteResult:
    """Delete selected library copies, reporting each failure independently."""
    deleted: list[str] = []
    failed: list[tuple[str, str]] = []
    for name in dict.fromkeys(names):
        try:
            delete_document(name)
        except (OSError, ValueError) as exc:
            failed.append((name, str(exc)))
        else:
            deleted.append(name)
    return BatchDeleteResult(tuple(deleted), tuple(failed))
