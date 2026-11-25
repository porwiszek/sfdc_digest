"""A small fake Setup Audit Trail shared by the tests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from sfdigest.queries import data_decl
from sfdigest.snapshot import write_snapshot

COLLECTED_AT = datetime(2026, 11, 13, 12, 0, 0, tzinfo=UTC)


def entry(when, user, section, action, display, delegate=None):
    return {
        "Action": action,
        "Section": section,
        "Display": display,
        "CreatedBy": {"Username": user} if user else None,
        "CreatedDate": f"{when}.000+0000",
        "DelegateUser": delegate,
    }


ADMIN, DEV, ERP = "Admin@acme.com", "dev@acme.com", "int.erp@acme.com"

TRAIL = [
    entry("2026-11-13T09:00:00", ADMIN, "Manage Users", "PermSetAssign",
          "Permission set Sales Basics: assigned to user Sam Sales (UserID: [005S])"),
    entry("2026-11-13T08:00:00", ADMIN, "Manage Users", "PermSetEnableUserPerm",
          "Changed permission set Data Steward: ViewAllData permission was changed from "
          "disabled to enabled"),
    entry("2026-11-12T15:00:00", ADMIN, "Manage Users", "PermSetGroupAssign",
          "Permission set group Admin_Bundle: assigned to user Sam Sales (UserID: [005S])"),
    entry("2026-11-12T14:00:00", ADMIN, "Session Settings", "changedsessiontimeout",
          "Changed session timeout value from 2 hours to 12 hours"),
    entry("2026-11-12T10:00:00", DEV, "Apex Class", "changedApexClass",
          "Changed Payment Apex Class code", delegate="support@acme.com"),
    entry("2026-11-11T10:00:00", DEV, "Apex Class", "changedApexClass",
          "Changed AccountService Apex Class code"),
    entry("2026-11-11T09:00:00", DEV, "Connected Apps", "createdconnectedapp",
          "Created connected app Data Exporter"),
    entry("2026-11-10T09:00:00", ERP, "Manage Users", "changedUserEmail",
          "Changed email for user Ann"),
    entry("2026-11-10T03:00:00", None, "", "BlackTabFrameworkActionRun",
          "A Salesforce employee ran the Releasable Action", delegate="Salesforce Administrator"),
]  # fmt: skip

PSA = [
    {"PermissionSet": {"Name": "X00e", "Label": "X00e", "IsOwnedByProfile": True}},
    {"PermissionSet": {"Name": "Admin_Bundle", "Label": "Admin Bundle",
                       "IsOwnedByProfile": False}},
]  # fmt: skip


def make_snapshot(path: Path, data: dict | None = None, errors: dict | None = None, days=7):
    decl = data_decl(days)
    return write_snapshot(
        path,
        org_id="00D1",
        org={"Id": "00D1", "Name": "Acme"},
        instance_url="https://acme.my.salesforce.com",
        api_version="68.0",
        collecting_user="auditor@acme.com",
        collected_at=COLLECTED_AT,
        data={
            "soql": {"setup_audit_trail": TRAIL, "privileged_psa": PSA} if data is None else data
        },  # fmt: skip
        errors=errors or {},
        queries={f"soql/{name}.json": q for name, q in decl["soql"].items()},
    )


@pytest.fixture
def snapshot_dir(tmp_path) -> Path:
    return make_snapshot(tmp_path / "00D1_20261113T120000Z")
