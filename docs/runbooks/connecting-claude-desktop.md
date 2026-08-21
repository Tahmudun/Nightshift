# Connecting Claude Desktop to Nightshift

**What this gets you.** Your own Claude can search the job corpus, explain a
match's score, read your application pipeline, and capture a posting you paste
into the conversation. Nightshift never calls a model and there is no API bill —
the model is the Claude you already pay for. ADR 0038.

**What it deliberately cannot do.** Claude can suggest and surface. It cannot
confirm a captured posting, change an application's stage, or apply to
anything. Those stay in Nightshift, done by you, because approving a *tool call*
is not the same as reviewing a parsed job title (invariant I5).

---

## Setup

### 1. Mint a token

```
services/api/.venv/bin/python -m nightshift.cli tokens \
  --email you@example.com --create --label "claude desktop"
```

It prints the token **once** — only its SHA-256 reaches the database, so there
is no way to look it up again — followed by the exact JSON block to paste.

### 2. Merge it into Claude Desktop's config

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
Windows: `%APPDATA%\Claude\claude_desktop_config.json`

**Merge, do not paste over.** On a current Claude Desktop this file already
exists before you touch it, and it is not empty and not only about MCP — it
holds the app's own `preferences` object (sidebar mode, per-account settings,
your user-files path). Replacing the file with the printed block silently
throws all of that away, and nothing tells you: the app just comes back with
its settings reset. The block is printed as a *fragment* to add, and the
warning it deserves is stronger than the one about a second server.

On macOS this merges it without disturbing anything else, backup first:

```
CFG=~/Library/Application\ Support/Claude/claude_desktop_config.json
cp "$CFG" "$CFG.backup"
python3 - "$CFG" <<'EOF'
import json, sys
path = sys.argv[1]
cfg = json.load(open(path))
cfg.setdefault("mcpServers", {})["nightshift"] = json.loads(input(
    "paste the nightshift entry (the inner object), then Enter: "))
json.dump(cfg, open(path, "w"), indent=2)
EOF
```

Or edit it by hand: add an `mcpServers` key at the top level beside
`preferences`, and put the `"nightshift"` entry inside it.

**`"command"` must be the absolute path to this repository's virtualenv**,
which is what `--create` prints. Not `python`, not `python3`, not a path that
relies on a shell.

Claude Desktop does pass a reasonable `PATH` — it is close to your login
shell's, and it logs the one it used. What it cannot do is *activate* a
virtualenv, and that is the part that bites. A bare `python3` resolves to
whichever system Python that `PATH` finds first, and on a machine where this
repo has been installed in editable mode that interpreter **can still import
`nightshift`** — the editable install leaves it on `sys.path` for every
interpreter you own. So the obvious sanity check passes, and the server dies
one import later:

```
ModuleNotFoundError: No module named 'httpx'
```

The venv's own interpreter is the only one with the dependencies. It also
launches from a working directory that is not this repository, which the
absolute path handles and a relative one does not.

### 3. Start Nightshift, then restart Claude Desktop

```
make dev
```

Claude Desktop reads its config only at launch, so quit it fully — on macOS
`Cmd-Q`, not just closing the window — and reopen.

### 4. Check the link

Ask Claude: **"which Nightshift account am I connected to?"** It should call
`whoami` and answer with your email. If it does, everything downstream works.

### 5. Sign in to the website as that same account

**The token's account and your browser session are independent, and nothing
reconciles them.** A token minted for one account, and a browser signed in as
another, is a working setup in which every capture Claude makes lands in a
review queue you are not looking at. Nothing warns you — you see an empty
queue, which is what an empty queue looks like.

That separation is deliberate and it is M5b's isolation doing its job: a
capture belongs to one account and no other account can see it, including
yours. But it means the answer `whoami` gives you in step 4 is the account you
must be signed in as at http://localhost:3000, or the last step of every
capture goes somewhere you cannot reach.

Mint the token for the account you actually use. If you are walking this with
the seeded demo reader, `make seed` prints its password.

---

## When it does not work

### Claude does not offer any Nightshift tools

The server never started. Claude Desktop captures the server's **stderr** to a
log file, and on macOS that file is:

```
~/Library/Logs/Claude/mcp-server-nightshift.log
```

`~/Library/Logs/Claude/mcp.log` beside it carries the same lines for every
server plus the protocol traffic. A healthy connection looks like this — the
absolute path it launched, then the handshake:

```
[nightshift] [info] Using MCP server command: /…/services/api/.venv/bin/python
[nightshift] [info] Server started and connected successfully
[nightshift] [info] Message from client: method="initialize" id=0 params
[nightshift] [info] Message from server: id=0 result
[nightshift] [info] Message from client: method="tools/list" id=1 params
```

If `tools/list` never gets a result, the process died during import and the
traceback is above it in that same file.

Run the server by hand to see the error directly:

```
NIGHTSHIFT_API_URL=http://localhost:8000 \
NIGHTSHIFT_MCP_TOKEN=<your token> \
services/api/.venv/bin/python -m nightshift.mcp
```

It will sit silently waiting for JSON-RPC on stdin — **that is success.** Press
`Ctrl-D`. If instead it prints an error and exits, that error is the problem.

The most common cause is `"command"` in the config pointing at the wrong
Python. It must be this repository's virtualenv, not whatever `python` resolves
to inside Claude Desktop's environment. `nightshift tokens --create` fills in
the right absolute path; a hand-edited config often does not.

### Every tool answers "Nightshift's API is not reachable"

`make dev` is not running, or it is on a different port. That message is
deliberate: an unreachable API **never** returns an empty result, because
"there are no jobs open" and "I could not ask" must not look the same to a
reader (invariant I3).

### Every tool answers "Nightshift rejected this token"

The token expired, was revoked, or was pasted wrong. Check what is live:

```
services/api/.venv/bin/python -m nightshift.cli tokens --email you@example.com --list
```

Then mint a new one and paste it again. The listing never prints a token or its
hash — it shows ids, labels and expiry, which is what you need to choose one to
end.

### Claude states a job's street address

**Stop and report this.** Every location this server returns carries a
`confidence` and a plain-English `means` field, and a `city_only` role has no
known address. Claude inventing one is invariant I1 being broken at the only
layer that can enforce it — the tool descriptions — and it is a bug in the
description, not in the model.

---

## Ending a token

```
services/api/.venv/bin/python -m nightshift.cli tokens \
  --email you@example.com --list
services/api/.venv/bin/python -m nightshift.cli tokens \
  --email you@example.com --revoke <id>
```

Revoking an MCP token does not sign you out of the website, and signing out of
the website does not unplug Claude Desktop. They share a table and not a fate.

**An MCP token has the same power as a browser session** — it is not scoped or
read-only, and it sits in a plaintext config file. Treat it like a password,
and revoke it if the machine holding it is no longer yours.
