# Tasks

Companion to `requirements.md` and `design.md` in this folder.
`R*` / `#*` / `P*` / `D*` / `N*` ids refer to those documents.

> **`T-##` are task labels; the manifest ids are real.** Each task carries an **Id** field holding its
> manifest id (e.g. `MMA-6050-a`), mapped in the **Jira ticket grouping** table below. `T-##` remains only
> as a short handle for cross-references within this document.

Each ticket carries: **Module** (primary Gradle path, or `—` for shared-lib/spike),
**Covers** (requirement ids), **Depends** (ticket ids), **QA** (Story = user-visible, Task = internal),
**Project**, **Size**, and — for tickets that add screen UI — **Owns** (the file it is the sole editor of).

---

## Prerequisites (not this repo)

| id | Ticket | Status | Repo | Task | Blocks |
|---|---|---|---|---|---|
| | | | | | |

---

## Jira ticket grouping

The `T-##` items are **parts** of tickets, not tickets. Several tasks roll up to one Jira ticket for
tracking, while each keeps its own dependencies and file ownership for the orchestrator.

**Id scheme.** The manifest's `id` becomes the branch name and worktree directory; manifest ops select on
`.id==$id` and the schema sets `additionalProperties: false` — so there is no `jira` field to add and two
tasks cannot share an `id`. Instead:

* a group with **one** task uses the bare key — `MMA-4494`;
* a group with **several** uses suffixes — `MMA-1234-a`, `MMA-1234-b`, …

Either way the Jira key is the prefix, so branches, commit messages and PR titles all lead with it.

| # | Jira ticket | Key | QA | Tasks → manifest id |
|---|---|---|---|---|
| 1 | | | | |

---

## Pre-handoff checklist

| | Item | Status |
|---|---|---|
| | | |

---

## Phase 1 — Foundations (no feature code; unblocks everything)

### T-01 ·

**Module** `—` · **Covers** — · **Depends** — · **QA** Task · **Project** MMA · **Size** S
**Id** `MMA-6048`

---

> Ready for the real project spec. Replace the sections above with the actual tickets; the
> pipeline (`gen_board.py`, `dag.py`, `reconciler.py`) reads the `### T-##` headers and their
> **Module** / **Covers** / **Depends** fields.
