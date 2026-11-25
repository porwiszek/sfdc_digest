"""What sfdigest reads from the org. Every query is a read-only SELECT.

The objects and fields in both queries were verified on Developer Edition orgs.
"""

from sfdigest.collect import DataDecl

MAX_DAYS = 180  # Salesforce keeps the Setup Audit Trail for 180 days

# Admin-level permissions treated as privileged (PermissionSet field names without the
# "Permissions" prefix).
PRIVILEGED_PERMISSIONS = [
    "ModifyAllData",
    "ViewAllData",
    "ManageUsers",
    "AuthorApex",
    "CustomizeApplication",
]

# Active users holding a privileged permission. Used only to learn which permission
# sets and groups are privileged, so that assigning one can be flagged.
PRIVILEGED_PSA = (
    "SELECT AssigneeId, Assignee.Username, Assignee.Name, Assignee.UserType, "
    "Assignee.IsActive, Assignee.LastLoginDate, Assignee.CreatedDate, "
    "PermissionSet.Name, PermissionSet.Label, PermissionSet.IsOwnedByProfile, "
    "PermissionSet.Profile.Name, "
    + ", ".join(f"PermissionSet.Permissions{p}" for p in PRIVILEGED_PERMISSIONS)
    + ", PermissionSetGroupId FROM PermissionSetAssignment WHERE ("
    + " OR ".join(f"PermissionSet.Permissions{p} = true" for p in PRIVILEGED_PERMISSIONS)
    + ") AND Assignee.IsActive = true"
)


def audit_trail_query(days: int) -> str:
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_DAYS}, got {days}")
    return (
        "SELECT Action, Section, Display, CreatedBy.Username, CreatedDate, DelegateUser "
        f"FROM SetupAuditTrail WHERE CreatedDate = LAST_N_DAYS:{days} "
        "ORDER BY CreatedDate DESC"
    )


def data_decl(days: int) -> DataDecl:
    return {
        "soql": {
            "setup_audit_trail": audit_trail_query(days),
            "privileged_psa": PRIVILEGED_PSA,
        }
    }
