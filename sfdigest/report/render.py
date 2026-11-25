"""Render a Digest: one self-contained HTML file, a text version and a CSV."""

import csv
import io
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from sfdigest import branding
from sfdigest.models import Digest

SF_TIMESTAMP = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(?:\+0000|Z)")

# What a change digest cannot tell you. Shown in every digest.
NOT_CHECKED = [
    "Whether MFA is enforced for every login",
    "Who holds admin-level permissions today, and whether those accounts are still used",
    "Password, session and login IP settings against a baseline",
    "What guest (unauthenticated) users can read on your sites",
    "Which connected apps and OAuth tokens can reach your data",
    "Who can use the API, and how integration users are set up",
    "Whether each flagged change has a matching change record or approval",
]


def fmt_time(value: Any) -> str:
    """One UTC timestamp style throughout."""
    return SF_TIMESTAMP.sub(r"\1 \2 UTC", str(value or ""))


def org_label(d: Digest) -> str:
    org = d.manifest.get("org") or {}
    return d.settings.org_label or org.get("Name") or d.manifest.get("org_id", "")


def render_html(d: Digest) -> str:
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(time=fmt_time)
    return env.get_template("template.html").render(
        d=d,
        label=org_label(d),
        flagged=d.flagged,
        max_day=max((c.changes for c in d.by_day), default=1),
        not_checked=NOT_CHECKED,
        brand=branding,
    )


def render_text(d: Digest) -> str:
    """Short text version, for pasting into an email or a chat message."""
    lines = [f"Salesforce setup changes · {org_label(d)}", "", *d.summary]
    if d.flagged:
        lines += ["", "Needs a look:"]
        for c in d.flagged:
            lines.append(f"- {fmt_time(c.when)} · {c.by or 'unknown user'} · {c.change}")
            lines.append(f"  why: {'; '.join(c.flags)}")
    for file, reason in d.not_collected.items():
        lines += ["", f"Not collected: {file}: {reason}"]
    return "\n".join(lines) + "\n"


def changes_csv(d: Digest) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["when", "by", "section", "action", "change", "delegate", "why_flagged"])
    for c in d.changes:
        writer.writerow(
            [fmt_time(c.when), c.by, c.section, c.action, c.change, c.delegate, "; ".join(c.flags)]
        )
    return out.getvalue()


def write_outputs(d: Digest, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "html": out_dir / "digest.html",
        "text": out_dir / "digest.txt",
        "csv": out_dir / "changes.csv",
        "json": out_dir / "digest.json",
    }
    paths["html"].write_text(render_html(d), "utf-8")
    paths["text"].write_text(render_text(d), "utf-8")
    paths["csv"].write_text(changes_csv(d), "utf-8")
    paths["json"].write_text(d.model_dump_json(indent=2) + "\n", "utf-8")
    return paths
