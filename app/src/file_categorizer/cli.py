"""CLI entry point."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console

from file_categorizer.core.config_loader import load_config
from file_categorizer.core.db import Database
from file_categorizer.core.feedback import review_queue
from file_categorizer.core.pipeline import FilePipeline, IMAGE_EXTS, VIDEO_EXTS
from file_categorizer.utils.logger import setup_logging

load_dotenv()

app = typer.Typer(help="Local-first self-learning file categorizer.")
console = Console()

CONFIG_OPT = typer.Option("config/config.yaml", "--config", "-c")


def _build_pipeline(cfg, db, no_metadata: bool = False):
    """Return the metadata-wrapping pipeline unless disabled."""
    metadata_on = bool(cfg.raw.get("metadata", {}).get("enabled", True)) and not no_metadata
    if metadata_on:
        from file_categorizer.core.metadata_db import MetadataDatabase
        from file_categorizer.core.metadata_pipeline import MetadataPipeline

        mdb = MetadataDatabase(cfg.paths.get("database", "data/cache.db"))
        return MetadataPipeline(
            cfg, db, mdb, gemini_key=os.environ.get("GEMINI_API_KEY")
        )
    return FilePipeline(cfg, db)


def _iter_files(root: Path, recursive: bool):
    it = root.rglob("*") if recursive else root.iterdir()
    for p in it:
        if p.is_file() and p.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS):
            yield p


def _print_result(result: dict, dry_run: bool) -> None:
    """Print a compact one-block summary, including metadata when present."""
    status = result.get("status", "?")
    tag = result.get("tag", "")
    conf = result.get("confidence")
    conf_txt = f" ({conf:.0%})" if isinstance(conf, (int, float)) else ""
    name = Path(result.get("path", "")).name
    console.print(f"[bold]{name}[/bold] -> {status} {tag}{conf_txt}")

    if dry_run:
        if status == "duplicate":
            dest = result.get("duplicate_of_path") or "existing"
            console.print(f"    would leave in place (exact duplicate of {Path(str(dest)).name})")
        else:
            dest = result.get("tag", "?")
            console.print(f"    would move to: output/{dest}/")
    elif result.get("moved_to"):
        console.print(f"    moved to: {result['moved_to']}")
    elif status == "duplicate":
        console.print(
            f"    left in place (exact duplicate of "
            f"{Path(str(result.get('duplicate_of_path') or 'existing')).name})"
        )

    dup = result.get("metadata_duplicate") or {}
    if dup.get("is_duplicate"):
        console.print(
            f"    duplicate ({dup.get('reason')}) of "
            f"{str(dup.get('duplicate_of'))[:12]}"
        )

    fields = result.get("metadata_fields") or []
    for f in fields:
        value = f.get("field_value", "")
        src = f.get("source", "")
        console.print(f"    [dim]{f.get('field_name')}:[/dim] {value} [dim][{src}][/dim]")


def _run_index(
    path: Path,
    recursive: bool,
    dry_run: bool,
    review: bool,
    no_metadata: bool,
    config_path: str,
) -> None:
    """Shared implementation for the ``scan`` and ``index`` commands."""
    if not path.exists():
        console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(code=1)

    cfg = load_config(config_path)
    setup_logging(cfg.paths.get("logs", "data/logs"))
    db = Database(cfg.paths.get("database", "data/cache.db"))
    pipeline = _build_pipeline(cfg, db, no_metadata=no_metadata)

    if not os.environ.get("GEMINI_API_KEY"):
        console.print(
            "[dim]No GEMINI_API_KEY set: running fully local "
            "(Gemini fallback disabled).[/dim]"
        )

    targets = [path] if path.is_file() else list(_iter_files(path, recursive))
    if not targets:
        console.print("[yellow]No supported image/video files found.[/yellow]")
    results = []
    for target in targets:
        try:
            result = pipeline.process(target, dry_run=dry_run)
        except Exception as exc:
            result = {"path": str(target), "status": "error", "error": str(exc)}
        results.append(result)
        _print_result(result, dry_run)

    if review:
        threshold = cfg.feedback.get("confidence_threshold", 0.75)
        low = [r for r in results
               if r.get("status") == "classified"
               and r.get("confidence", 1.0) < threshold]
        if low:
            review_queue(low, db)

    if not dry_run and cfg.raw.get("spreadsheet", {}).get("export_after_index", True):
        try:
            from file_categorizer.core.metadata_db import MetadataDatabase
            from file_categorizer.core.spreadsheet import export_workbook
            target_wb = cfg.raw.get("spreadsheet", {}).get(
                "workbook_path", "output/metadata.xlsx"
            )
            mdb = MetadataDatabase(cfg.paths.get("database", "data/cache.db"))
            mdb.init_schema()
            path_wb = export_workbook(mdb, target_wb)
            console.print(f"[dim]Exported workbook to {path_wb}[/dim]")
        except Exception as exc:
            console.print(f"[dim]Workbook export skipped: {exc}[/dim]")

    errors = [r for r in results if r.get("status") == "error"]
    console.print(f"Done: {len(results)} file(s), {len(errors)} error(s).")
    db.close()


@app.command()
def scan(
    path: Path = typer.Argument(..., help="File or folder to scan"),
    recursive: bool = typer.Option(False, "--recursive", "-r"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    review: bool = typer.Option(False, "--review"),
    no_metadata: bool = typer.Option(False, "--no-metadata", help="Skip OCR/VLM extraction"),
    config_path: str = CONFIG_OPT,
):
    """Classify, sort and index files (extracts metadata, EXIF, and duplicates)."""
    _run_index(path, recursive, dry_run, review, no_metadata, config_path)


@app.command()
def index(
    path: Path = typer.Argument(..., help="File or folder to index"),
    recursive: bool = typer.Option(False, "--recursive", "-r"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    review: bool = typer.Option(False, "--review"),
    no_metadata: bool = typer.Option(False, "--no-metadata", help="Skip OCR/VLM extraction"),
    config_path: str = CONFIG_OPT,
):
    """Same as ``scan``: classify, sort and index files."""
    _run_index(path, recursive, dry_run, review, no_metadata, config_path)

@app.command()
def review(config_path: str = CONFIG_OPT):
    """Review saved corrections."""
    cfg = load_config(config_path)
    db = Database(cfg.paths.get("database", "data/cache.db"))
    rows = db.conn.execute(
        "SELECT * FROM corrections ORDER BY id DESC LIMIT 100"
    ).fetchall()
    for r in rows:
        console.print(dict(r))
    db.close()


@app.command()
def stats(config_path: str = CONFIG_OPT):
    """Show cache + correction + metadata stats."""
    from file_categorizer.core.metadata_db import MetadataDatabase

    cfg = load_config(config_path)
    db = Database(cfg.paths.get("database", "data/cache.db"))
    counts = {
        "cached": db.conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0],
        "corrections": db.conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0],
        "patterns": db.conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0],
    }
    mdb = MetadataDatabase(cfg.paths.get("database", "data/cache.db"))
    mdb.init_schema()
    counts.update({
        "meta_files": len(mdb.all_files()),
        "meta_entities": len(mdb.all_entities()),
        "meta_fields": mdb.count_rows("meta_extracted_fields"),
        "meta_links": mdb.count_rows("meta_file_entities"),
        "meta_exports": mdb.count_rows("meta_exports"),
        "meta_corrections": mdb.count_rows("meta_field_corrections"),
    })
    console.print(json.dumps(counts, indent=2))
    db.close()


@app.command("review-metadata")
def review_metadata(
    limit: int = typer.Option(20, "--limit", "-n", help="How many rows to show"),
    needs_review: bool = typer.Option(
        False, "--needs-review", help="Only rows flagged for review"
    ),
    config_path: str = CONFIG_OPT,
):
    """Show stored metadata rows (newest first) with their extracted fields."""
    from file_categorizer.core.metadata_db import MetadataDatabase

    cfg = load_config(config_path)
    mdb = MetadataDatabase(cfg.paths.get("database", "data/cache.db"))
    mdb.init_schema()

    rows = mdb.all_files()
    if needs_review:
        rows = [r for r in rows if r["needs_review"]]
    rows = rows[:limit]
    if not rows:
        console.print("No metadata rows.")
        return

    for r in rows:
        fields = mdb.get_fields(r["file_hash"])
        joined = ", ".join(
            f"{f['field_name']}={f['field_value']}" for f in fields
        ) or "(no fields)"
        flag = " [needs review]" if r["needs_review"] else ""
        console.print(
            f"[bold]{str(r['file_hash'])[:12]}[/bold]  "
            f"{r['category'] or '?':<16}{flag}  {Path(r['file_path']).name}"
        )
        console.print(f"    {joined}")


@app.command()
def export(
    workbook: Optional[str] = typer.Option(None, "--workbook", "-w"),
    config_path: str = CONFIG_OPT,
):
    """Build or update the Excel workbook from the metadata tables."""
    from file_categorizer.core.metadata_db import MetadataDatabase
    from file_categorizer.core.spreadsheet import export_workbook

    cfg = load_config(config_path)
    target = workbook or cfg.raw.get("spreadsheet", {}).get(
        "workbook_path", "output/metadata.xlsx"
    )
    mdb = MetadataDatabase(cfg.paths.get("database", "data/cache.db"))
    mdb.init_schema()
    path = export_workbook(mdb, target)
    console.print(f"Wrote {path}")


@app.command()
def duplicates(
    phash_threshold: int = typer.Option(6, "--phash-threshold", "-t"),
    no_perceptual: bool = typer.Option(False, "--no-perceptual"),
    config_path: str = CONFIG_OPT,
):
    """Scan for exact and perceptual duplicate groups."""
    from file_categorizer.core.metadata_db import MetadataDatabase
    from file_categorizer.core.duplicates import scan_duplicates, group_summary

    cfg = load_config(config_path)
    mdb = MetadataDatabase(cfg.paths.get("database", "data/cache.db"))
    mdb.init_schema()
    groups = scan_duplicates(
        mdb,
        phash_threshold=phash_threshold,
        include_perceptual=not no_perceptual,
    )
    summary = group_summary(groups)
    console.print(
        json.dumps(
            {
                "groups": summary["groups"],
                "exact_groups": summary["exact_groups"],
                "perceptual_groups": summary["perceptual_groups"],
                "files": summary["files"],
                "reclaimable_bytes": summary["reclaimable"],
            },
            indent=2,
        )
    )
    for g in groups[:50]:
        console.print(
            f"[bold]{g.group_id}[/bold] ({g.kind}) keep={Path(g.keep_path).name} "
            f"copies={len(g.files)} reclaimable={summary['reclaimable'] if False else ''}"
        )
        for f in g.files:
            mark = "KEEP" if f.is_keep else "DUP"
            console.print(f"  [{mark}] {f.file_path}")


if __name__ == "__main__":
    app()
