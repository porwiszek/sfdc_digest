import pytest
from conftest import PSA, TRAIL, entry, make_snapshot

from sfdigest.digest import build_digest
from sfdigest.models import Settings
from sfdigest.queries import MAX_DAYS, audit_trail_query

WITH_ERP = Settings(integration_users=["INT.ERP@acme.com"])


def flags(digest):
    return {c.change.split(":")[0][:40]: c.flags for c in digest.flagged}


def test_flags_match_the_assessment_rules(snapshot_dir):
    d = build_digest(snapshot_dir, WITH_ERP)
    expected = {
        "Changed permission set Data Steward": ["privileged permission granted"],
        "Permission set group Admin_Bundle": ["privileged permission set assigned"],
        "Changed session timeout value from 2 hou": ["security setting changed"],
        "Changed Payment Apex Class code": [
            "done while logged in as another user (support@acme.com)"
        ],
        "Created connected app Data Exporter": ["connected app change"],
        "Changed email for user Ann": ["change by integration user"],
    }
    assert flags(d) == expected
    # routine changes are listed but not flagged
    assert len(d.changes) == 8 and len(d.flagged) == 6


def test_integration_user_flag_needs_the_setting(snapshot_dir):
    d = build_digest(snapshot_dir, Settings())
    assert len(d.flagged) == 5
    assert "Changed email for user Ann" not in flags(d)


def test_salesforce_automation_is_counted_not_listed(snapshot_dir):
    d = build_digest(snapshot_dir, Settings())
    assert d.automated == 1
    assert all(c.action != "BlackTabFrameworkActionRun" for c in d.changes)
    assert d.summary[-1] == "1 change by Salesforce automation not counted."


def test_automated_process_user_and_unattributed_changes_are_counted_not_listed(tmp_path):
    trail = [
        entry("2026-11-12T10:00:00", "autoproc@00d000000000001", "Permission Set Group",
              "PermissionSetGroupCalculationStarted", "Permission set group calculation started"),
        entry("2026-11-12T09:00:00", None, "", "value_MAX_STREAMING_TOPICS_PROV",
              "Max number of streaming topics"),
        entry("2026-11-12T08:00:00", "Admin@acme.com", "Apex Class", "changedApexClass",
              "Changed Foo Apex Class code"),
    ]  # fmt: skip
    snap = make_snapshot(tmp_path / "s", {"setup_audit_trail": trail, "privileged_psa": PSA})
    d = build_digest(snap, Settings())
    assert d.automated == 2
    assert [c.by for c in d.changes] == ["admin@acme.com"]
    assert d.summary[0] == "1 setup change by 1 user in the last 7 days."
    assert d.summary[-1] == "2 changes by Salesforce automation not counted."


def test_automated_user_change_matching_a_rule_is_still_listed(tmp_path):
    trail = [
        entry("2026-11-12T10:00:00", "autoproc@00d000000000001", "Session Settings",
              "changedSessionTimeout", "Changed session timeout value"),
        entry("2026-11-12T09:00:00", None, "Connected Apps", "createdConnectedApp",
              "Created connected app X"),
    ]  # fmt: skip
    snap = make_snapshot(tmp_path / "s", {"setup_audit_trail": trail, "privileged_psa": PSA})
    d = build_digest(snap, Settings())
    assert d.automated == 0
    assert [c.flags for c in d.changes] == [["security setting changed"], ["connected app change"]]


def test_counts(snapshot_dir):
    d = build_digest(snapshot_dir, WITH_ERP)
    assert [(c.name, c.changes, c.flagged) for c in d.by_user] == [
        ("admin@acme.com", 4, 3),  # usernames lowercased
        ("dev@acme.com", 3, 2),
        ("int.erp@acme.com", 1, 1),
    ]
    assert [(c.name, c.changes) for c in d.by_section][:2] == [
        ("Manage Users", 4),
        ("Apex Class", 2),
    ]
    assert [(c.name, c.changes) for c in d.by_day] == [
        ("2026-11-13", 2), ("2026-11-12", 3), ("2026-11-11", 2), ("2026-11-10", 1)
    ]  # fmt: skip
    assert sum(c.changes for c in d.by_flag) == 6
    assert [c.when for c in d.changes] == sorted((c.when for c in d.changes), reverse=True)


def test_summary_lines(snapshot_dir):
    d = build_digest(snapshot_dir, WITH_ERP)
    assert d.days == 7
    assert d.summary[0] == "8 setup changes by 3 users in the last 7 days."
    assert d.summary[1].startswith("6 need a look: ")
    assert "1 × done while logged in as another user" in d.summary[1]
    assert (
        d.summary[2] == "Most active: admin@acme.com (4), dev@acme.com (3), int.erp@acme.com (1)."
    )
    assert d.summary[3].startswith("Most changed areas: Manage Users (4), Apex Class (2)")


def test_quiet_period(tmp_path):
    snap = make_snapshot(tmp_path / "s", {"setup_audit_trail": [], "privileged_psa": PSA}, days=1)
    d = build_digest(snap, Settings())
    assert d.summary == ["No setup changes by people in the last 1 day."]
    assert d.changes == [] and d.by_user == []


def test_only_routine_changes(tmp_path):
    snap = make_snapshot(tmp_path / "s", {"setup_audit_trail": [TRAIL[0]], "privileged_psa": PSA})
    d = build_digest(snap, Settings())
    assert d.summary[:2] == [
        "1 setup change by 1 user in the last 7 days.",
        "None matched the high-risk rules.",
    ]


def test_trail_not_collected(tmp_path):
    errors = {"soql/setup_audit_trail.json": "QueryError: INSUFFICIENT_ACCESS"}
    snap = make_snapshot(tmp_path / "s", {"privileged_psa": PSA}, errors)
    d = build_digest(snap, Settings())
    assert "INSUFFICIENT_ACCESS" in d.not_collected["soql/setup_audit_trail.json"]
    assert d.summary[0].startswith("The Setup Audit Trail could not be read")
    assert d.changes == []


def test_privileged_sets_not_collected_still_gives_a_digest(tmp_path):
    errors = {"soql/privileged_psa.json": "QueryError: boom"}
    snap = make_snapshot(tmp_path / "s", {"setup_audit_trail": TRAIL}, errors)
    d = build_digest(snap, Settings())
    assert len(d.changes) == 8 and len(d.flagged) == 4  # the group assignment is not flagged
    assert d.summary[-1].startswith("Privileged permission sets could not be read")


def test_tampered_snapshot_is_reported(snapshot_dir):
    (snapshot_dir / "soql" / "setup_audit_trail.json").write_text("[]")
    assert build_digest(snapshot_dir, Settings()).integrity_issues == [
        "soql/setup_audit_trail.json: SHA-256 does not match manifest"
    ]


@pytest.mark.parametrize("days", [0, MAX_DAYS + 1, -3])
def test_days_out_of_range(days):
    with pytest.raises(ValueError, match="between 1 and 180"):
        audit_trail_query(days)


def test_query_is_the_verified_one():
    assert audit_trail_query(30) == (
        "SELECT Action, Section, Display, CreatedBy.Username, CreatedDate, DelegateUser "
        "FROM SetupAuditTrail WHERE CreatedDate = LAST_N_DAYS:30 ORDER BY CreatedDate DESC"
    )
