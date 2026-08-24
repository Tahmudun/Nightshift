# Docker will not start

**Symptom.** Every `docker` command fails the same way, while Docker Desktop
looks like it is running — its icon is in the menu bar, its window opens:

```
failed to connect to the docker API at unix:///Users/…/.docker/run/docker.sock;
check if the path is correct and if the daemon is running:
dial unix /Users/…/.docker/run/docker.sock: connect: no such file or directory
```

`make up`, `make migrate`, `make seed`, `make acceptance` and every test that
needs a database all fail downstream of this, in ways that do not name Docker.

**The socket is missing rather than refusing.** That distinction matters: a
refused connection means the daemon is up and unhappy, a missing socket means
the Linux VM that would have created it never started.

## Check first — did the VM even try?

```
tail -5 ~/Library/Containers/com.docker.docker/Data/log/host/com.docker.virtualization.log
```

- **The newest line is from a previous day, and you have restarted Docker
  since** → the VM never attempted to start. A healthy start writes
  `starting with pid …`, `running VM`, `VM has started` every single time.
  This is the case the rest of this runbook is about.
- **There are fresh lines ending in an error** → the VM tried and failed. Read
  the error; this runbook will not help.

Then check why it died in the first place:

```
df -h /System/Volumes/Data
grep -c "no space left on device" \
  ~/Library/Containers/com.docker.docker/Data/log/host/*.log
```

## What happened on 2026-08-23

**The disk filled to zero bytes.** Docker's VM was mid-write and could not even
log its own death:

```
[com.docker.virtualization.CrashDetectorPKG][W] logging console:
  write …/log/vm/console.log: no space left on device
```

Docker Desktop's backend then failed to write *its* log for the same reason,
put up an error dialog, and stopped. Space was reclaimed by macOS afterwards,
so by the time anyone looked, `df` reported 12 GB free and the disk looked
innocent. **The evidence that it was ever full is only in the logs.**

**And then the part that makes this a runbook rather than a footnote: quitting
Docker Desktop did not fix it.** `osascript -e 'quit app "Docker Desktop"'`
returned cleanly, `pkill -f "com.docker.backend"` reported nothing, and
`open -a Docker` relaunched the app — and the daemon still never came up, for
**seven minutes** of polling. The virtualization log stayed silent the whole
time, which is the tell: the app was starting, and the VM was not.

The cause was a single `com.docker.backend` process left over from before the
crash. **It ignores `SIGTERM`.** A normal quit does not remove it, `pkill`
without `-9` does not remove it, and while it exists a relaunched Docker
Desktop attaches to the dead instance instead of building a new VM. Nothing
on screen says so.

## Fix

Kill every Docker host process outright, confirm they are gone, then relaunch:

```
pkill -9 -f "com.docker"
pkill -9 -f "Docker Desktop"
ps aux | grep -i docker | grep -v grep
```

**The only line that should survive is the root-owned privileged helper**,
`/Library/PrivilegedHelperTools/com.docker.vmnetd`. It is meant to persist and
killing it is not necessary. If any process owned by you is still listed, the
fix will not work — kill it before going on.

```
open -a Docker
```

The daemon came back in about twenty seconds, with both project containers
running and their data intact.

Confirm, rather than assuming:

```
docker info --format 'Server {{.ServerVersion}} | running {{.ContainersRunning}}'
docker compose -f infra/docker-compose.yml ps
curl -s http://localhost:8000/health
```

`/health` is the honest one — it reports the database and Redis separately and
will tell you if Postgres came back but Redis did not.

## After the daemon is back, check the MCP token

**A crash does not destroy tokens, but the recovery people usually reach for
does.** If anyone ran `make reset-db` while working around this — and it is a
natural thing to try when the database looks wrong — every Claude Desktop and
Claude Code connection is now broken, silently, and every Nightshift tool
answers `Nightshift rejected this token`.

See `connecting-claude-desktop.md`, *"Every tool answers Nightshift rejected
this token"*. Nothing can restore a destroyed token; mint a new one.

Check without waiting to be surprised:

```
services/api/.venv/bin/python -m nightshift.cli tokens \
  --email dev@nightshift.local --list
```

**A token you hold in a config file is not proven live by being present.**
Prove it against the API, which is exactly what `whoami` does:

```
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/auth/me
```

`{"detail":"not signed in"}` is a dead token. An email address is a live one.

**Do not extract a minted token with `grep -o 'nsk_[A-Za-z0-9]*'`.** Tokens
contain characters outside that class, so it returns a *truncated* token that
looks entirely plausible — right prefix, wrong length — and fails
authentication for a reason that has nothing to do with the token being wrong.
This runbook's author did it, installed a 20-character token, and spent the
next step debugging the wrong thing. Match the whole non-space run instead:

```
sed -n 's/^[[:space:]]*\(nsk_[^[:space:]]*\)[[:space:]]*$/\1/p'
```

Or let the CLI write the config itself with `--merge-config`, which is the
supported path and does not involve parsing output at all.

## Then restart the web dev server, which the outage probably wedged

**A `next dev` that ran through the outage does not recover when the API comes
back.** On 2026-08-24 the server had been up 21 hours, straddling the crash. Once
Docker returned, `/` served a `200` — and twenty minutes later **every route
hung**, `/` included, with `next-server` pegged at **111% CPU**. It was not
compiling; it was spinning.

The measurement that distinguishes the two, because a slow first compile looks
identical from outside:

```
ps -o pid,etime,time,%cpu -p $(lsof -ti:3000)
sleep 5
ps -o pid,time -p $(lsof -ti:3000)
```

**If `TIME` advances by roughly the five seconds you waited, it is burning CPU
continuously** and will not finish. A compile that is genuinely working shows
the same thing briefly, so give it one honest minute before concluding — but a
process 22 hours old with four minutes of total CPU that suddenly spends all of
it is not compiling.

Restart only the web side; the API survives an outage fine and was serving
`/health` and `/capture` correctly throughout:

```
kill -9 $(lsof -ti:3000)
cd apps/web && npm run dev
```

Ready in three seconds, `/` in six, `/operate/capture` in two, and the process
back to 0.0% CPU. **Check that last number** — a server that comes up and
immediately spins again is a different problem, and the `200` on the first
request will not tell you.

## The standing risk

**This will happen again unless the disk gets headroom.** At the time of the
incident the volume was 95% full — 205 GB used of 233 GB — and the largest
single consumer was `~/Downloads` at **78 GB**, which is roughly a third of the
disk and none of it this project's.

`docker builder prune -af` reclaims Docker's build cache, and on 2026-08-23 it
freed 2.5 GB — **inside the VM, where macOS cannot see it.** `Docker.raw` is a
sparse file that grows and does not shrink, so the host's free space did not
move by a single byte. It is worth running and it is not a fix for a full disk.

The fix for a full disk is deleting things that are not Docker's.
