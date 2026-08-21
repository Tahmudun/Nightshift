# M5c — closing the Claude Desktop deviation

`docs/reviews/milestone-5c-acceptance.md` proved the thing that matters — a real
Claude model, in front of these tools, refusing to invent a street address under
pressure — and stated one deviation plainly: **Claude Desktop was not installed
on that machine, so the client was Claude Code.** `CLAUDE.md` §6 names Claude
Desktop specifically. This document closes that gap.

Claude Desktop was installed on 2026-08-21. What was unwalked, in the
acceptance document's own words, was *"Claude Desktop's own connection flow: its
config file location, its restart cycle, and its error surface."* Those three
are what this walk is about; the model-honesty half is already proved and is not
re-litigated here.

---

## 1. The config file, and the defect that was waiting in it

**The runbook was wrong about the file it sends people to edit**, and the way it
was wrong destroys data.

`nightshift tokens --create` prints a block shaped like a whole file:

```json
{
  "mcpServers": {
    "nightshift": { "command": "…", "args": ["-m", "nightshift.mcp"], "env": {…} }
  }
}
```

The runbook's only warning was *"If the file already has an `mcpServers` object,
add the `"nightshift"` entry inside it rather than replacing the whole object."*
That covers a second MCP server and nothing else.

What is actually on disk before Nightshift touches anything, on a Claude Desktop
installed an hour earlier and never configured:

```
$ python3 -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json
{
  "preferences": {
    "coworkWebSearchEnabled": true,
    "remoteToolsDeviceName": "macbookpro",
    "epitaxyPrefs": { … },
    "sidebarMode": "epitaxy",
    …
  },
  "coworkUserFilesPath": "/Users/tahmudun/Claude"
}
```

**No `mcpServers` key at all, and a `preferences` object holding the app's own
settings.** A reader following the runbook literally — paste the block into the
file — resets every Claude Desktop preference they have, and nothing tells them:
the app simply comes back different. The condition the warning was guarding
(`mcpServers` already present) is the *rarer* case; the common case is a file
that is not empty and not about MCP.

Fixed in three places, because a person reads whichever one they happen to hit:

- The CLI report now says **"merge this into `claude_desktop_config.json` — do
  not replace the file, it already holds Claude Desktop's own settings"**, with
  `test_the_report_warns_against_replacing_the_config_file` holding the wording.
- The runbook's step 2 is retitled *Merge it into Claude Desktop's config*,
  carries a backup step and a merge command, and explains why the block is a
  fragment.
- The runbook now says why `"command"` must be absolute: **Claude Desktop is a
  GUI application, so the server is launched with no login shell** — no
  `.zshrc`, no `PATH` additions, no `pyenv`, no activated virtualenv — and from
  a working directory that is not this repository.

The merge itself was done with the rest of the file preserved, verified by
comparing `preferences` keys before and after against a backup.

## 2. The launch environment, checked before the app was asked to do it

Rather than restart the app and read a log, the server was launched **exactly as
Claude Desktop launches it** — the command and env read out of the real config
file, a deliberately bare environment (`HOME`, `PATH=/usr/bin:/bin`, `TMPDIR`,
`USER` and nothing else), and `cwd="/"`:

```
initialize -> {'name': 'nightshift', 'version': '0.1.0'}
tools -> ['capture_posting', 'explain_match', 'get_job',
          'list_applications', 'search_jobs', 'whoami']
whoami -> {"id": "…0001", "email": "dev@nightshift.local",
           "display_name": "Nadia Okonkwo"}
exit: 0
stderr: (silent)
```

Six tools, the right account, a clean exit and a silent stderr, with none of the
developer's shell present. This is the check that would have caught a
`command` pointing at a `python` that only exists inside a shell profile — the
runbook's single most common failure and, until now, its least verified claim.

**It also found the second defect.** `serverInfo.version` came back as the empty
string: `MCPServer(...)` was constructed without a `version`, and the SDK
defaults it to `""`. That string is what Claude Desktop prints beside the
connector's name, so the first thing a person would have seen about Nightshift
is a connector with no version — which reads as broken before a single tool is
called. Now read from installed package metadata (`0.1.0`), deliberately not
from `health.py`'s `VERSION`, whose module opens a database session that ADR
0038 forbids this package from importing.

## 3. The error surface, walked rather than promised

The runbook promises three specific sentences. A promise about an error message
nobody has produced is documentation, not a runbook. All three were produced
against the real server:

| Config fault | What a person actually gets |
|---|---|
| `NIGHTSHIFT_MCP_TOKEN` missing | Server **exits 2 before the handshake**, stderr: `error: NIGHTSHIFT_MCP_TOKEN is not set.` and the exact `nightshift tokens` command to fix it |
| A token the database has never seen | Tool error: `Nightshift rejected this token. Mint a new one with …, paste it into claude_desktop_config.json, and restart Claude Desktop.` |
| A live token, API on the wrong port | Tool error: `Nightshift's API is not reachable at http://localhost:8099. Start it with make dev …` — and **`No conclusion should be drawn about the corpus from this failure.`** |

The third row is invariant I3 enforced in the one place it can be enforced
against a language model: the sentence the model reads. An unreachable API
returns an error, never an empty list, because *"there are no jobs open"* and
*"I could not ask"* must not look the same to a reader.

Note the first row's shape: a missing token is fatal **before** the handshake,
so Claude Desktop shows a server that failed to start rather than a connector
that works until the first tool call. That is deliberate and `__main__.py`
records why.

---

## 4. The live conversation

*Pending — this is the human's half, and it is the half that cannot be
automated.*

<!-- Filled in from the real Claude Desktop session: the connector appearing,
     whoami, the adversarial address prompt, and the capture. -->

## 5. What this walk changes

| Claim | Before | After |
|---|---|---|
| The config path and file shape | Documented, unwalked | **Walked, and the documentation was wrong in a way that loses data** |
| Launch under a GUI environment | Assumed | **Proved: bare env, `cwd=/`, six tools, exit 0** |
| The connector's identity in the UI | Unexamined | **Was blank; now `nightshift 0.1.0`** |
| The three troubleshooting messages | Promised | **Produced, verbatim** |
| A model in front of the tools staying honest | Proved (Claude Code) | Unchanged — see `milestone-5c-acceptance.md` |
| Claude Desktop end to end | **Not walked** | *Pending §4* |
