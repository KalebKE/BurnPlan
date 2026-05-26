# BurnPlan

BurnPlan is a project tuning tool for repositories maintained by humans and coding agents.

Skyhook tells an agent where to read. BurnPlan adds the longer-lived layer around that map: project intent, architecture direction, code health evidence, team routing, generated documentation proposals, and a record of what agents changed and why.

## The Problem

A code map is useful, but it does not answer enough by itself.

Agents also need to know:

- what the product is supposed to do
- which architecture choices are intentional
- which docs are missing, stale, or scattered
- where churn and coupling suggest weak spots
- which team or subagent should handle a class of work
- what previous agents changed and why they made those choices

Without that context, every session starts from the same shallow scan. Work may still get done, but the repository does not get easier to work in over time.

## How BurnPlan Solves It

BurnPlan consumes or refreshes a Skyhook map, then writes a project ratchet under `.burnplan/`.

The core artifacts are:

- `.burnplan/onboarding.md`: product, architecture, goals, risks, and documentation preferences
- `.burnplan/quality.md`: lightweight churn, coupling, volatility, and static-analysis evidence
- `.burnplan/agent-prompts.md`: guidance agents should read before working
- `.burnplan/documentation-ledger.md`: known documentation inventory and gaps
- `.burnplan/proposals/docs/`: reviewable architecture, design, testing, code health, and ADR drafts
- `.burnplan/proposals/agents/`: reviewable agent team definitions
- `.burnplan/worklog/`: what changed
- `.burnplan/rationale/`: why it changed

BurnPlan is deliberately review-first. It writes proposals under `.burnplan/proposals/` and only copies them into human-owned docs or agent directories when you run `burnplan promote`.

## Why It Works This Way

Generated documentation should not become project truth just because a tool wrote it. BurnPlan keeps generated proposals separate until someone reviews them.

The ratchet is file-based because it needs to work in normal local repos, CI runners, and agent harnesses without a database or service. Files can be committed, reviewed, diffed, edited, or ignored.

The quality analysis is lightweight on purpose. BurnPlan looks for useful signals such as churn, co-change coupling, volatile areas, static-analysis configuration, and missing architecture docs. It is meant to point agents toward weak spots, not pretend to replace deeper analysis.

The team model is also plain data. BurnPlan ships with opinionated Product Owner and Project Manager teams, but users can edit `.burnplan/teams.json` or supply their own mapping.

## Relationship To Skyhook

Use Skyhook for fast wayfinding:

- `.skyhook/INDEX.md`
- `.skyhook/map.md`
- `.skyhook/map.json`
- `.skyhook/docs.md`
- `.skyhook/architecture.md`
- `.skyhook/routes/`

Use BurnPlan for the ratchet:

- onboarding and project intent
- quality and weak-point evidence
- documentation proposals
- agent team definitions
- worklog and rationale entries
- routing teams through Skyhook profiles

BurnPlan imports Skyhook. When `burnplan onboard` or `burnplan optimize` runs, it can refresh `.skyhook/` first and then build BurnPlan artifacts from the current map.

## Install

From sibling checkouts:

```sh
python3 -m pip install -e ../Skyhook -e .
```

From another repository or a remote runner:

```sh
python3 -m pip install \
  "git+https://github.com/KalebKE/Skyhook.git" \
  "git+https://github.com/KalebKE/BurnPlan.git"
```

Run without installing by adding Skyhook to `PYTHONPATH`:

```sh
PYTHONPATH=../Skyhook python3 -m burnplan --help
```

## First Setup

From the repository you want to tune:

```sh
burnplan onboard
```

In automation or when you want a noninteractive first pass:

```sh
burnplan onboard --provider static --no-interview
```

Initialize editable team behavior mappings:

```sh
burnplan teams init
```

Review the generated files under `.burnplan/proposals/`. When the proposed docs are good enough to become project docs:

```sh
burnplan promote docs
```

When the proposed agent specs are good enough to install:

```sh
burnplan promote agents
```

Promotion refuses to overwrite existing files unless `--force` is supplied.

## Configuration

Optional BurnPlan config lives at `.burnplan/config.yaml`.

```yaml
version: 1
outputDir: .burnplan
mapDir: .skyhook
quality:
  sinceDays: 90
  maxCommits: 1000
```

Optional Skyhook config lives at `.skyhook/config.yaml`.

```yaml
version: 1
outputDir: .skyhook
model:
  provider: auto
  model: auto
scan:
  include:
    - .
  exclude:
    - build
    - dist
    - node_modules
    - .git
    - .gradle
    - .burnplan
  maxFiles: 5000
docs:
  extraGlobs:
    - "docs/**/*.md"
    - "adr/**/*.md"
    - "architecture/**/*.md"
    - "**/*ADR*.md"
    - "**/*C4*.md"
```

The YAML parser intentionally supports a small subset. Neither Skyhook nor BurnPlan requires PyYAML.

## Model Provider

BurnPlan delegates repository mapping to Skyhook. Skyhook supports an OpenAI-compatible chat completions endpoint through the Python standard library.

Environment variables:

- `OPENAI_API_KEY` or `SKYHOOK_API_KEY`
- `OPENAI_BASE_URL` or `SKYHOOK_BASE_URL`
- `SKYHOOK_MODEL`

If no API key is available and provider is `auto`, Skyhook uses static mode. That keeps BurnPlan usable on local machines and remote runners.

## Commands

### `burnplan onboard`

Run this when introducing BurnPlan to a repo or when the project direction has changed enough that the old onboarding notes are misleading.

```sh
burnplan onboard
```

When attached to a terminal, BurnPlan asks about functional requirements, non-functional requirements, architecture intent, short-term goals, long-term goals, risk areas, and documentation preferences.

For a noninteractive pass:

```sh
burnplan onboard --provider static --no-interview
```

### `burnplan optimize`

Run this before committing, opening a PR, or handing work to another agent:

```sh
burnplan optimize
```

It refreshes the Skyhook map, quality evidence, onboarding guidance, agent prompts, documentation ledger, and proposal drafts.

Use dry-run as a gate:

```sh
burnplan optimize --dry-run
```

Dry-run exits `1` when generated artifacts would change and `0` when they are current.

### `burnplan document`

Run this when an agent finishes material work:

```sh
burnplan document \
  --area sync \
  --what "Added retry handling" \
  --why "Transient failures should be explicit and recoverable."
```

It writes separate entries:

- `.burnplan/worklog/<timestamp>-<slug>.md`
- `.burnplan/worklog/<timestamp>-<slug>.json`
- `.burnplan/rationale/<timestamp>-<slug>.md`
- `.burnplan/rationale/<timestamp>-<slug>.json`

Use `--from-git` to fill `--what` from local git status and diff stats. `--why` is still required.

### `burnplan teams init`

Write the default Product Owner and Project Manager team mapping:

```sh
burnplan teams init
```

The default preset maps:

- `product-owner story` to `product_planning`
- `product-owner requirements` to `requirements_planning`
- `project-manager breakdown` to `technical_breakdown`
- `project-manager implement` to `implementation`
- `project-manager review` to `code_review`
- `project-manager bugfix` to `bug_hunt`

The default subagents cover product stories, requirements, acceptance criteria, technical breakdowns, implementation, code review, and bug hunting. Edit `.burnplan/teams.json` when your organization wants different names, behaviors, or route profiles.

### `burnplan assign`

Route a task through a team behavior:

```sh
burnplan assign \
  --team project-manager \
  --behavior implement \
  --task-file issue.md
```

BurnPlan resolves the behavior to a Skyhook route profile, refreshes `.skyhook/` if needed, and prints a route pack.

Emit JSON for an orchestrator:

```sh
burnplan assign \
  --team product-owner \
  --behavior story \
  --task "Plan checkout retry handling" \
  --format json
```

Persist the generated route under `.skyhook/routes/`:

```sh
burnplan assign --team project-manager --behavior review --task-file pr-notes.md --save
```

### `burnplan promote`

Promote reviewed proposal drafts:

```sh
burnplan promote docs
burnplan promote agents
burnplan promote all
```

Documentation promotion writes to `docs/`, including architecture, design, code map, testing, code health, agent operating model, and an initial ADR.

Agent promotion writes generic agent specs to `docs/agents/` and Claude-style subagent files to `.claude/agents/`.

## When To Rerun

Run `burnplan onboard`:

- when adding BurnPlan to a repository
- after a significant product direction change
- after a major architecture change
- when existing onboarding notes are stale enough to mislead agents

Run `burnplan optimize`:

- before opening a PR
- before handing a repo to another agent session
- after a large refactor or module move
- after adding important docs, tests, or architecture decisions
- periodically after worklog and rationale entries accumulate

Run `burnplan document` after material agent work. It is most useful when the entry captures both what changed and why the approach was chosen.

Run `burnplan promote` only after reviewing proposals. Promotion is intentionally explicit because generated docs should not silently overwrite project truth.

## Quality Evidence

BurnPlan currently mines lightweight evidence from git history:

- hotspots from recent churn
- repeated file co-changes as coupling hints
- volatile top-level areas
- detected static-analysis configuration
- documentation weak points such as missing ADRs or architecture docs

It discovers static-analysis tools but does not execute them yet.

## CI Example

Use dry-run when generated artifacts are expected to be current:

```yaml
name: burnplan

on:
  pull_request:

jobs:
  optimize-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: |
          python3 -m pip install \
            "git+https://github.com/KalebKE/Skyhook.git" \
            "git+https://github.com/KalebKE/BurnPlan.git"
      - run: burnplan optimize --provider static --dry-run
```

Adjust install paths for your checkout layout. In many repos, BurnPlan will be installed from a package or tool cache rather than directly from Git.

## Development

```sh
PYTHONPATH=../Skyhook python3 -m unittest discover -s tests -v
PYTHONPATH=../Skyhook python3 -m burnplan onboard --provider static --no-interview --dry-run
PYTHONPATH=../Skyhook python3 -m burnplan optimize --provider static --dry-run
PYTHONPATH=../Skyhook python3 -m burnplan assign --team project-manager --behavior implement --task "add retry handling"
PYTHONPATH=../Skyhook python3 -m burnplan onboard --provider static --no-interview
PYTHONPATH=../Skyhook python3 -m burnplan promote docs
```
