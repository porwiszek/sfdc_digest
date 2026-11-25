# sfdigest — Salesforce setup change digest

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

```bash
uv sync                                    # install
sf org login web --alias my-org            # authenticate (once)
uv run sfdigest run --org my-org           # last 7 days
uv run sfdigest run --org my-org --days 30 # up to 180
```

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
