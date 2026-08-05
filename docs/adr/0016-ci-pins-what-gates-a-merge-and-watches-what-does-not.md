# ADR 0016 — CI pins what gates a merge, and an unpinned canary watches what does not

- **Status:** accepted
- **Date:** 2026-08-05
- **Milestone:** between M3a and M3b
- **Relates to:** `docs/QUESTIONS.md` Q3 (answered by this ADR), AMENDMENTS A14 (CI scope), `CLAUDE.md` §4

## Context

CI installed with `pip install -e "services/api[dev]"` and no pin of any kind, so
every run resolved whatever was newest on PyPI that minute. On 2026-08-05 that
was alembic 1.19.0, released with a check-constraint comparator that
autogenerate had never had. The migrations job went red on a branch that had not
touched a migration in a week.

**It was right to go red.** The drift was real: ten check constraints had been
carrying a doubled `ck_` prefix in the database since 2026-07-29, because five
migrations wrote the *rendered* constraint name into `name=` and
`op.create_table` applied the naming convention again on top. Nothing
behavioural could see it — each constraint enforced exactly what it was written
to enforce — and no local command ran a drift probe at all.

So the question is not "was pinning obviously right". Pinning would have
suppressed a true bug report, and that is the strongest argument against it.

The two things at stake are separable, which is the useful framing and the one
Q3 was written around:

- **Reproducibility.** A given commit should build the same way in six months.
  That argues for a pin.
- **Early warning.** This project should learn about a breaking release from its
  own CI rather than from a future upgrade under deadline. That argues for
  something unpinned, somewhere.

They only conflict if there is one place to install.

## Decision

**Two places to install. The one that gates a merge is pinned; the one that
gates nothing is not.**

### 1. `services/api/constraints-ci.txt`, applied through `PIP_CONSTRAINT`

A generated constraints file listing 72 distributions at exact versions. It is
wired in as a single workflow-level `env` entry in `ci.yml`, not as a flag added
to three install steps — pip maps `PIP_<OPTION>` to the option of the same name,
so every `pip install` in every job reads it and there is no way for the three
to drift apart.

A constraints file rather than a requirements file, because the *set* of
dependencies stays declared in `pyproject.toml` where it belongs. The
constraints file only says which versions, and never which packages.

### 2. It is generated on linux, in a container, and that is not fastidiousness

`make constraints` runs `scripts/regenerate_constraints.sh`, which resolves
inside `python:3.12-slim` on `linux/amd64` — the platform a GitHub runner is.

Freezing the developer's venv instead was the obvious cheap option and it does
not work. Measured 2026-08-05, the two environments disagree about eleven
distributions, and one disagreement cannot be reconciled at any version:

```
onnxruntime      1.28.0 on linux/amd64
                 1.23.2 is the newest release with a macOS x86_64 wheel
```

A file frozen from this machine would have pinned CI to versions that resolve
differently there, and a file generated for CI cannot be applied locally. **The
consequence is stated rather than hidden: this pin covers CI and does not cover
a developer's machine.** The file's own header says so.

### 3. The pin is checked, not assumed

`-c` constrains only the distributions the file names. Add a dependency to
`pyproject.toml`, forget to regenerate, and it installs at whatever is newest
along with its transitive tree — the pin silently becomes partial while
everything continues to call it a pin. That is precisely the failure class this
project keeps finding.

So the `python` job compares `pip freeze` against the file and fails on any
difference, in either direction. "CI is pinned" is a checked claim.

### 4. `.github/workflows/dependency-canary.yml` installs unpinned, weekly

It runs on `schedule` and `workflow_dispatch` only — never on `pull_request`,
never on `push`. It therefore *cannot* gate a merge, and no branch protection
rule should ever require it.

It runs the checks a library release can break: ruff format, ruff check, mypy,
the pytest suite, and migrate → downgrade → migrate → drift probe. The last one
is the step that earned the workflow.

Every run, red or green, writes a diff of the unpinned resolution against the
committed pin to the job summary. A green run listing eleven upgrades is the
evidence for running `make constraints`; a red run tells you which release to
go and read.

Notification is GitHub's default email to the repository owner on a failed
scheduled run on the default branch. No bot, no issue-filing: one reader does
not need a queue, and a queue nobody empties is worse than an email.

### 5. `make drift`, which is a separate gap this episode exposed

The drift probe existed only in CI. "It passes locally" and "it passes in CI"
were therefore never the same claim about the schema, which is why a defect
eleven migrations old could sit there. `make drift` runs the probe against the
developer's own stack and is part of `make acceptance` — not of `make check`,
which must keep working without a database.

Shown able to fail rather than assumed to work: adding a `mutation_probe` column
to the `Company` model makes it print both `op.add_column` and `op.drop_column`
and exit 1, and the temporary revision file is cleaned up on the failure path
too.

## Consequences

**A release can no longer turn an unrelated pull request red.** That is the
point, and it is also the thing given up: the alembic finding arrived for free
and would now arrive up to seven days later, from the canary, on a Monday.
Seven days is the price. It is paid deliberately, and the alternative — an
unpinned merge gate — is what cost a session's attention at the exact moment a
branch was ready to merge.

**Adding a dependency is now two steps.** Edit `pyproject.toml`, then run
`make constraints` and commit the result. Forgetting the second step fails CI
with a diff and the exact command to run.

**`make constraints` needs docker and the network.** Neither is needed for
`make demo`, `make check` or `make acceptance`, so A9's offline requirement is
untouched. It is a maintainer's command run when `pyproject.toml` changes.

**The pin is versions, not hashes.** It defends against an unexpected release,
not against a compromised one. `--require-hashes` would defend against both and
would make every regeneration a much larger diff; supply-chain integrity is not
what went wrong here and is not what this decision is buying. If it is ever
wanted it is a change to the same file and a flag.

**Node is untouched.** `npm ci` against a committed `package-lock.json` is
already a lockfile with hashes. There is no unpinned surface on the web side for
a canary to watch, which is why the canary is Python-only.

**pip, the runner image, and the Postgres service tag are still floating.**
`actions/setup-python` resolves 3.12.x to whatever it has, `ubuntu-latest`
changes under us, and `pip install --upgrade pip` takes the newest pip. Pinning
those is a different and larger decision about reproducibility, and this ADR
does not take it. Named here so nobody reads "CI is pinned" as broader than it
is.

## What was rejected

**Pinning everything and deleting the early warning.** It buys quiet and it is
how a project arrives at a twelve-version alembic upgrade with forty
autogenerate operations in it, at the worst possible moment.

**Leaving everything unpinned.** The status quo, and it works right up until a
release lands mid-review. It also makes a green CI run un-reproducible: the same
commit re-run next month tests a different dependency set, which quietly weakens
every "CI is green at `<sha>`" claim in `PROGRESS.md`.

**A lockfile tool — uv, poetry, pip-tools.** All three would do this better, and
all three are a new toolchain in a repo whose entire Python setup is `venv` plus
`pip`, with a Makefile that assumes it. `CLAUDE.md` §8 forbids adding
infrastructure for a problem that a constraints file and eleven lines of shell
already solve. Worth revisiting if the dependency set ever needs environment
markers or per-platform resolution, which is exactly where this approach runs
out.

**Failing the canary softly with `continue-on-error`.** A green check mark on a
run that found something is a lie told to whoever glances at the Actions tab.
"Informational" is enforced by *where it runs* — not on pull requests — rather
than by hiding its result.
