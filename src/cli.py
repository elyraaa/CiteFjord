"""Typer/Rich command-line interface for CiteFjord."""

from __future__ import annotations

import re
import statistics
from pathlib import Path
from time import perf_counter
from typing import NoReturn

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from .config import DEFAULT_DB
from .ingest import IngestResult, ingest_folder
from .retriever import Source, ask as answer_question, open_index, search_index


app = typer.Typer(help="Search your local engineering documents with Ollama.", no_args_is_help=True, add_completion=False)
console = Console()


def _fail(exc: Exception) -> NoReturn:
    console.print(Text(f"Error: {exc}", style="bold red"))
    raise typer.Exit(code=1)


def _index_table(result: IngestResult, elapsed: float) -> Table:
    table = Table(title="Indexing result")
    table.add_column("Measure")
    table.add_column("Value", justify="right")
    for label, value in (
        ("Files scanned", result.scanned),
        ("Files indexed", result.indexed),
        ("Files unchanged", result.unchanged),
        ("Files removed", result.removed),
        ("Chunks stored", result.chunks_added),
    ):
        table.add_row(label, str(value))
    table.add_row("Elapsed", f"{elapsed:.2f} s")
    return table


def _source_table(sources: tuple[Source, ...], answer: str) -> tuple[Table, set[int]]:
    cited = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    valid = {source.number for source in sources}
    displayed = [source for source in sources if source.number in cited] or list(sources)
    table = Table(title="Cited sources" if cited & valid else "Retrieved sources")
    table.add_column("#", justify="right")
    table.add_column("File", overflow="fold")
    table.add_column("Page", justify="right")
    table.add_column("Cosine distance", justify="right")
    for source in displayed:
        table.add_row(
            str(source.number),
            Text(source.relative_path),
            str(source.page) if source.page is not None else "-",
            f"{source.distance:.3f}",
        )
    return table, cited - valid


@app.command()
def ingest(
    folder: Path = typer.Argument(..., help="Folder of documents to index"),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="ChromaDB directory"),
    offline: bool = typer.Option(False, "--offline", help="Use only the cached embedding model"),
) -> None:
    """Index documents, updating changed files and removing deleted files."""
    try:
        start = perf_counter()
        result = ingest_folder(folder, db, offline=offline)
        console.print(_index_table(result, perf_counter() - start))
    except (OSError, ValueError, RuntimeError) as exc:
        _fail(exc)


@app.command()
def ask(
    query: str = typer.Argument(..., help="Question about indexed documents"),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="ChromaDB directory"),
    k: int = typer.Option(4, "--k", min=1, help="Number of chunks to retrieve"),
) -> None:
    """Answer from retrieved context using local Ollama."""
    try:
        result = answer_question(query, db_path=db, k=k)
        console.print(Markdown(result.answer))
        if result.sources:
            table, unknown_citations = _source_table(result.sources, result.answer)
            console.print(table)
            if unknown_citations:
                console.print(Text("Answer contains a citation number absent from the retrieved sources.", style="yellow"))
    except (OSError, ValueError, RuntimeError) as exc:
        _fail(exc)


@app.command()
def stats(
    folder: Path = typer.Argument(..., help="Folder to index before benchmarking"),
    query: str = typer.Argument(..., help="Question used for retrieval timing"),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="ChromaDB directory"),
    k: int = typer.Option(4, "--k", min=1, help="Number of chunks to retrieve"),
    runs: int = typer.Option(3, "--runs", min=1, help="Number of retrieval timing runs"),
    offline: bool = typer.Option(False, "--offline", help="Use only the cached embedding model during indexing"),
) -> None:
    """Measure indexing wall time and query-embedding plus search latency."""
    try:
        if not query.strip():
            raise ValueError("Question cannot be empty")
        start = perf_counter()
        indexed = ingest_folder(folder, db, offline=offline)
        indexing_seconds = perf_counter() - start

        start = perf_counter()
        store = open_index(db)
        setup_seconds = perf_counter() - start
        latencies = []
        sources: tuple[Source, ...] = ()
        for _ in range(runs):
            sources, seconds = search_index(store, query, k=k)
            latencies.append(seconds)

        table = Table(title="CiteFjord benchmark")
        table.add_column("Measure")
        table.add_column("Value", justify="right")
        for label, value in (
            ("Files scanned", str(indexed.scanned)),
            ("Files newly indexed", str(indexed.indexed)),
            ("Files unchanged", str(indexed.unchanged)),
            ("Files removed", str(indexed.removed)),
            ("Chunks stored", str(indexed.chunks_added)),
            ("Chunks retrieved", str(len(sources))),
            ("Indexing wall time (includes model load)", f"{indexing_seconds:.3f} s"),
            ("Retriever setup (includes model load)", f"{setup_seconds:.3f} s"),
            (f"Retrieval median ({runs} {'run' if runs == 1 else 'runs'})", f"{statistics.median(latencies):.3f} s"),
            ("Retrieval minimum", f"{min(latencies):.3f} s"),
            ("Retrieval maximum", f"{max(latencies):.3f} s"),
        ):
            table.add_row(label, value)
        console.print(table)
        console.print("Retrieval timings include query embedding and Chroma search, after the model and index are loaded.")
    except (OSError, ValueError, RuntimeError) as exc:
        _fail(exc)


if __name__ == "__main__":
    app()
