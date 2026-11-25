"""Turn a snapshot of the Setup Audit Trail into a digest.

Reads only from the snapshot. The summary is built by rules; no data is sent to any
service and no AI model is involved. Missing data is reported under `not_collected`,
never raised.

The flagging rules (classify and privileged_sets below) are the same as in the
author's full assessment, so the digest and an assessment agree on what counts as a
high-risk change.
"""

import re
from collections import Counter
from pathlib import Path
from typing import Any

from sfdigest import __version__
from sfdigest.models import Change, Count, Digest, Settings
from sfdigest.snapshot import MANIFEST, MissingDataError, Snapshot, iso_utc, sha256_file, utc_now

TRAIL = "setup_audit_trail"
TRAIL_FILE = f"soql/{TRAIL}.json"
ASSIGN_ACTIONS = {"PermSetAssign", "PermSetGroupAssign"}
DELEGATED = "done while logged in as another user"


def privileged_sets(psa_rows: list[dict[str, Any]]) -> set[str]:
    """Names and labels of permission sets and groups (not profiles) that are privileged."""
    names = set()
    for row in psa_rows:
        ps = row.get("PermissionSet") or {}
        if not ps.get("IsOwnedByProfile"):
            names.update(n for n in (ps.get("Name"), ps.get("Label")) if n)
    return names


def classify(entry: dict[str, Any], settings: Settings, priv_sets: set[str]) -> list[str]:
    """Why a change deserves a look; empty for a routine change."""
    display = entry.get("Display") or ""
    section = entry.get("Section") or ""
    user = ((entry.get("CreatedBy") or {}).get("Username") or "").lower()
    reasons = []
    perms = "|".join(re.escape(p) for p in settings.privileged_permissions)
    if perms and re.search(
        rf"\b({perms}) permission was changed from disabled to enabled", display
    ):
        reasons.append("privileged permission granted")
    if entry.get("Action") in ASSIGN_ACTIONS and any(
        re.search(rf"\b{re.escape(name)}\b", display) for name in priv_sets
    ):
        reasons.append("privileged permission set assigned")
    if entry.get("DelegateUser"):
        reasons.append(f"{DELEGATED} ({entry['DelegateUser']})")
    if section in settings.security_sections:
        reasons.append("security setting changed")
    if section in settings.connected_app_sections:
        reasons.append("connected app change")
    if user and user in {u.lower() for u in settings.integration_users}:
        reasons.append("change by integration user")
    return reasons


def is_automated_user(entry: dict[str, Any], settings: Settings) -> bool:
    """True for a change Salesforce recorded with no user, or by its Automated Process user."""
    user = ((entry.get("CreatedBy") or {}).get("Username") or "").lower()
    prefixes = tuple(p.lower() for p in settings.automated_user_prefixes)
    return not user or bool(prefixes) and user.startswith(prefixes)


def flag_kind(flag: str) -> str:
    """A flag without its detail, for counting: '... another user (x)' -> '... another user'."""
    return DELEGATED if flag.startswith(DELEGATED) else flag


def period_days(manifest: dict[str, Any]) -> int | None:
    """The number of days the snapshot was collected for, from its recorded query."""
    query = (manifest.get("queries") or {}).get(TRAIL_FILE, "")
    match = re.search(r"LAST_N_DAYS:(\d+)", query)
    return int(match.group(1)) if match else None


def _counts(pairs: list[tuple[str, bool]]) -> list[Count]:
    """Counts per name, most changes first."""
    total, flagged = Counter(), Counter()
    for name, is_flagged in pairs:
        total[name] += 1
        flagged[name] += is_flagged
    return [
        Count(name=name, changes=n, flagged=flagged[name])
        for name, n in sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def summarize(d: Digest) -> list[str]:
    """Plain-language lines for the top of the digest and for pasting into a message."""
    period = f"the last {_plural(d.days, 'day')}" if d.days else "the collected period"
    if TRAIL_FILE in d.not_collected:
        return [f"The Setup Audit Trail could not be read: {d.not_collected[TRAIL_FILE]}"]
    if not d.changes:
        lines = [f"No setup changes by people in {period}."]
    else:
        people = [c for c in d.by_user if c.name]
        lines = [
            f"{_plural(len(d.changes), 'setup change')} by {_plural(len(people), 'user')} "
            f"in {period}."
        ]
        flagged = d.flagged
        if flagged:
            kinds = ", ".join(f"{c.changes} × {c.name}" for c in d.by_flag)
            verb = "needs" if len(flagged) == 1 else "need"
            lines.append(f"{len(flagged)} {verb} a look: {kinds}.")
        else:
            lines.append("None matched the high-risk rules.")
        top_users = ", ".join(f"{c.name} ({c.changes})" for c in people[:3])
        if top_users:
            lines.append(f"Most active: {top_users}.")
        top_sections = ", ".join(f"{c.name} ({c.changes})" for c in d.by_section[:3])
        lines.append(f"Most changed areas: {top_sections}.")
    if d.automated:
        lines.append(f"{_plural(d.automated, 'change')} by Salesforce automation not counted.")
    if "soql/privileged_psa.json" in d.not_collected:
        lines.append(
            "Privileged permission sets could not be read, so assignments of them are not flagged."
        )
    return lines


def build_digest(snapshot_dir: Path, settings: Settings) -> Digest:
    snapshot = Snapshot(snapshot_dir)
    not_collected: dict[str, str] = {}

    def rows(name: str) -> list[dict[str, Any]]:
        try:
            data = snapshot.soql(name)
        except MissingDataError as e:
            not_collected[f"soql/{name}.json"] = str(e)
            return []
        if not isinstance(data, list):
            not_collected[f"soql/{name}.json"] = "collected data is not a list of records"
            return []
        return [r for r in data if isinstance(r, dict)]

    trail = rows(TRAIL)
    priv_sets = privileged_sets(rows("privileged_psa"))
    changes: list[Change] = []
    automated = 0
    for entry in trail:
        if entry.get("Action") in settings.automated_actions:
            automated += 1
            continue
        flags = classify(entry, settings, priv_sets)
        # A change by Salesforce's own users is counted, not listed, unless a rule matched:
        # a flagged change is never hidden.
        if not flags and is_automated_user(entry, settings):
            automated += 1
            continue
        changes.append(
            Change(
                when=str(entry.get("CreatedDate") or ""),
                by=((entry.get("CreatedBy") or {}).get("Username") or "").lower(),
                section=str(entry.get("Section") or ""),
                action=str(entry.get("Action") or ""),
                change=str(entry.get("Display") or entry.get("Action") or ""),
                delegate=str(entry.get("DelegateUser") or ""),
                flags=flags,
            )
        )
    changes.sort(key=lambda c: c.when, reverse=True)

    digest = Digest(
        tool_version=__version__,
        generated_at=iso_utc(utc_now()),
        snapshot_dir=snapshot.path.name,
        manifest=snapshot.manifest,
        manifest_sha256=sha256_file(snapshot.path / MANIFEST),
        integrity_issues=snapshot.verify(),
        settings=settings,
        days=period_days(snapshot.manifest),
        changes=changes,
        automated=automated,
        by_user=_counts([(c.by, bool(c.flags)) for c in changes]),
        by_section=_counts([(c.section or "(no section)", bool(c.flags)) for c in changes]),
        by_day=sorted(
            _counts([(c.when[:10], bool(c.flags)) for c in changes]),
            key=lambda c: c.name,
            reverse=True,
        ),
        by_flag=_counts([(flag_kind(f), True) for c in changes for f in c.flags]),
        not_collected=dict(sorted(not_collected.items())),
    )
    digest.summary = summarize(digest)
    return digest
