"""sfdigest command line: collect, digest, run."""

from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from sfdigest.connect import ConnectError, get_session
from sfdigest.digest import build_digest
from sfdigest.models import Digest, Settings
from sfdigest.queries import MAX_DAYS, data_decl
from sfdigest.report.render import write_outputs
from sfdigest.snapshot import SnapshotError

app = typer.Typer(help="Read-only digest of Salesforce setup changes.")

OrgOpt = Annotated[str, typer.Option("--org", help="Salesforce CLI org alias or username.")]
DaysOpt = Annotated[
    int, typer.Option("--days", min=1, max=MAX_DAYS, help="How many days back to read.")
]
SettingsOpt = Annotated[
    Path | None,
    typer.Option("--settings", exists=True, dir_okay=False, help="Optional settings.yaml."),
]
SnapshotArg = Annotated[
    Path, typer.Argument(exists=True, file_okay=False, help="Snapshot directory.")
]
SnapshotsOpt = Annotated[Path, typer.Option("--snapshots", help="Where snapshots are written.")]
ReportsOpt = Annotated[Path, typer.Option("--reports", help="Where digests go.")]


def _fail(message: str) -> None:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def load_settings(path: Path | None) -> Settings:
    if path is None:
        return Settings()
    try:
        return Settings(**(yaml.safe_load(path.read_text("utf-8")) or {}))
    except (ValidationError, TypeError, yaml.YAMLError) as e:
        raise ValueError(f"{path}: {e}") from e


def _do_collect(org: str, days: int, snapshots: Path) -> Path:
    from sfdigest.collect import SfCliClient, collect

    session = get_session(org)
    typer.echo(f"Reading {days} day(s) of setup changes from {session.username} …")
    path = collect(session, SfCliClient(org), data_decl(days), snapshots)
    typer.echo(f"Snapshot: {path}")
    return path


def _do_digest(snapshot: Path, settings: Settings, reports: Path) -> Digest:
    digest = build_digest(snapshot, settings)
    paths = write_outputs(digest, reports / snapshot.resolve().name)
    typer.echo("")
    for line in digest.summary:
        typer.echo(line)
    typer.echo("")
    for file, reason in digest.not_collected.items():
        typer.secho(f"warning: {file} not collected: {reason}", fg=typer.colors.YELLOW, err=True)
    if digest.integrity_issues:
        typer.secho("warning: snapshot integrity check failed", fg=typer.colors.YELLOW, err=True)
    typer.echo(f"Digest: {paths['html']}")
    typer.echo(f"Text version: {paths['text']}")
    return digest


@app.command("collect")
def collect_cmd(
    org: OrgOpt, days: DaysOpt = 7, snapshots: SnapshotsOpt = Path("snapshots")
) -> None:
    """Read the Setup Audit Trail (read-only) and write a hashed snapshot."""
    try:
        _do_collect(org, days, snapshots)
    except ConnectError as e:
        _fail(str(e))


@app.command("digest")
def digest_cmd(
    snapshot: SnapshotArg,
    settings: SettingsOpt = None,
    reports: ReportsOpt = Path("reports"),
) -> None:
    """Build the digest from a snapshot (offline)."""
    try:
        _do_digest(snapshot, load_settings(settings), reports)
    except (SnapshotError, ValueError) as e:
        _fail(str(e))


@app.command("run")
def run_cmd(
    org: OrgOpt,
    days: DaysOpt = 7,
    settings: SettingsOpt = None,
    snapshots: SnapshotsOpt = Path("snapshots"),
    reports: ReportsOpt = Path("reports"),
) -> None:
    """collect + digest in one go."""
    try:
        loaded = load_settings(settings)  # fail before collecting
        _do_digest(_do_collect(org, days, snapshots), loaded, reports)
    except (ConnectError, SnapshotError, ValueError) as e:
        _fail(str(e))


if __name__ == "__main__":
    app()
