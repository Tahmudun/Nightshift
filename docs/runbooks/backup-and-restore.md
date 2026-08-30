# Backup and restore

> Written at M6a, deliberately **before** the reader's own account existed.
> After that point their profile, their confirmed resume facts and their
> application history live in exactly one place, and `make reset-db` drops it.

## The short version

```bash
make backup                                   # -> backups/nightshift-<utc>.dump
make restore FILE=backups/nightshift-....dump # OVERWRITES the current database
```

`backups/` is gitignored. Nothing in it is ever committed: it contains a real
person's job search.

## What a backup contains

Everything in the `nightshift` database — the corpus, the reader's account, the
`applications` table and its append-only event history, confirmed resume
extractions, and `user_sessions`.

`user_sessions` matters more than it looks. An MCP token is stored only as a
hash, so a restore brings back the *rows* but a token you never wrote down is
still gone. If Claude Desktop stops working after a restore, re-mint:
`nightshift tokens --create --merge-config` (see
`connecting-claude-desktop.md`).

## What it does not contain

- **Docker volumes as such.** This is a logical dump, not a filesystem copy.
  That is the point: it restores into a database that already has a schema, and
  it survives a Postgres version bump that a raw volume copy would not.
- **The embedding model and the map tiles.** Those are caches under
  `~/.cache/nightshift`, re-fetched by `make setup`.
- **`.env`.** Keep it yourself. It holds `POSTGRES_PASSWORD`, and a dump that
  carried its own credentials would be a worse thing to leave in a directory.

## Before `make reset-db`

`reset-db` drops the volume. Since M6a it prints what it is about to destroy —
jobs, applications, users — waits five seconds, and then does it anyway. It is
not a prompt. If the counts it prints matter to you, stop it and run
`make backup` first.

## Restoring somewhere else

`restore.sh` reads `POSTGRES_DB`, so a dump can be loaded into a database other
than the default without editing anything:

```bash
POSTGRES_DB=nightshift_scratch ./scripts/restore.sh backups/nightshift-....dump
```

That is how `test_backup_roundtrip.py` proves the pair works: it dumps the test
database, restores into a scratch database it creates and drops, and asserts a
specific application row arrives. The scratch database starts empty, so "the
row was not here before" is a fact rather than something the test arranged.

## When a restore reports errors

`pg_restore` exits non-zero on warnings it recovered from — an extension it
could not drop, an owner that does not exist locally. `restore.sh` prints those
and continues, because they are usually harmless and the useful check is the
data itself:

```bash
docker exec nightshift-postgres-1 psql -U nightshift -d nightshift -tAc \
  "select count(*) from applications; select count(*) from users;"
```

If those numbers match what you expect, the restore worked.

## Cadence

There is no scheduler for this. It is one person's laptop, and a cron job that
silently stops is worse than a habit. Run `make backup` after anything you would
hate to redo: confirming a resume, a batch of application updates, a milestone.
