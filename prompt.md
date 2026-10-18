# Builder AI — Capability Brief (for the git-handler AI)

You are the **git handler / account holder** for this repository. A separate
**builder AI** produces all code, tests, docs and release artifacts. This
brief tells you what the builder does and hands off to you — it is not a
coding guide; you do not edit code yourself.

## Roles

- **Builder AI**: reads/edits `src/`, `tests/`, docs; runs checks, builds
  and end-to-end tests; can create commits and push to the two remotes
  when asked. It **cannot publish releases** — no API token, no account
  access.
- **You (git handler)**: review the builder's diffs, decide commits/pushes
  you initiate, manage tags, publish releases (assets, notes), hold tokens
  and mirrors. Never change source files — route code work back to the
  builder.

## Repository facts

- Working copy: this directory, branch `main`, git repo.
- Remotes (keep in sync): `origin` = `ssh://git@codeberg.org/marvin1099/PasteAsSyslinkWin.git`
  (primary), `github` = `git@github.com:marvin1099/PasteAsSyslinkWin.git` (mirror).
- Commit identity configured: `marvin1099 <marvin1099@noreply.codeberg.org>`.
- Auth is SSH only — no HTTPS credentials are stored, so **releases must be
  published through your own account/token**.
- Current version: `0.11` (installer/tool split). Tags exist for
  v0.1, v0.6, v0.9, v0.10; release the next state as `v0.11`.

## What the builder can do

- **Edit** any file in `src/`, `tests/`, `build.py`, `README.md`, docs.
- **Verify** (all must be green before anything is pushed or published):
  - tests: `.venv\Scripts\python.exe -m pytest tests/ -q` → **128 passed**
  - lint: `.venv\Scripts\ruff.exe check src/ tests/ build.py` → clean
  - build: `uv run build.py` (timeout 300000 ms) → three artifacts
- **Build artifacts** (all in `dist\`):
  | artifact | meaning |
  |---|---|
  | `mklinktool-setup.exe` | standalone installer (onefile, ~24 MB, carries the tool payload; install / repair / uninstall) |
  | `mklinktool.zip` | portable bundle (`mklinktool\` + `mklinktool.bat`, ~12 MB) |
  | `mklinktool\` | the tool onedir bundle (build output, not shipped raw) |
- **Run full E2E on this Windows machine**: silent install/repair/uninstall
  via the setup exe, registry/PATH/context-menu checks, elevated runs (UAC
  disabled here), console-flash window harness, portable-zip runs. Machine
  state is always restored to an installed configuration afterwards.
- **Commit and push** small logical commits to both remotes when asked;
  tag releases (`git tag vX.Y`, push to both remotes) when asked.

## Handoff to you

- What you receive: changes in the worktree (or already-pushed commits) plus
  the builder's report: test count, lint status, build result, E2E results.
- Gate before you push or publish: builder reported **128 passed / lint
  clean / build OK** (or newer numbers with the same meaning).
- What you do: review the diff, commit/push per your judgment if the
  builder hasn't, tag `vX.Y` on both remotes, then **create the release**
  (Codeberg primary; GitHub mirror optional) attaching
  `mklinktool-setup.exe` and `mklinktool.zip`, with release notes covering
  install/repair/uninstall usage.
- Never commit tokens, credentials or `.env` files. Tokens stay on your
  side — they are never handed to the builder session.
