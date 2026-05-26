# BurnPlan

BurnPlan is the tuning ratchet for agent-maintained repositories.

It consumes or refreshes a Skyhook code/documentation map, adds onboarding guidance, mines lightweight quality evidence from git history, and records what agents changed and why. The goal is not a comprehensive index. The goal is durable project memory that gets better as a team or coding-agent fleet works in the repo.
It also generates reviewable project documentation and agent-team definitions, then promotes them into the repo only when you explicitly ask it to.

## Relationship To Skyhook

Use Skyhook for fast wayfinding:

- `.skyhook/map.md`
- `.skyhook/map.json`
- `.skyhook/docs.md`
- `.skyhook/architecture.md`

Use BurnPlan for the ratchet:

- `.burnplan/onboarding.md`
- `.burnplan/quality.md`
- `.burnplan/agent-prompts.md`
- `.burnplan/documentation-ledger.md`
- `.burnplan/proposals/docs/`
- `.burnplan/proposals/agents/`
- `.burnplan/worklog/`
- `.burnplan/rationale/`

BurnPlan imports Skyhook and can refresh the map before generating ratchet artifacts.
BurnPlan can also map team behaviors onto Skyhook route profiles, so a product
or project-management agent receives context shaped for the kind of work it is doing.

## Install

From sibling checkouts:

```sh
python3 -m pip install -e ../Skyhook -e .
```

Run without installing by adding Skyhook to `PYTHONPATH`:

```sh
PYTHONPATH=../Skyhook python3 -m burnplan --help
```

## Commands

### `burnplan onboard`

Run this when introducing BurnPlan to a repo:

```sh
burnplan onboard
```

When attached to a terminal, BurnPlan asks a short interview about functional requirements, non-functional requirements, architecture intent, short-term goals, long-term goals, risk areas, and documentation preferences.

For CI, automation, or first-pass tuning:

```sh
burnplan onboard --provider static --no-interview
```

This writes or refreshes Skyhook map artifacts in `.skyhook/`, then writes BurnPlan artifacts in `.burnplan/`.
It also writes reviewable proposal drafts under `.burnplan/proposals/`.

### `burnplan optimize`

Run this before committing, opening a PR, or handing work to another agent:

```sh
burnplan optimize
```

It refreshes the Skyhook map, quality evidence, onboarding guidance, agent prompts, documentation ledger, and proposal drafts.

Use it as a pre-PR gate:

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

It writes `.burnplan/teams.json`. The default preset maps:

- `product-owner story` -> `product_planning`
- `product-owner requirements` -> `requirements_planning`
- `project-manager breakdown` -> `technical_breakdown`
- `project-manager implement` -> `implementation`
- `project-manager review` -> `code_review`
- `project-manager bugfix` -> `bug_hunt`

Users can edit `.burnplan/teams.json` to define their own teams, behaviors, and subagents. The default teams include opinionated subagents for product stories, requirements, acceptance criteria, technical breakdowns, implementation, code review, and bug hunting.

### `burnplan assign`

Route a task through a team behavior:

```sh
burnplan assign \
  --team project-manager \
  --behavior implement \
  --task-file issue.md
```

BurnPlan resolves the behavior to a Skyhook route profile, refreshes `.skyhook`
if needed, and prints a route pack. Emit JSON for an orchestrator:

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

BurnPlan is review-first. Onboarding and optimization write proposal drafts; promotion copies reviewed drafts into human-owned project files.

Promote documentation:

```sh
burnplan promote docs
```

This writes proposal docs to `docs/`, including architecture, design, code map, testing, code health, agent operating model, and an initial ADR.

Promote agent definitions:

```sh
burnplan promote agents
```

This writes generic agent specs to `docs/agents/` and Claude-style subagent files to `.claude/agents/`.

Promote everything:

```sh
burnplan promote all
```

Promotion refuses to overwrite existing files unless `--force` is supplied.

## Model Provider

BurnPlan delegates repository mapping to Skyhook. Skyhook supports an OpenAI-compatible chat completions endpoint through the Python standard library.

Environment variables:

- `OPENAI_API_KEY` or `SKYHOOK_API_KEY`
- `OPENAI_BASE_URL` or `SKYHOOK_BASE_URL`
- `SKYHOOK_MODEL`

If no API key is available and provider is `auto`, Skyhook uses deterministic static mode so BurnPlan remains usable in local and CI environments.

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
  maxFiles: 5000
docs:
  extraGlobs:
    - "docs/**/*.md"
    - "adr/**/*.md"
    - "architecture/**/*.md"
    - "**/*ADR*.md"
    - "**/*C4*.md"
```

The current implementation uses a small YAML subset so neither project requires PyYAML.

## Quality Evidence

BurnPlan currently mines lightweight evidence from git history:

- hotspots from recent churn
- repeated file co-changes as coupling hints
- volatile top-level areas
- detected static-analysis configuration
- documentation weak points such as missing ADRs or architecture docs

It discovers static-analysis tools but does not execute them yet.

## Development

```sh
PYTHONPATH=../Skyhook python3 -m unittest discover -s tests -v
PYTHONPATH=../Skyhook python3 -m burnplan onboard --provider static --no-interview --dry-run
PYTHONPATH=../Skyhook python3 -m burnplan optimize --provider static --dry-run
PYTHONPATH=../Skyhook python3 -m burnplan assign --team project-manager --behavior implement --task "add retry handling"
PYTHONPATH=../Skyhook python3 -m burnplan onboard --provider static --no-interview
PYTHONPATH=../Skyhook python3 -m burnplan promote docs
```
