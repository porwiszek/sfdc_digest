import csv
import io
import json

from conftest import PSA, TRAIL, entry, make_snapshot

from sfdigest import branding
from sfdigest.digest import build_digest
from sfdigest.models import Settings
from sfdigest.report.render import changes_csv, render_html, render_text, write_outputs


def test_html(snapshot_dir):
    html = render_html(build_digest(snapshot_dir, Settings()))
    assert "<h1>Acme</h1>" in html and "last 7 days" in html
    assert "Needs a look (5)" in html and "All changes (8)" in html
    assert "2026-11-12 14:00 UTC" in html
    assert "What this digest does not check" in html
    assert "no integration users listed in settings.yaml" in html
    assert "Not collected" not in html and "integrity check failed" not in html


def test_contact_line_only_when_branding_is_filled(snapshot_dir, monkeypatch):
    digest = build_digest(snapshot_dir, Settings())
    monkeypatch.setattr(branding, "AUTHOR", "")
    assert "<strong>" not in render_html(digest).split("does not check")[2].split("</div>")[0]
    monkeypatch.setattr(branding, "AUTHOR", "Example Security")
    monkeypatch.setattr(branding, "URL", "https://example.com")
    monkeypatch.setattr(branding, "OFFER", "full Salesforce security assessments")
    html = render_html(digest)
    assert "<strong>Example Security</strong>: full Salesforce security assessments" in html
    assert '<a href="https://example.com">' in html


def test_html_escapes_org_data(tmp_path):
    evil = entry("2026-11-13T09:00:00", "a@acme.com", "Apex Class", "x",
                 "<script>alert(1)</script>")  # fmt: skip
    snap = make_snapshot(tmp_path / "s", {"setup_audit_trail": [evil], "privileged_psa": PSA})
    html = render_html(build_digest(snap, Settings()))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_text_version(snapshot_dir):
    text = render_text(build_digest(snapshot_dir, Settings()))
    lines = text.splitlines()
    assert lines[0] == "Salesforce setup changes · Acme"
    assert lines[2] == "8 setup changes by 3 users in the last 7 days."
    assert "Needs a look:" in lines
    assert "  why: security setting changed" in lines
    assert sum(line.startswith("- ") for line in lines) == 5


def test_csv_and_files(snapshot_dir, tmp_path):
    digest = build_digest(snapshot_dir, Settings())
    rows = list(csv.DictReader(io.StringIO(changes_csv(digest))))
    assert len(rows) == len(TRAIL) - 1  # the Salesforce automation entry is left out
    assert rows[0]["when"] == "2026-11-13 09:00 UTC" and rows[0]["why_flagged"] == ""
    paths = write_outputs(digest, tmp_path / "out")
    assert {p.name for p in paths.values()} == {
        "digest.html", "digest.txt", "changes.csv", "digest.json"
    }  # fmt: skip
    assert json.loads(paths["json"].read_text())["automated"] == 1
