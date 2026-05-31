# setupProd.md — guide de mise en production GBP-Pilot-Review

Document de référence pour mettre en ligne le SaaS sur `https://pilot-review.com` (vitrine + app Next.js) et `https://api.pilot-review.com` (backend FastAPI + Celery + Telegram bot).

Il est ordonné : suis les phases A → H dans l'ordre. Chaque phase liste les actions concrètes et une section *Vérification* avant de passer à la suivante.

Compagnon de [setup.md](setup.md) (qui couvre le run local).

---

## Décisions d'architecture (validées)

| Sujet | Choix |
|---|---|
| Sous-domaine API | `api.pilot-review.com` |
| Hébergement front | Cloudflare Pages via `@opennextjs/cloudflare` |
| Hébergement back | VPS Oracle Free Tier ARM, Docker Compose + Caddy |
| TLS backend | Cloudflare Origin Certificate (15 ans), Cloudflare proxy ON |
| Environnement | **Prod uniquement** au lancement (staging plus tard) |
| Auth front | NextAuth v5 (JWT, Credentials → backend) |
| CI/CD | GitHub Actions (back : lint+tests+deploy SSH ; front : lint+tests, deploy Cloudflare via Git integration) |

---

## Legende de la TodoList :

- [x] Fait
- [~] En cours
- [ ] À faire

## Phase A — Prérequis externes & DNS : DONE [x]

### A.1 Comptes externes (créés en Phase 0, à vérifier)
- [x] Cloudflare (gestion DNS de `pilot-review.com`)
- [x] Oracle Cloud (VPS Free Tier ARM Ampere, 4 vCPU, 24 Go RAM)
- [x] GitHub (les deux repos)
- [~] Google Cloud Console (OAuth client en mode *Production* — voir Phase C.4)
- [~] Lemon Squeezy (store + API key)
- [x] Resend (domaine `pilot-review.com` vérifié SPF/DKIM/DMARC)
- [~] Sentry (deux projets : `gbp-pilot-review-backend`, `gbp-pilot-review-website`)
- [~] UptimeRobot
- [~] Cloudflare R2 (bucket `gbp-pilot-review-backups`)
- [ ] Anthropic API (Claude key)
- [ ] Telegram (bot token via @BotFather)

### A.2 DNS sur Cloudflare (zone `pilot-review.com`)
Crée les enregistrements suivants :

| Type | Nom | Cible | Proxy |
|---|---|---|---|
| CNAME | `@` (apex) | `gbp-pilot-review-website.pages.dev` (sera complété Phase D) | ON 🟧 |
| CNAME | `www` | `gbp-pilot-review-website.pages.dev` | ON 🟧 |
| A | `api` | `<IP publique du VPS Oracle>` | **ON 🟧** |

Note : grâce au Cloudflare Origin Certificate (étape A.3), on peut garder le proxy ON sur `api.` — pas besoin de désactiver pour Let's Encrypt.

### A.3 Cloudflare Origin Certificate
1. Cloudflare → SSL/TLS → Origin Server → *Create Certificate*
2. Hostnames : `*.pilot-review.com`, `pilot-review.com`
3. Validity : **15 ans**
4. Télécharge `origin.pem` (cert) et `origin.key` (clé privée). À déposer Phase C.3 dans `/etc/caddy/` du VPS.
5. Cloudflare → SSL/TLS → *Overview* → mode **Full (strict)**

### A.4 Ouverture des ports sur le VPS
Sur Oracle Cloud → Security List de la VCN du VPS :
- TCP 80 (0.0.0.0/0)
- TCP 443 (0.0.0.0/0)
- TCP 22 (restreindre à ton IP perso si possible)

Sur le VPS (`ssh vps`) :
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
sudo ufw status
```

### A.5 Coffre des secrets
Prépare un coffre (1Password / Bitwarden) avec **tous** les secrets à renseigner Phase C, en t'appuyant sur `backend/.env.example`. Génère localement :
```bash
# Secrets backend
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print('OAUTH_TOKEN_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# Secret NextAuth (frontend)
openssl rand -base64 32   # → AUTH_SECRET
```

### Vérification Phase A
```bash
dig api.pilot-review.com +short      # → IP Cloudflare (proxy)
dig pilot-review.com +short          # → IP Cloudflare
curl -I https://api.pilot-review.com # → 521/522 (origin pas encore prête, c'est normal)
```

---

## Phase B — Hardening backend (artefacts en local) : [ ]

Tu travailles dans `/home/victor/Projects/gbp-pilot-review/`.

### B.1 `backend/Dockerfile`
Multi-stage Python 3.12 slim ARM64, `uv sync --frozen`, user non-root, `HEALTHCHECK` sur `/health`. Image identique pour API et workers (le service overridé via `command:`).

### B.2 `docker-compose.prod.yml` (racine du repo)
Services :
- `api` : uvicorn → expose 8000 sur réseau interne uniquement
- `worker-default`, `worker-polling`, `worker-publication`, `worker-notifications`, `worker-high_priority` : celery worker -Q <queue>
- `beat` : celery beat
- `telegram-bot`
- `postgres` (Postgres 16, volume `pgdata`)
- `redis` (volume `redisdata`, AOF activé)
- `caddy` : seul service à exposer 80/443 publiquement

Réseau Docker `internal` ; seul `caddy` est sur le bridge.

### B.3 `Caddyfile` (racine du repo)
```caddy
api.pilot-review.com {
    tls /etc/caddy/origin.pem /etc/caddy/origin.key
    encode gzip zstd
    header {
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
    reverse_proxy api:8000
}
```

### B.4 `.env.prod.example`
Copie de `backend/.env.example` avec sentinelles `__SET_ME__` et ces overrides :
```env
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
FRONTEND_URL=https://pilot-review.com
CORS_ORIGINS=https://pilot-review.com,https://www.pilot-review.com
GOOGLE_OAUTH_REDIRECT_URI=https://api.pilot-review.com/api/v1/oauth/google/callback
```

### B.5 `scripts/deploy.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml build --pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec -T api uv run alembic upgrade head
docker compose -f docker-compose.prod.yml ps
```

### B.6 `scripts/backup.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
TS=$(date -u +%Y%m%dT%H%M%SZ)
docker compose -f /home/ubuntu/gbp-pilot-review/docker-compose.prod.yml \
  exec -T postgres pg_dump -U postgres gbp_pilot_review \
  | gzip > /tmp/db-${TS}.sql.gz
rclone copy /tmp/db-${TS}.sql.gz r2:gbp-pilot-review-backups/
rm /tmp/db-${TS}.sql.gz
```

### B.7 Quality gates locaux
```bash
cd backend
uv run ruff check . --fix
uv run mypy app
uv run pytest -m "not load"
```

### B.8 Commit + push
```bash
git add backend/Dockerfile docker-compose.prod.yml Caddyfile .env.prod.example scripts/ setupProd.md
git commit -m "infra: production docker compose, Caddy, deploy scripts"
git push origin main
```

### Vérification Phase B
```bash
docker compose -f docker-compose.prod.yml config > /dev/null && echo OK
docker buildx build --platform linux/arm64 -f backend/Dockerfile backend/  # build cross-platform OK
```

---

## Phase C — Déploiement backend sur VPS

Tout se passe via `ssh vps`.

### C.1 Pull et structure
```bash
ssh vps
cd ~/gbp-pilot-review
git pull --ff-only
mkdir -p ~/gbp-pilot-review/caddy-data ~/gbp-pilot-review/caddy-config
```

### C.2 Déposer le certificat Cloudflare Origin
```bash
sudo mkdir -p /etc/caddy
sudo nano /etc/caddy/origin.pem    # coller le contenu de origin.pem
sudo nano /etc/caddy/origin.key    # coller la clé privée
sudo chmod 600 /etc/caddy/origin.key
```
Adapter `docker-compose.prod.yml` pour monter `/etc/caddy:/etc/caddy:ro` dans le service `caddy`.

### C.3 Créer `.env` de production
```bash
cp .env.prod.example .env
nano .env   # remplir tous les __SET_ME__ depuis ton coffre
chmod 600 .env
```
Liste de contrôle des secrets à renseigner :
- DB : `DATABASE_URL=postgresql+asyncpg://postgres:<password>@postgres:5432/gbp_pilot_review`, `REDIS_URL=redis://redis:6379/0`
- Crypto : `JWT_SECRET`, `SECRET_KEY`, `OAUTH_TOKEN_ENCRYPTION_KEY`
- Google OAuth : `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (client prod, voir C.4)
- LLM : `CLAUDE_API_KEY`, `CLAUDE_MODEL=claude-sonnet-4-6`
- Billing : `LEMONSQUEEZY_API_KEY`, `LEMONSQUEEZY_WEBHOOK_SECRET`, `LEMONSQUEEZY_STORE_ID`
- Notifications : `RESEND_API_KEY`, `RESEND_FROM_EMAIL=notifications@pilot-review.com`, `TELEGRAM_BOT_TOKEN`
- Observabilité : `SENTRY_DSN`

### C.4 Mettre à jour les dashboards externes
1. **Google Cloud Console** → OAuth client (le tien) → *Authorized redirect URIs* → ajouter `https://api.pilot-review.com/api/v1/oauth/google/callback`. Publier l'app (sortir du mode *Testing*) en utilisant le futur site vitrine comme preuve de présence.
2. **Lemon Squeezy** → Settings → Webhooks → URL = `https://api.pilot-review.com/api/v1/webhooks/lemonsqueezy`, signing secret → copier dans `.env` comme `LEMONSQUEEZY_WEBHOOK_SECRET`.
3. **Resend** → Vérifier domaine `pilot-review.com` (records SPF/DKIM/DMARC ajoutés en Phase A).

### C.5 Premier déploiement
```bash
bash scripts/deploy.sh
docker compose -f docker-compose.prod.yml ps           # tous les services Up
docker compose -f docker-compose.prod.yml logs --tail=100 api beat worker-polling
```

### C.6 Persistance via systemd
Crée `/etc/systemd/system/gbp-pilot-review.service` :
```ini
[Unit]
Description=GBP Pilot Review (docker compose)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/gbp-pilot-review
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gbp-pilot-review.service
```

### C.7 Timer de backup quotidien
`/etc/systemd/system/gbp-pilot-review-backup.service` :
```ini
[Unit]
Description=Daily Postgres backup
[Service]
Type=oneshot
ExecStart=/bin/bash /home/ubuntu/gbp-pilot-review/scripts/backup.sh
```
`/etc/systemd/system/gbp-pilot-review-backup.timer` :
```ini
[Unit]
Description=Daily backup at 03:00 UTC
[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
[Install]
WantedBy=timers.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gbp-pilot-review-backup.timer
systemctl list-timers | grep gbp
```

### C.8 Log rotation Docker
`/etc/docker/daemon.json` :
```json
{ "log-driver": "json-file", "log-opts": { "max-size": "50m", "max-file": "5" } }
```
```bash
sudo systemctl restart docker
sudo systemctl restart gbp-pilot-review.service
```

### Vérification Phase C
```bash
# Depuis n'importe où
curl https://api.pilot-review.com/health                  # → 200 {"status":"ok"}
curl https://api.pilot-review.com/api/v1/openapi.json     # → JSON OpenAPI

# Depuis le VPS
docker compose -f docker-compose.prod.yml logs --tail=200 api worker-polling beat telegram-bot
# → aucune erreur, beat dispatch les 6 tâches, workers reçoivent

# Sentry test event
docker compose -f docker-compose.prod.yml exec api python -c "import sentry_sdk; sentry_sdk.capture_message('prod boot test')"
# → vérifier réception dans le projet Sentry backend
```

---

## Phase D — Déploiement frontend Cloudflare Pages

Tu travailles dans `/home/victor/Projects/gbp-pilot-review-website/`.

### D.1 Nettoyer les vestiges Astro
```bash
cd /home/victor/Projects/gbp-pilot-review-website
rm -rf _astro-source dist
```

### D.2 Installer l'adapter Cloudflare pour Next.js
```bash
pnpm add -D @opennextjs/cloudflare wrangler
```

### D.3 Réécrire `wrangler.jsonc`
```jsonc
{
  "name": "gbp-pilot-review-website",
  "compatibility_date": "2026-04-25",
  "compatibility_flags": ["nodejs_compat"],
  "main": ".open-next/worker.js",
  "assets": {
    "directory": ".open-next/assets",
    "binding": "ASSETS"
  },
  "observability": { "enabled": true }
}
```

### D.4 Créer `open-next.config.ts`
```ts
import { defineCloudflareConfig } from "@opennextjs/cloudflare";
export default defineCloudflareConfig();
```

### D.5 Scripts `package.json`
Ajouter :
```json
"build:cf": "next build && opennextjs-cloudflare build",
"deploy:cf": "wrangler deploy"
```

### D.6 Mise à jour du CLAUDE.md du repo website
Le fichier référence encore Astro. Remplace par : Next.js 15 App Router, pnpm, déploiement Cloudflare via `@opennextjs/cloudflare`.

### D.7 Cloudflare Pages dashboard
1. Cloudflare → Workers & Pages → *Create* → Pages → *Connect to Git*
2. Sélectionner le repo `gbp-pilot-review-website`
3. Build settings :
   - Framework preset : *None*
   - Build command : `pnpm build:cf`
   - Build output directory : `.open-next`
   - Root directory : `/`
4. Environment variables (Production) :
   - `NEXT_PUBLIC_BACKEND_URL=https://api.pilot-review.com`
   - `AUTH_SECRET=<openssl rand base64 32>`
   - `AUTH_TRUST_HOST=true`
   - `NEXT_PUBLIC_FORMSPREE_ENDPOINT=https://formspree.io/f/<your-id>`
   - `NEXT_PUBLIC_SENTRY_DSN=<dsn-front>`
5. *Save and Deploy*. Attendre le premier déploiement.
6. *Custom domains* → ajouter `pilot-review.com` et `www.pilot-review.com`. Cloudflare met à jour automatiquement les CNAME créés en Phase A.2.

### D.8 Commit + push
```bash
cd /home/victor/Projects/gbp-pilot-review-website
git add -A
git commit -m "infra: Cloudflare Pages deployment via @opennextjs/cloudflare"
git push origin main
```

### Vérification Phase D
- `https://pilot-review.com` charge la home
- `https://www.pilot-review.com` redirige vers l'apex
- `/login`, `/signup` sont rendus
- DevTools Network : appels API préfixés par `https://api.pilot-review.com/api/v1`
- Lighthouse mobile > 90

---

## Phase E — Wire-up front ↔ back

### E.1 CORS backend
Le backend doit accepter les origines `https://pilot-review.com` et `https://www.pilot-review.com` (déjà posé via `CORS_ORIGINS` en Phase C.3). Vérifie dans `backend/app/main.py` que le middleware FastAPI lit cette variable.

### E.2 Test preflight
Depuis la console DevTools sur `https://pilot-review.com` :
```js
fetch('https://api.pilot-review.com/api/v1/auth/login', {
  method: 'OPTIONS',
  headers: { 'Content-Type': 'application/json', 'Origin': 'https://pilot-review.com' }
}).then(r => console.log(r.status, [...r.headers]))
```
→ 200 + headers `access-control-allow-origin: https://pilot-review.com`.

### E.3 Cookie NextAuth
NextAuth v5 en JWT pose un cookie `__Secure-authjs.session-token`. Vérifie qu'il est bien `Secure; HttpOnly; SameSite=Lax` (devtools → Application → Cookies).

### Vérification Phase E
- Signup via UI prod → 200, redirect login
- Login via UI prod → JWT stocké, redirect dashboard
- Appel `/api/v1/me` depuis le dashboard → 200 avec les infos user

---

## Phase F — Smoke tests feature par feature

### F.0 Front cleaning — actions de déploiement de la branche `feature/ui-overhaul`

À faire **avant** les smoke tests, une fois la branche mergée/déployée :

- [ ] **Variantes Lemon Squeezy** : créer/relever les 3 variant IDs (Starter/Pro/Business) dans le dashboard LS et renseigner `LEMONSQUEEZY_VARIANT_STARTER`, `LEMONSQUEEZY_VARIANT_PRO`, `LEMONSQUEEZY_VARIANT_BUSINESS` dans le `.env` de prod. Sans ça, `POST /api/v1/subscription/checkout` renvoie un **503** explicite (au lieu d'ouvrir le checkout).
- [ ] **Migration DB** : `docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head` → applique `0003` (colonnes `clients.tone`, `always_mention`, `never_mention`).
- [ ] **Fuseau Celery** : le polling est désormais fixé à **11h/14h/17h/20h Europe/Paris** (Celery `timezone="Europe/Paris"`). Effet de bord : les crons de maintenance (`check_quota_thresholds` 09:00, `purge_expired_data` 03:15) passent aussi en heure de Paris. Décider si on les re-fixe en UTC ; sinon, juste vérifier que `beat` planifie aux bons horaires.
- [ ] **Vérif post-deploy** : parcourir `CHECKLIST.md` (racine des deux repos).

Exécute dans l'ordre, avec un compte de test (`test+<n>@pilot-review.com`) puis répète avec `victor.simon760@gmail.com`. Coche chaque ligne avant de passer à la suivante.

| # | Test | Endpoint / Action | Critère de succès |
|---|---|---|---|
| 1 | **Signup** | `POST /api/v1/auth/signup` via `/signup` | User en DB, email Resend reçu |
| 2 | **Login** | `POST /api/v1/auth/login` via `/login` | JWT, redirect `/dashboard` |
| 3 | **OAuth Google connect** | `/dashboard/settings` → bouton Connect | Consent → callback → `oauth_tokens` chiffré en DB, locations listées |
| 4 | **Sélection location** | UI choix location | `client.location_id` mis à jour |
| 5 | **Polling manuel** | Bouton "Synchroniser" ou Celery task admin | Nouveaux avis insérés (`reviews`) |
| 6 | **Génération IA** | Bouton "Générer une réponse" | Draft `responses` créé, payload Claude OK |
| 7 | **Approbation** | Bouton "Approuver" | `responses.state = approved` |
| 8 | **Publication** | Worker `publication` après délai | API Google Business Profile retourne 200, `state = published` |
| 9 | **Notif Telegram** | Bot envoie message | Reçu sur le chat configuré |
| 10 | **Notif email** | Resend send | Email reçu (templates HTML OK) |
| 11 | **Billing checkout** | Lemon Squeezy → `/billing` → checkout | Webhook `subscription_created` reçu → ligne `subscriptions` créée, quota appliqué |
| 12 | **Admin dashboard** | `make_admin.py <email>` puis `/admin` | Stats, file de validation, monitoring accessibles |

Pour chaque test : capture (DevTools Network ou screenshot) + status. Reporter ici (annexe à compléter au fur et à mesure) :

```
[ ] 1. Signup        — date : ___ status : ___
[ ] 2. Login         — date : ___ status : ___
[ ] 3. OAuth Google  — date : ___ status : ___
[ ] 4. Location      — date : ___ status : ___
[ ] 5. Polling       — date : ___ status : ___
[ ] 6. Génération    — date : ___ status : ___
[ ] 7. Approbation   — date : ___ status : ___
[ ] 8. Publication   — date : ___ status : ___
[ ] 9. Telegram      — date : ___ status : ___
[ ] 10. Email        — date : ___ status : ___
[ ] 11. Billing      — date : ___ status : ___
[ ] 12. Admin        — date : ___ status : ___
```

---

## Phase G — CI/CD GitHub Actions

### G.1 Backend — `.github/workflows/backend-ci.yml`
Déclenche sur `pull_request` et `push` (paths : `backend/**`). Jobs :
- `lint` : `uv run ruff check .`
- `typecheck` : `uv run mypy app`
- `test` : `uv run pytest -m "not load" --cov=app` avec services `postgres:16` et `redis:7`

### G.2 Backend — `.github/workflows/backend-deploy.yml`
Déclenche sur `push` vers `main`. Step unique avec `appleboy/ssh-action@v1` :
```yaml
- uses: appleboy/ssh-action@v1
  with:
    host: ${{ secrets.VPS_HOST }}
    username: ${{ secrets.VPS_USER }}
    key: ${{ secrets.VPS_SSH_KEY }}
    script: bash ~/gbp-pilot-review/scripts/deploy.sh
```
Secrets GitHub à créer dans le repo backend : `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` (clé privée SSH dédiée déploiement).

### G.3 `.pre-commit-config.yaml` (racine backend)
Hooks : `ruff`, `ruff-format`, `mypy`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`.

### G.4 Frontend — `.github/workflows/frontend-ci.yml`
Déclenche sur `pull_request` et `push`. Jobs : `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build:cf`.

### G.5 Frontend deploy
**Pas de workflow custom** : la Git integration Cloudflare Pages (configurée Phase D.7) déclenche le build à chaque push sur `main`.

### Vérification Phase G
- Ouvrir une PR de test côté backend → CI verte
- Merger sur `main` → workflow `backend-deploy.yml` SSH le VPS → vérifier `docker compose ps` à jour et nouveau commit reflété dans logs
- Ouvrir une PR de test côté frontend → CI verte
- Merger sur `main` → Cloudflare Pages déploie la nouvelle version

---

## Phase H — Monitoring, backups, hardening

### H.1 Sentry
- Backend : `SENTRY_DSN` posé en Phase C.3, vérifier que les unhandled exceptions remontent (déclencher une erreur volontaire sur un endpoint test).
- Frontend : `NEXT_PUBLIC_SENTRY_DSN` posé en Phase D.7, vérifier qu'une erreur côté client est capturée.
- Release tracking : ajouter une step `sentry-cli releases new $GITHUB_SHA` dans les deux workflows deploy (optionnel).

### H.2 UptimeRobot
Crée 3 monitors HTTPS (interval 5 min) :
1. `https://pilot-review.com` — keyword *Pilot Review* attendu
2. `https://api.pilot-review.com/health` — status 200
3. `https://api.pilot-review.com/api/v1/openapi.json` — status 200

Alert contacts : email + Telegram (créer un *Alert Contact* type Telegram avec ton bot existant).

### H.3 Backups Cloudflare R2
- Bucket `gbp-pilot-review-backups` créé en Phase A.1
- Lifecycle rule : delete after 30 days
- Le timer systemd (Phase C.7) exécute `scripts/backup.sh` chaque jour à 03:00 UTC
- **Restore test mensuel** : récupérer le dump le plus récent, le restaurer dans une DB jetable, vérifier intégrité (`SELECT count(*) FROM users`, etc.). Documenter la procédure dans `docs/runbook.md`.

### H.4 fail2ban
```bash
sudo apt install fail2ban
sudo systemctl enable --now fail2ban
```
Le jail SSH est actif par défaut.

### H.5 Runbook incident — `docs/runbook.md`
À créer, contenant :
- Procédure restart workers : `docker compose -f docker-compose.prod.yml restart worker-polling`
- Procédure restore DB depuis R2
- Rotation des secrets (Fernet key, JWT secret)
- Contacts d'urgence (Resend support, Cloudflare, Oracle)

### Vérification Phase H
- Déclencher une 500 volontaire → événement reçu sur Sentry < 1 min
- Couper temporairement le service API (`docker compose stop api`) 6 min → alerte UptimeRobot reçue
- Exécuter `scripts/backup.sh` à la main → fichier `.sql.gz` présent dans R2
- Tester restore sur DB jetable → données identiques

---

## Annexe — Liste des fichiers créés par ce guide

### Repo backend `/home/victor/Projects/gbp-pilot-review/`
- `setupProd.md` (ce fichier)
- `backend/Dockerfile`
- `docker-compose.prod.yml`
- `Caddyfile`
- `.env.prod.example`
- `scripts/deploy.sh`, `scripts/backup.sh`
- `.github/workflows/backend-ci.yml`, `.github/workflows/backend-deploy.yml`
- `.pre-commit-config.yaml`
- `docs/runbook.md`

### Repo frontend `/home/victor/Projects/gbp-pilot-review-website/`
- `wrangler.jsonc` (réécrit)
- `open-next.config.ts`
- `package.json` (scripts `build:cf`, `deploy:cf`)
- `CLAUDE.md` (mis à jour)
- `.github/workflows/frontend-ci.yml`
- Supprimés : `_astro-source/`, `dist/`

### Sur le VPS
- `/etc/caddy/origin.pem`, `/etc/caddy/origin.key`
- `/etc/systemd/system/gbp-pilot-review.service`
- `/etc/systemd/system/gbp-pilot-review-backup.{service,timer}`
- `/etc/docker/daemon.json` (log rotation)
- `~/gbp-pilot-review/.env`

---

## À retenir

- **Tu n'as pas besoin de tout faire d'un coup.** Phases A → E pour avoir le site et l'API en ligne reliés. Phase F pour valider les features une à une. Phases G et H peuvent venir après les premiers tests utilisateurs.
- **Itère feature par feature** dans la Phase F : ne passe pas au test suivant tant que le précédent n'est pas vert.
- **Rollback** : `cd ~/gbp-pilot-review && git checkout <sha-précédent> && bash scripts/deploy.sh`.
- **Mise à jour de ce guide** : à chaque changement d'infra (nouveau service, nouveau secret, changement de DNS), update ce fichier dans le même commit, comme on le fait pour `setup.md`.
