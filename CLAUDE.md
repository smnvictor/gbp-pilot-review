# CLAUDE.md — GBP-Review-Manager (backend)

## Project overview

Automated Google Business Review Saas Tools — **dépôt backend uniquement**.

Depuis mai 2026 le frontend a été migré vers le dépôt voisin
[`~/Projects/gbp-pilot-review-website/`](../gbp-pilot-review-website/) (Next.js 15
unifié marketing + SaaS). Ce dépôt ne contient plus que l'API FastAPI, les
workers Celery, le bot Telegram et les migrations Alembic.

See [North_Star.md](North_Star.md) for full business context and [roadmap.md](roadmap.md) for phased implementation plan.

---

## Core rules (always apply)

### 1. Architecture — see [.rules/implementation.md](.rules/implementation.md)

All implementation decisions (OOP structure, modularity, toolchain, coding standards) are documented there. Read it before writing any feature code.
Always make tests for new features.

### 2. README.md stays current

Every new feature or configurable parameter **must be reflected in [README.md](README.md) immediately** — before the PR/commit is considered done. This includes:
- New classes or modules added
- New config keys (`.env` or `config.yaml`)
- New feature flags
- New CLI commands or Telegram bot commands
- Behaviour changes affecting the user

### 3. setup.md stays current

[setup.md](setup.md) is the zero-to-running guide for the project. Update it alongside every feature that requires:
- A new API key or third-party account
- A new environment variable
- An installation step (OS package, DNS record, Docker volume, etc.)
- Any prerequisite that is not purely code (domain purchase, Resend domain verification, etc.)

Keep it **ordered for a fresh setup** (e.g. register accounts before configuring keys). Write at the level of someone who has never touched the project.

---

## Toolchain quick reference

| Tool | Purpose |
|---|---|
| `uv` | Package manager & venv |
| `ruff` | Lint + format (line-length 100) |
| `mypy --strict` | Type checking |
| `pytest` | Test runner (`--cov=src`) |
| `pre-commit` | All of the above as hooks |
| `structlog` | Structured logging (JSON prod / pretty dev) |
| `docker-compose` | 2 services: `pipeline` + `telegram` |

Run quality checks: `uv run ruff check . && uv run mypy src/ && uv run pytest`

---

## Secrets — never commit

All secrets live in `.env` (git-ignored). The canonical list is maintained in `.env.example` and documented in [setup.md](setup.md).


## Remote debugging (VPS)

To access the production environment, run `ssh vps`, then `cd ~/gbp-review-manager`.
