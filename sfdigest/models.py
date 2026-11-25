"""Settings and digest models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sfdigest.queries import PRIVILEGED_PERMISSIONS


class Settings(BaseModel):
    """Optional configuration from settings.yaml. The defaults work for most orgs."""

    model_config = ConfigDict(extra="forbid")

    org_label: str = ""  # name shown on the digest; defaults to the org's own name
    # Granting one of these permissions is flagged.
    privileged_permissions: list[str] = Field(
        default_factory=lambda: [*PRIVILEGED_PERMISSIONS, "ApiEnabled"]
    )
    # Any change in these Setup sections is flagged.
    security_sections: list[str] = Field(
        default_factory=lambda: [
            "Session Settings",
            "Security Controls",
            "Identity Verification",
            "Password Policies",
            "Network Access",
            "Single Sign-On Settings",
            "Login Access Policies",
        ]
    )
    connected_app_sections: list[str] = Field(
        default_factory=lambda: [
            "External Client Application",
            "Connected Apps",
            "Manage Connected Apps",
        ]
    )
    # Usernames of integration (system) users; a setup change by one of them is flagged.
    integration_users: list[str] = Field(default_factory=list)
    # Salesforce's own release automation; counted separately, never flagged.
    automated_actions: list[str] = Field(default_factory=lambda: ["BlackTabFrameworkActionRun"])
    # Salesforce's Automated Process user (autoproc@<org id>). Its changes, and changes
    # recorded with no user, are counted separately unless a rule flags them.
    automated_user_prefixes: list[str] = Field(default_factory=lambda: ["autoproc@"])


class Change(BaseModel):
    when: str
    by: str  # username, lowercased; "" when Salesforce recorded none
    section: str
    action: str
    change: str
    delegate: str = ""
    flags: list[str] = Field(default_factory=list)
    automated: bool = False


class Count(BaseModel):
    name: str
    changes: int
    flagged: int = 0


class Digest(BaseModel):
    """Output of `sfdigest digest`, input of the report."""

    tool_version: str
    generated_at: str
    snapshot_dir: str
    manifest: dict[str, Any]
    manifest_sha256: str = ""
    integrity_issues: list[str] = Field(default_factory=list)
    settings: Settings
    days: int | None = None  # period the snapshot covers; None if it cannot be read
    changes: list[Change] = Field(default_factory=list)  # by people, newest first
    automated: int = 0  # changes by Salesforce automation, not listed
    by_user: list[Count] = Field(default_factory=list)
    by_section: list[Count] = Field(default_factory=list)
    by_day: list[Count] = Field(default_factory=list)
    by_flag: list[Count] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)  # plain-language lines
    not_collected: dict[str, str] = Field(default_factory=dict)

    @property
    def flagged(self) -> list[Change]:
        return [c for c in self.changes if c.flags]
