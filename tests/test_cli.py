"""End to end through the real subprocess path, against a fake `sf` executable."""

import json
import os
import stat
import sys

import pytest
from conftest import PSA, TRAIL
from typer.testing import CliRunner

from sfdigest.cli import app

FAKE_SF = """#!{python}
import json, sys

args = sys.argv[1:]
data = json.load(open({data_path!r}))
if args[:2] == ["org", "display"]:
    out = {{"status": 0, "result": {{"id": "00D1", "instanceUrl": "https://acme.my.salesforce.com",
            "apiVersion": "68.0", "username": "auditor@acme.com", "accessToken": "SECRET"}}}}
elif args[:2] == ["data", "query"]:
    query = args[args.index("--query") + 1]
    assert query.lstrip().upper().startswith("SELECT"), query
    open({log_path!r}, "a").write(query + "\\n")
    sobject = query.split(" FROM ")[1].split()[0]
    if sobject in data["fail"]:
        out = {{"status": 1, "name": "INSUFFICIENT_ACCESS", "message": "no access"}}
    else:
        records = data["records"][sobject]
        out = {{"status": 0, "result": {{"done": True, "totalSize": len(records),
                "records": records}}}}
else:
    out = {{"status": 1, "name": "Unexpected", "message": " ".join(args)}}
print(json.dumps(out))
"""

BY_SOBJECT = {
    "Organization": [{"Id": "00D1", "Name": "Acme"}],
    "SetupAuditTrail": TRAIL,
    "PermissionSetAssignment": PSA,
}


@pytest.fixture
def fake_sf(tmp_path, monkeypatch):
    def install(fail: list[str] | None = None):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        data_path = tmp_path / "org.json"
        data_path.write_text(json.dumps({"records": BY_SOBJECT, "fail": fail or []}))
        script = bin_dir / "sf"
        script.write_text(
            FAKE_SF.format(
                python=sys.executable,
                data_path=str(data_path),
                log_path=str(tmp_path / "queries.log"),
            )
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    return install


def run(tmp_path, *args):
    return CliRunner().invoke(
        app,
        [*args, "--snapshots", str(tmp_path / "snapshots"), "--reports", str(tmp_path / "reports")],
    )


def test_run_end_to_end_without_settings(tmp_path, fake_sf):
    fake_sf()
    result = run(tmp_path, "run", "--org", "dev", "--days", "30")
    assert result.exit_code == 0, result.output
    assert "8 setup changes by 3 users in the last 30 days." in result.output
    assert "5 need a look" in result.output
    assert "SECRET" not in result.output
    assert "LAST_N_DAYS:30" in (tmp_path / "queries.log").read_text()
    (snapshot,) = (tmp_path / "snapshots").iterdir()
    assert "SECRET" not in (snapshot / "manifest.json").read_text()
    out = tmp_path / "reports" / snapshot.name
    assert {p.name for p in out.iterdir()} == {
        "digest.html", "digest.txt", "changes.csv", "digest.json"
    }  # fmt: skip
    digest = json.loads((out / "digest.json").read_text())
    assert digest["not_collected"] == {} and digest["integrity_issues"] == []


def test_run_without_access_to_the_audit_trail(tmp_path, fake_sf):
    fake_sf(fail=["SetupAuditTrail"])
    result = run(tmp_path, "run", "--org", "dev")
    assert result.exit_code == 0, result.output
    assert "The Setup Audit Trail could not be read" in result.output
    assert "INSUFFICIENT_ACCESS" in result.output


def test_days_are_limited_to_what_salesforce_keeps(tmp_path, fake_sf):
    fake_sf()
    result = run(tmp_path, "run", "--org", "dev", "--days", "365")
    assert result.exit_code == 2 and not (tmp_path / "snapshots").exists()


def test_bad_settings_fail_before_collecting(tmp_path, fake_sf):
    fake_sf()
    settings = tmp_path / "settings.yaml"
    settings.write_text("integration_user: [a@acme.com]\n")  # typo
    result = run(tmp_path, "run", "--org", "dev", "--settings", str(settings))
    assert result.exit_code == 1 and "integration_user" in result.output
    assert not (tmp_path / "snapshots").exists()
