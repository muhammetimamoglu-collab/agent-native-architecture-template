from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import track

from semantic_search.chunker import chunk_file
from semantic_search.config import settings
from semantic_search.embedders import get_embedder
from semantic_search.store import (
    delete_file_chunks,
    ensure_collection,
    upsert_chunks_smart,
)

docs_app = typer.Typer(
    name="index-docs",
    help="Index documentation files (docs_index collection).",
    no_args_is_help=True,
)
code_app = typer.Typer(
    name="index-code",
    help="Index source code files (code_index collection).",
    no_args_is_help=True,
)

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Return the git repository root (one level above .semantic-search/)."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    # Fallback: assume .semantic-search/ is one level inside the repo
    return Path(__file__).parent.parent.parent


def _discover_files(root: Path, extensions: list[str]) -> list[Path]:
    exts = {e.lower() for e in extensions}
    exclude = set(settings.index_exclude)
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in exclude for part in path.parts):
            continue
        if path.suffix.lower() in exts:
            found.append(path)
    return sorted(found)


def _run_index(
    paths: list[Path],
    repo_root: Path,
    collection_name: str,
    is_code: bool,
    force: bool,
) -> list[tuple[str, str]]:
    embedder = get_embedder()
    ensure_collection(collection_name, embedder.vector_size)

    total_indexed = 0
    total_skipped = 0
    failures: list[tuple[str, str]] = []

    for path in track(paths, description="Indexing..."):
        try:
            rel = path.relative_to(repo_root).as_posix()
        except ValueError:
            rel = path.as_posix()

        try:
            chunks = chunk_file(path, rel, is_code=is_code)
            if not chunks:
                continue

            if force:
                # Force: skip hash check â€” delete existing chunks and upsert all
                delete_file_chunks(rel, collection_name)
                result = upsert_chunks_smart(chunks, embedder, collection_name)
                total_indexed += result["indexed"]
            else:
                result = upsert_chunks_smart(chunks, embedder, collection_name)
                total_indexed += result["indexed"]
                total_skipped += result["skipped"]
        except Exception as exc:
            failures.append((rel, str(exc)))
            console.print(f"[red]Failed:[/red] {rel} - {exc}")

    if force:
        console.print(
            f"[green]Done:[/green] {total_indexed} chunks written (force mode, "
            f"hash-check skipped) into [bold]{collection_name}[/bold]."
        )
    else:
        console.print(
            f"[green]Done:[/green] {total_indexed} chunks indexed, "
            f"{total_skipped} skipped (unchanged) in [bold]{collection_name}[/bold]."
        )

    if failures:
        console.print(f"[red]Failures:[/red] {len(failures)} file(s) could not be indexed.")
        for rel, error in failures:
            console.print(f"  - {rel}: {error}")

    return failures


# ---------------------------------------------------------------------------
# docs_app commands
# ---------------------------------------------------------------------------

@docs_app.command("full")
def docs_full(
    force: bool = typer.Option(False, "--force", help="Bypass hash-check, rewrite all chunks."),
) -> None:
    """Index all documentation files under DOCS_ROOT."""
    repo_root = _repo_root()
    docs_root = (repo_root / settings.docs_root).resolve()

    if not docs_root.exists():
        console.print(f"[yellow]DOCS_ROOT '{docs_root}' does not exist. Nothing to index.[/yellow]")
        raise typer.Exit(0)

    paths = _discover_files(docs_root, settings.index_extensions_docs)
    console.print(f"[blue]Full docs index:[/blue] {len(paths)} files found in {docs_root}")
    failures = _run_index(paths, repo_root, settings.docs_collection, is_code=False, force=force)
    if failures:
        raise typer.Exit(1)


@docs_app.command("files")
def docs_files(
    file_paths: list[str] = typer.Argument(..., help="Relative paths of files to re-index."),
    force: bool = typer.Option(False, "--force", help="Bypass hash-check."),
) -> None:
    """Incrementally re-index specific documentation files."""
    repo_root = _repo_root()
    exts = {e.lower() for e in settings.index_extensions_docs}
    paths = [
        repo_root / fp
        for fp in file_paths
        if (repo_root / fp).exists() and Path(fp).suffix.lower() in exts
    ]
    if not paths:
        console.print("[yellow]No matching docs files to index.[/yellow]")
        raise typer.Exit(0)
    console.print(f"[blue]Incremental docs index:[/blue] {len(paths)} file(s)")
    failures = _run_index(paths, repo_root, settings.docs_collection, is_code=False, force=force)
    if failures:
        raise typer.Exit(1)


@docs_app.command("delete")
def docs_delete(
    file_paths: list[str] = typer.Argument(..., help="Relative paths of files to remove from index."),
) -> None:
    """Remove specific documentation files from the index (e.g. after rename or deletion)."""
    for fp in file_paths:
        try:
            rel = Path(fp).as_posix()
            delete_file_chunks(rel, settings.docs_collection)
            console.print(f"[green]Deleted chunks for[/green] {rel}")
        except Exception as exc:
            console.print(f"[red]Failed to delete {fp}: {exc}[/red]")


# ---------------------------------------------------------------------------
# code_app commands
# ---------------------------------------------------------------------------

@code_app.command("full")
def code_full(
    force: bool = typer.Option(False, "--force", help="Bypass hash-check, rewrite all chunks."),
) -> None:
    """Index all source code files under CODE_ROOT."""
    repo_root = _repo_root()
    code_root = (repo_root / settings.code_root).resolve()

    if not code_root.exists():
        console.print(f"[yellow]CODE_ROOT '{code_root}' does not exist. Nothing to index.[/yellow]")
        raise typer.Exit(0)

    paths = _discover_files(code_root, settings.index_extensions_code)
    console.print(f"[blue]Full code index:[/blue] {len(paths)} files found in {code_root}")
    failures = _run_index(paths, repo_root, settings.code_collection, is_code=True, force=force)
    if failures:
        raise typer.Exit(1)


@code_app.command("files")
def code_files(
    file_paths: list[str] = typer.Argument(..., help="Relative paths of files to re-index."),
    force: bool = typer.Option(False, "--force", help="Bypass hash-check."),
) -> None:
    """Incrementally re-index specific source code files."""
    repo_root = _repo_root()
    exts = {e.lower() for e in settings.index_extensions_code}
    paths = [
        repo_root / fp
        for fp in file_paths
        if (repo_root / fp).exists() and Path(fp).suffix.lower() in exts
    ]
    if not paths:
        console.print("[yellow]No matching code files to index.[/yellow]")
        raise typer.Exit(0)
    console.print(f"[blue]Incremental code index:[/blue] {len(paths)} file(s)")
    failures = _run_index(paths, repo_root, settings.code_collection, is_code=True, force=force)
    if failures:
        raise typer.Exit(1)


@code_app.command("delete")
def code_delete(
    file_paths: list[str] = typer.Argument(..., help="Relative paths of files to remove from index."),
) -> None:
    """Remove specific source code files from the index (e.g. after rename or deletion)."""
    for fp in file_paths:
        try:
            rel = Path(fp).as_posix()
            delete_file_chunks(rel, settings.code_collection)
            console.print(f"[green]Deleted chunks for[/green] {rel}")
        except Exception as exc:
            console.print(f"[red]Failed to delete {fp}: {exc}[/red]")
