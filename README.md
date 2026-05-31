# gbp-pilot-review

## Description

Google Business Profile Review Manager that allows Business to reply automatically to reviews.

## Démarrage rapide

> **Note (mai 2026)** : Le frontend a été extrait dans le dépôt voisin
> [`~/Projects/gbp-pilot-review-website/`](../gbp-pilot-review-website/) (Next.js 15
> unifié marketing + SaaS). Ce dépôt ne contient plus que l'API FastAPI, les workers
> Celery, le bot Telegram et les migrations.

Voir le guide pas-à-pas dans **[setup.md](./setup.md)** (comptes externes, env vars, migrations, lancement).

Résumé express (depuis la racine du repo) :

```bash
# Backend
uv sync                                          # install deps
cp .env.example backend/.env                     # puis remplir les clés (cf. setup.md)
docker compose up -d                             # postgres + redis
cd backend && uv run alembic upgrade head        # créer les 16 tables
uv run uvicorn app.main:app --reload             # API sur :8000

# Frontend (autre dépôt, autre terminal)
cd ~/Projects/gbp-pilot-review-website
pnpm install
cp .env.example .env.local                       # remplir AUTH_SECRET (openssl rand -base64 32)
pnpm dev                                         # http://localhost:3000
```

## Modules backend implémentés

Phase 3 (backend core) **complète** — 15 PRs livrés :

- **PR 1 — Bootstrap** : FastAPI app factory, Pydantic Settings, Loguru JSON + correlation_id, Celery (5 queues + 6 jobs beat), Alembic, healthchecks `/healthz` et `/readyz`.
- **PR 2 — Modèles + migrations** : 16 tables SQLAlchemy 2.0 (`users`, `clients`, `subscriptions`, `quota_usage`, `oauth_credentials`, `locations`, `reviews`, `responses`, `regenerations`, `client_settings`, `notification_preferences`, `notifications`, `prompt_versions`, `audit_logs`, `dead_letter_jobs`, `webhook_events`), 14 enums Postgres, `EncryptedString` TypeDecorator basé sur Fernet, migration `0001_initial.py`.
- **PR 3 — Auth** : JWT HS256 access (60min) + refresh cookie HttpOnly (30j), argon2id, repository pattern générique, endpoints `/auth/{signup,login,logout,refresh,verify-email,password-reset/{request,confirm}}` et `/me`.
- **PR 4 — OAuth Google Business Profile** : Protocol `GoogleBusinessAdapter` + impl httpx, exceptions typées (Auth/RateLimit/5xx/Network), service OAuth (start/exchange/refresh/revoke + sync locations), routes `/oauth/google/{authorize,callback,status}` (`status` renvoie l'état de connexion + locations liées pour le dashboard client), beat task `refresh_expiring_tokens` (30 min, expire <60min).
- **PR 5 — Polling** : `PollingService.poll_client` (dedup par `google_review_id`), Celery `dispatch_pollings` (beat 15 min) + `poll_client_reviews` (queue=polling, retry 3x backoff 1800s) + `process_review_task`.
- **PR 6 — Filtering** : matrice exhaustive (note 1-3, langue ≠ fr/en, regex blocklist, no-text policy `ignore`/`reply_4_5_only`/`reply_all`) + bypass IA `template_no_text_v1` (sans appel Claude, sans quota consommé).
- **PR 7 — Generation Claude** : Protocol `LLMProvider` + impl Anthropic SDK avec **prompt caching** (cache_control ephemeral) et tool-use schema strict, 13 codes `details` validés via `Literal`, modèle `claude-sonnet-4-6`, routage post-génération (status=0 → team review, status=1 → suggestion/team selon `validation_mode`).
- **PR 8 — Publication + Undo** : `compute_publish_at` (jitter dans range, clamp à publish_window, conversion timezone), `schedule_publication` (set `undo_deadline_at = now + 10min`), garde-fou pré-publication (lock `SELECT FOR UPDATE SKIP LOCKED`), rollback `scheduled` sur 401, endpoints `/responses/{id}/{approve,cancel,regenerate}` + PATCH édition manuelle.
- **PR 9 — Reviews + Settings API** : `GET /reviews?status=`, `/reviews/pending`, `/reviews/{id}` ; `GET /settings` + `PATCH /settings` (inclut la personnalisation IA portée par `clients` : `tone` list[str], `business_context`, `always_mention`, `never_mention` — migration `0003`, injectés dans le prompt Claude) ; admin `/validation-queue` pour `validation_mode='team'`.
- **PR 10 — Reliability** : décorateur `@with_retry` (exponential backoff + jitter), 5 circuit breakers `pybreaker` (Google 5/60s, Claude 3/120s, Resend/Telegram/Lemon 5/60s), Celery `task_failure` signal → DLQ persistée, admin `/monitoring/{dlq, dlq/{id}/replay, circuits}`.
- **PR 11 — Notifications** : adapters Resend + Telegram, `NotificationService.dispatch` avec mode immediate vs digest (events critiques `oauth_revoked`/`publish_failed`/`quota_exhausted` toujours immediate), beat task `send_pending_digests` (15 min), 18 templates email/text indexés par `event_type`.
- **PR 12 — Subscription + Quota + Lemon Squeezy** : webhooks HMAC-SHA256, idempotence via `webhook_events.event_id` UNIQUE, handlers `subscription_created/updated/cancelled/payment_failed/payment_success`, `QuotaService.consume_or_raise` atomique, beat tasks `check_quota_thresholds` (09:00 UTC, alerte 80%/100%) + `purge_expired_data` (03:15 UTC, RGPD). `POST /subscription/checkout` prend un `tier` (`starter`/`pro`/`business`) résolu en variant Lemon Squeezy via `LEMONSQUEEZY_VARIANT_{STARTER,PRO,BUSINESS}` (503 si non configuré, au lieu d'un 502 opaque) ; `GET /subscription` expose `quota_used` pour l'affichage de la consommation.
- **PR 13 — Admin + audit + RGPD** : helper `audit()`, `/admin/clients/{id}/{suspend,reactivate}`, `/admin/deletions/{users,clients}/{id}`.
- **Phase 5 — Dashboard admin (backend)** : migration `0002` (colonne `clients.admin_notes`), schémas `app/schemas/admin.py`, service `app/services/admin_metrics.py`. Endpoints supplémentaires :
  - `GET /admin/clients` enrichi (`search`, `status`, `offset`) ; `GET /admin/clients/{id}` détail ; `PATCH /admin/clients/{id}/notes` ; `GET /admin/clients/{id}/metrics`.
  - `GET /admin/validation-queue` avec `client_id`, `order=oldest|newest`, `offset`, items enrichis (rating + auteur + nom du client).
  - `GET /admin/monitoring/metrics` (système) et `GET /admin/monitoring/oauth-alerts` (`expiring|expired|revoked`).
  - `POST /admin/deletions/responses/{id}` (appel Google `delete_reply` + soft delete + audit) ; `GET /admin/deletions/responses` (historique).
  - Garde `owner_or_admin` ajoutée sur `/responses/*` pour autoriser l'admin sur les actions rapides.
- **PR 14 — Tests** : 27 tests unitaires (auth/JWT, encryption Fernet, retry decorator, time.compute_publish_at, signature Lemon Squeezy, templates notifs, OAuth authorize URL, prompt rendering, filtering matrix).
- **PR 15 — Hardening** : slowapi rate limiting, Sentry SDK conditionnel (FastAPI + Starlette integrations), CORS strict sur `frontend_url`.
- **Phase 6 — Tests** : extension du harnais avec fixtures DB transactionnelles (`db_session`), client FastAPI overridé (`client`), factories synchrones (`tests/factories/`), mocks Claude + Google + Lemon Squeezy. Nouveaux suites :
  - **Unit** (`tests/unit/`) — services `generation`, `polling`, `publication`, `quota`, `oauth`, `subscription`, `dlq` + repositories transverses + utilitaires `circuit`, `language`.
  - **Integration** (`tests/integration/`) — pipeline polling → filtering → génération → publication, webhook Lemon Squeezy (signature + idempotence), OAuth authorize/callback, retries + circuit breaker, garde admin sur `/responses/*`.
  - **E2E** (`tests/e2e/`) — parcours signup → login → /me → OAuth, validation d'une réponse (approve + cancel), configuration des paramètres.
  - **Load** (`tests/load/`) — `locustfile.py` (HTTP) + `simulate_pipeline.py` (20 clients × 5 reviews, mesure latences par étape).

Quality gates : `uv run ruff check .` ✓, `uv run mypy app` ✓, `uv run pytest` ✓.

### Commandes de test

```bash
# Unit only (rapide, sans Postgres)
uv run pytest tests/unit -m "not integration"

# Suite complète (requiert Postgres + Redis)
docker compose up -d postgres redis
uv run pytest

# Sélectivement
uv run pytest -m integration   # tests d'intégration uniquement
uv run pytest -m e2e           # parcours end-to-end
uv run pytest --cov=app --cov-report=html  # rapport couverture

# Charge légère (Locust HTTP)
uv tool install locust
uv run locust -f tests/load/locustfile.py --headless -u 20 -r 2 -t 2m \
    --host http://localhost:8000

# Charge légère (pipeline in-process avec mocks Google + Claude)
uv run python tests/load/simulate_pipeline.py --clients 20 --reviews 5
```

## Frontend

Le frontend a été extrait (mai 2026) vers le dépôt voisin
[`~/Projects/gbp-pilot-review-website/`](../gbp-pilot-review-website/) :

- **Stack** : Next.js 15 App Router · React 19 · TypeScript strict · Tailwind v3 · shadcn/ui · NextAuth v5 · TanStack Query v5 · React Hook Form + Zod · Vitest.
- **Périmètre** : site marketing public (Home, Features, Pricing, About, Contact, Privacy, Terms, Mentions légales, DPA) + SaaS authentifié (auth, onboarding, dashboard, reviews, pending, settings, billing) + **espace admin** (`/admin`, `/admin/clients`, `/admin/clients/[id]`, `/admin/validation`, `/admin/monitoring`, `/admin/deletions`) réservé au rôle `admin` via middleware + garde server-side dans `app/admin/layout.tsx`.
- **Charte graphique** : Fraunces (titres) + Inter (corps), palette marine `#0B1E3F`. Référence visuelle : [`BRIEF.md`](../gbp-pilot-review-website/BRIEF.md).
- **i18n** : FR uniquement au lancement (la structure next-intl a été retirée pour simplifier).
- **Build** : 23 pages compilent, 14 tests Vitest passent.

**Gaps backend connus (à résoudre pour finalisation MVP)** :
1. Affichage de la réponse active dans `/reviews/[id]` nécessite un endpoint `GET /reviews/{id}/responses` ou un champ `active_response_id` dans `ReviewPublic` — composants prêts (`ResponseEditor`, `ResponseActions`, `UndoBanner`), à câbler dès qu'exposé.
2. Customisation IA fine (tone, signature, must-mention) hors-scope — nécessite extension de `ClientSettingsUpdate` ou endpoint dédié `prompt_profile`.
3. Endpoint `/api/v1/metrics` non disponible ; métriques dashboard calculées côté front à partir de la liste des avis.
4. Notifications in-app reportées Phase 5 (pas d'endpoint « liste notifications utilisateur »).
5. La page `/features` utilise des visuels simplifiés (placeholder) sur les FeatureBlock — les visuels riches du design Astro original (radar, file d'attente animée, etc.) sont à reporter depuis [`_astro-source/src/pages/features.astro`](../gbp-pilot-review-website/_astro-source/src/pages/features.astro).

## Documentation

Vision produit et roadmap :

- [North-Star.md](./North-Star.md) — vision, modèle économique, périmètre MVP
- [Roadmap.md](./Roadmap.md) — plan de développement par phases
- [setup.md](./setup.md) — guide d'installation zéro-à-running

Conception technique (Phase 1) :

- [docs/01-database.md](./docs/01-database.md) — modèle de données, SQLAlchemy 2.0, indexation
- [docs/02-backend.md](./docs/02-backend.md) — architecture FastAPI / Celery / structure Python
- [docs/03-frontend.md](./docs/03-frontend.md) — routes Next.js, composants, auth, i18n
- [docs/04-flows.md](./docs/04-flows.md) — OAuth Google, pipeline polling→publication, notifications, erreurs
- [docs/05-prompts.md](./docs/05-prompts.md) — prompt système Claude, nomenclature `details`, versioning
- [docs/06-security.md](./docs/06-security.md) — modèle de menace, contrôles, conformité RGPD, registre des traitements

## License

This project is licensed under the PolyForm Noncommercial License 1.0.0.
You may view, modify, and use this code for non-commercial purposes only.
See the [LICENSE](./LICENSE.md) file for details.
