# Backups — the only copy of your job search

The database volume holds everything Nightshift knows about *you*: applications
and their stage history, interviews, notes, the profile and confirmed resume
facts, captures, MCP tokens, and the company offices you typed and geocoded. The
job corpus can be re-polled. None of the rest can.

```sh
make backup                       # verified dump → ~/nightshift-backups/nightshift-<UTC>.dump
make restore                      # newest dump, after you type RESET
make restore FILE=~/nightshift-backups/nightshift-20261002T051500Z.dump
```

- **A backup is verified before it counts.** It is written to a `.partial` name,
  read back with `pg_restore --list`, and only then renamed. A dump interrupted
  half-way never shows up as the newest backup.
- **A restore is one transaction.** If it fails, the database is exactly as it
  was before you ran it. A restore also brings back MCP tokens, so a linked
  Claude Desktop keeps working.
- **Backups live outside the repository** (`NIGHTSHIFT_BACKUP_DIR` to move them),
  because they are personal data and the tree is one `git add -A` from a public
  remote. Nothing ever deletes them; prune by hand.

## `make reset-db`

It now **backs up first and asks before deleting anything**. Two separate
escape hatches, on purpose:

| Setting | Skips |
|---|---|
| `FORCE=1` | the question — never the backup |
| `SKIP_BACKUP=1` | the backup — for a database that cannot be dumped |

If the backup fails, the reset is aborted and nothing is deleted. Without a
terminal (a script, CI) and without `FORCE=1`, it refuses rather than guessing.

## A habit worth having

`make backup` before anything heavy: a big ingest, a migration you wrote, a
dependency bump, `docker system prune`, or freeing disk when Docker has wedged
(`docker-will-not-start.md`). A full disk is how this machine lost Docker once
already.
