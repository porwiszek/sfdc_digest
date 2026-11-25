# sfdigest — Salesforce setup change digest

> **Early release (0.1.0).** Tested on a small number of orgs so far. It only reads
> from your org, but expect rough edges: flags that are noise, changes it should have
> flagged, wording that is unclear. Feedback is very welcome: please
> [open an issue](https://github.com/porwiszek/sfdc_digest/issues). Describe what you
> saw rather than pasting your digest, which contains your org's usernames and changes.

A small, free, local tool that answers one question: **what changed in my Salesforce
org's Setup lately, and which changes should I look at?**

It reads the Setup Audit Trail, read-only, and writes a digest:

- a plain-language summary (how many changes, by whom, in which areas)
- the changes that match a high-risk rule: a privileged permission granted, a
  privileged permission set assigned, a change made while logged in as another user,
  a security setting or connected app changed, a change made by an integration user
- counts by user, by Setup area and by day, and the full list

Everything stays on your computer. The digest is built by fixed rules; no data is
sent to any service and no AI model is used.

## Use

You need Python 3.12+, [uv](https://docs.astral.sh/uv/) and the Salesforce CLI (`sf`).

Log in to your org once:

```bash
sf org login web --alias my-org
```

Then run it without installing anything, in a folder of your choice:

```bash
uvx --from git+https://github.com/porwiszek/sfdc_digest sfdigest run --org my-org           # last 7 days
uvx --from git+https://github.com/porwiszek/sfdc_digest sfdigest run --org my-org --days 30 # up to 180
```

Or clone the repository, if you want to read the code first:

```bash
git clone https://github.com/porwiszek/sfdc_digest.git
cd sfdc_digest
uv sync
uv run sfdigest run --org my-org
```

The snapshot is written under `snapshots/` and the digest under `reports/`, in the
folder you run it from. Both contain your org's data; keep them private.

Output, under `reports/<snapshot>/`:

- `digest.html`: the digest
- `digest.txt`: short text version to paste into an email or chat message
- `changes.csv`: every change in the period
- `digest.json`: the same data for other tools

To get a weekly digest, schedule `sfdigest run` with cron or Task Scheduler.

`settings.yaml` is optional; see `settings.example.yaml` to list your integration
users or change what is flagged.

## The user that runs it

The user logged in to the `sf` CLI needs "View Setup and Configuration" to read the
Setup Audit Trail. The tool only runs SELECT queries.

## Limitations

- Salesforce keeps the Setup Audit Trail for 180 days, so that is the longest period.
- The digest covers Setup (configuration) changes, not changes to records.
- Flags are based on the audit trail's text and area names in English; an org whose
  audit trail is in another language will list changes but flag fewer of them.
- A flag means "check this was intended", not "this is wrong".
- A very large number of changes can exceed the sf CLI's query record limit
  (`org-max-query-limit`). The digest then says the trail was not collected instead of
  showing a partial list; use fewer days or raise the limit.


## License

MIT. See [LICENSE](LICENSE). The software is provided as is, without warranty: a digest
with no flags does not mean the org is secure.
