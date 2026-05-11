# setup.md — guide d'installation zéro à running

Ce document décrit, étape par étape et dans l'ordre, comment passer d'une machine vierge à un backend GBP-Review-Manager qui démarre en local. Suit les conventions du [CLAUDE.md](CLAUDE.md) — toute nouvelle feature qui ajoute un prérequis externe (compte SaaS, clé API, package OS) doit être ajoutée ici.

---

## 1. Prérequis système

Outils à installer avant tout :

| Outil | Version min | Pourquoi |
|---|---|---|
| Python | 3.12+ | Runtime backend |
| `uv` | 0.11+ | Gestionnaire de paquets et venv |
| Docker + Docker Compose | dernière | Postgres + Redis en local |
| Node.js | 20+ | Runtime frontend (Next.js) — dans le dépôt voisin `gbp-pilot-review-website/` |
| `pnpm` | 9+ | Gestionnaire de paquets frontend — idem |
| Git | n'importe quelle | clonage |

Installation `uv` (Linux/macOS) :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Installation `pnpm` (Linux/macOS) :

```bash
curl -fsSL https://get.pnpm.io/install.sh | sh -
```

---

## 2. Comptes externes à créer

À faire **avant** de remplir le `.env`. Certains comptes prennent du temps (vérification, validation Google).

### 2.1. Google Cloud Console — OAuth (Phase 3)

1. Crée un projet sur https://console.cloud.google.com.
2. Active l'API **Google Business Profile API** (anciennement My Business v4).
3. Dans **APIs & Services → Credentials**, crée un OAuth 2.0 Client ID type "Web application".
4. Redirect URI à enregistrer : `http://localhost:8000/api/v1/oauth/google/callback` (dev) + l'URL de prod plus tard.
5. ⚠️ **App review** : le scope `business.manage` requiert une validation Google qui prend **2 à 6 semaines**. À lancer dès la Phase 3 (PR 4) pour ne pas bloquer la mise en prod.
6. Note `client_id` et `client_secret` → `.env`.

### 2.2. Anthropic Claude (Phase 3, PR 7)

1. Crée un compte sur https://console.anthropic.com.
2. Génère une API key dans la section **API Keys**.
3. Ajoute ~5–10€ de crédit pour les tests de dev.
4. Note la clé → `CLAUDE_API_KEY`.

### 2.3. Lemon Squeezy (Phase 3, PR 12)

1. Crée un compte vendeur sur https://lemonsqueezy.com.
2. Crée un store et note son `store_id`.
3. Génère une API key dans **Settings → API**.
4. Configure le webhook signing secret (sera utilisé pour vérifier les webhooks entrants).
5. Notes : `LEMONSQUEEZY_API_KEY`, `LEMONSQUEEZY_WEBHOOK_SECRET`, `LEMONSQUEEZY_STORE_ID`.

### 2.4. Resend — emails transactionnels (Phase 3, PR 11)

1. Compte sur https://resend.com.
2. Vérifie ton domaine d'envoi (ajout d'enregistrements DNS DKIM/SPF — peut prendre quelques heures).
3. Crée une API key.
4. Notes : `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (doit être sur le domaine vérifié).

### 2.5. Telegram (optionnel, Phase 3, PR 11)

1. Parle à `@BotFather` sur Telegram → `/newbot`.
2. Note le token retourné → `TELEGRAM_BOT_TOKEN`.
3. Les utilisateurs renseigneront leur `chat_id` côté frontend.

### 2.6. Sentry (optionnel, Phase 2 / hardening)

1. Compte sur https://sentry.io.
2. Crée un projet Python.
3. Note le DSN → `SENTRY_DSN`.

---

## 3. Cloner et installer le backend

```bash
git clone <repo-url> gbp-review-manager
cd gbp-review-manager
uv sync                # crée backend/.venv et installe toutes les deps depuis backend/pyproject.toml
```

`uv sync` détecte automatiquement le `pyproject.toml` situé dans `backend/`.

---

## 4. Configurer le `.env` backend

```bash
cp .env.example backend/.env
```

Ouvre `backend/.env` et remplis chaque clé :

### 4.1. Génère la clé de chiffrement Fernet (obligatoire)

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Colle la sortie dans `OAUTH_TOKEN_ENCRYPTION_KEY=`.

⚠️ **Ne jamais perdre cette clé** — toutes les credentials OAuth Google sont chiffrées avec. La rotation se fait via une seconde clé `OAUTH_TOKEN_ENCRYPTION_KEY_OLD` (à wirer si besoin).

### 4.2. Génère deux secrets aléatoires

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"   # → SECRET_KEY
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"   # → JWT_SECRET
```

### 4.3. Liste exhaustive des variables

Toutes les clés sont documentées dans [.env.example](.env.example). Récap :

| Variable | Obligatoire | Source |
|---|---|---|
| `ENVIRONMENT` | non (`development`) | — |
| `DEBUG` | non (`false`) | — |
| `LOG_LEVEL` | non (`INFO`) | — |
| `SECRET_KEY` | oui | random |
| `FRONTEND_URL` | oui | `http://localhost:3000` en dev |
| `DATABASE_URL` | oui | postgres dsn (avec `+asyncpg`) |
| `REDIS_URL` | oui | redis dsn |
| `OAUTH_TOKEN_ENCRYPTION_KEY` | oui | Fernet (cf. 4.1) |
| `JWT_SECRET` | oui | random |
| `JWT_ACCESS_TTL_MINUTES` | non (`60`) | — |
| `JWT_REFRESH_TTL_DAYS` | non (`30`) | — |
| `GOOGLE_OAUTH_CLIENT_ID` | oui | Google Cloud Console (§2.1) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | oui | Google Cloud Console |
| `GOOGLE_OAUTH_REDIRECT_URI` | oui | doit matcher Google Cloud Console |
| `CLAUDE_API_KEY` | oui (Phase 3 PR 7+) | Anthropic Console |
| `CLAUDE_MODEL` | non (`claude-sonnet-4-6`) | — |
| `LEMONSQUEEZY_API_KEY` | oui (PR 12+) | Lemon Squeezy dashboard |
| `LEMONSQUEEZY_WEBHOOK_SECRET` | oui (PR 12+) | Lemon Squeezy dashboard |
| `LEMONSQUEEZY_STORE_ID` | oui (PR 12+) | Lemon Squeezy dashboard |
| `RESEND_API_KEY` | oui (PR 11+) | Resend dashboard |
| `RESEND_FROM_EMAIL` | oui (PR 11+) | doit être sur domaine vérifié Resend |
| `TELEGRAM_BOT_TOKEN` | non | BotFather |
| `SENTRY_DSN` | non | Sentry project |

Pour les phases en cours de dev où tu n'as pas encore créé tel ou tel compte, il suffit de mettre une valeur **bidon non vide** (ex. `dev-claude-key`) — le backend démarre, et seules les routes qui appellent l'API correspondante échoueront.

---

## 5. Démarrer Postgres + Redis

```bash
docker compose up -d
```

Vérifications :

```bash
docker compose ps                              # postgres + redis "healthy"
docker compose exec postgres psql -U app -d gbp_review_manager -c '\dt'   # liste tables (vide avant migration)
```

Si tu n'as pas Docker, installe Postgres 16 + Redis 7 via ton gestionnaire de paquets et adapte `DATABASE_URL` / `REDIS_URL`.

---

## 6. Appliquer les migrations Alembic

Depuis `backend/` :

```bash
cd backend
uv run alembic upgrade head
```

Cela crée les **16 tables** + **14 enums Postgres** + l'extension `citext` (cf. PR 2 et `backend/alembic/versions/0001_initial.py`).

Vérifier :

```bash
uv run alembic current             # → 0001 (head)
uv run alembic history              # liste des révisions
```

Pour rollback complet :

```bash
uv run alembic downgrade base
```

---

## 7. Lancer l'API

Toujours depuis `backend/` :

```bash
uv run uvicorn app.main:app --reload
```

Endpoints disponibles (Phase 3 complète, PR 1 → 15) :

**Meta**
- `GET  /healthz` — liveness
- `GET  /readyz` — DB ping

**Auth & profil**
- `POST /api/v1/auth/{signup,login,logout,refresh,verify-email}`
- `POST /api/v1/auth/password-reset/{request,confirm}`
- `GET  /api/v1/me` · `DELETE /api/v1/me` (soft delete RGPD)

**OAuth Google**
- `GET  /api/v1/oauth/google/{authorize,callback}`

**Reviews & responses**
- `GET  /api/v1/reviews?status=…` · `GET /api/v1/reviews/pending` · `GET /api/v1/reviews/{id}`
- `GET  /api/v1/responses/{id}`
- `POST /api/v1/responses/{id}/{approve,cancel,regenerate}`
- `PATCH /api/v1/responses/{id}` (édition manuelle)

**Settings & subscription**
- `GET  /api/v1/settings` · `PATCH /api/v1/settings`
- `GET  /api/v1/subscription` · `POST /api/v1/subscription/checkout`

**Webhooks**
- `POST /api/v1/webhooks/lemonsqueezy` (HMAC-SHA256 vérifié)

**Admin** (rôle `admin` requis)
- `GET  /api/v1/admin/validation-queue`
- `GET  /api/v1/admin/clients` · `POST /api/v1/admin/clients/{id}/{suspend,reactivate}`
- `POST /api/v1/admin/deletions/{users,clients}/{id}`
- `GET  /api/v1/admin/monitoring/dlq` · `POST /api/v1/admin/monitoring/dlq/{id}/replay`
- `GET  /api/v1/admin/monitoring/circuits`

Doc OpenAPI auto-générée : http://localhost:8000/docs.

Test rapide :

```bash
curl -sX POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"a@b.com","password":"longpassword","business_name":"Resto Test"}'
```

---

## 8. Frontend (dépôt séparé)

Depuis mai 2026 le frontend vit dans le dépôt voisin
[`~/Projects/gbp-pilot-review-website/`](../gbp-pilot-review-website/) (Next.js 15
unifié marketing + SaaS). Voir son propre [`README.md`](../gbp-pilot-review-website/README.md)
pour l'installation pas-à-pas.

Résumé :

```bash
cd ~/Projects/gbp-pilot-review-website
pnpm install
cp .env.example .env.local
# éditer .env.local :
#   NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
#   AUTH_SECRET=$(openssl rand -base64 32)
#   NEXT_PUBLIC_FORMSPREE_ENDPOINT=https://formspree.io/f/YOUR_FORM_ID
pnpm dev                       # http://localhost:3000
```

⚠️ Côté backend, vérifier que `FRONTEND_URL=http://localhost:3000` dans `backend/.env`
(CORS strict).

Quality gates frontend (dans le dépôt frontend) :

```bash
pnpm lint
pnpm typecheck
pnpm test                      # Vitest
pnpm build                     # vérifie la prod build
```

---

## 9. Lancer les workers Celery

Deux processus séparés (chacun dans son terminal, ou via tmux/foreman) :

```bash
# Worker — consomme polling, generation, publication, notification
uv run celery -A app.celery_app worker -Q polling,generation,publication,notification,default --concurrency 4

# Beat — déclenche les jobs périodiques
uv run celery -A app.celery_app beat
```

Les jobs périodiques configurés (cf. `backend/app/celery_app.py`) :

| Job | Cadence | Module |
|---|---|---|
| `dispatch-pollings` | 15 min | PR 5 |
| `dispatch-publications` | 1 min | PR 8 |
| `refresh-oauth` | 30 min | PR 4 |
| `send-digests` | 15 min | PR 11 |
| `quota-thresholds` | quotidien 09:00 UTC | PR 12 |
| `purge-expired` | quotidien 03:15 UTC | PR 12 |

---

## 10. Quality gates

Avant chaque commit (cf. CLAUDE.md) :

```bash
# Backend
cd backend
uv run ruff check .       # lint
uv run mypy app           # type check strict
uv run pytest             # tests + couverture

# Frontend (dépôt voisin)
cd ~/Projects/gbp-pilot-review-website
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

---

## 11. Troubleshooting

| Symptôme | Cause probable | Fix |
|---|---|---|
| `ValidationError: secret_key Field required` au démarrage | `.env` non chargé ou clé manquante | vérifier `backend/.env`, valeurs non vides |
| `Could not decrypt value (invalid Fernet token)` | `OAUTH_TOKEN_ENCRYPTION_KEY` changée après génération de credentials | restaurer la clé d'origine ou ré-effectuer le flow OAuth |
| `connection refused` Postgres | container down ou port collision | `docker compose ps`, `docker compose up -d` |
| `ModuleNotFoundError: app` lors de `uv run alembic …` | exécuté hors du dossier `backend/` | `cd backend` puis relancer |
| Tests échouent sur `CITEXT` | extension Postgres manquante | la migration `0001_initial` la crée automatiquement |
| Frontend : `Missing required env var: NEXT_PUBLIC_BACKEND_URL` | `gbp-pilot-review-website/.env.local` absent ou variable vide | copier `.env.example` vers `.env.local` puis remplir |
| Frontend : 401 sur toutes les requêtes API | mauvais `NEXT_PUBLIC_BACKEND_URL` ou backend `FRONTEND_URL` ≠ origin frontend (CORS) | aligner les deux URL |

---

## 12. Pour aller plus loin

- Architecture détaillée : [docs/02-backend.md](docs/02-backend.md)
- Schéma de données complet : [docs/01-database.md](docs/01-database.md)
- Flows critiques (OAuth, polling, génération, publication) : [docs/04-flows.md](docs/04-flows.md)
- Prompt Claude v1.0.0 : [docs/05-prompts.md](docs/05-prompts.md)
- Roadmap par phases : [Roadmap.md](Roadmap.md)
