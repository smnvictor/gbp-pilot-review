# Runbook — Incidents de production Pilot Review

Procédures de réponse aux incidents les plus courants. Ce document doit être lisible à 3h du matin sans contexte.

**Domaines** :
- Frontend : `https://pilot-review.com` (Cloudflare Workers via OpenNext)
- Backend : `https://api.pilot-review.com` (FastAPI + Celery sur VPS Oracle)
- Base de données : Postgres 16 (container Docker sur VPS)

**Accès** :
- SSH VPS : `ssh vps` (alias dans `~/.ssh/config`, clé `~/.ssh/id_ed25519`)
- Path projet sur VPS : `/home/ubuntu/gbp-pilot-review`
- Cloudflare : compte personnel (Workers & Pages)
- Sentry : organisation perso, projets `gbp-pilot-review-backend` et `gbp-pilot-review-frontend`

---

## 1. Diagnostic initial — par où commencer

Avant tout, identifier ce qui est down :

```bash
# Frontend
curl -I https://pilot-review.com

# Backend health
curl https://api.pilot-review.com/healthz

# Backend full
curl https://api.pilot-review.com/openapi.json | head -c 100
```

Si frontend down mais backend OK → problème Cloudflare Workers ou Pages.
Si backend down → SSH au VPS et investiguer (sections suivantes).

---

## 2. Backend down ou erreurs 5xx

### 2.1 Vérifier l'état des containers

```bash
ssh vps
cd ~/gbp-pilot-review
docker compose -f docker-compose.prod.yml ps
```

État attendu : tous les services en `Up X minutes (healthy)`. Si un service est `Restarting`, `Exit X`, ou `unhealthy`, c'est lui le coupable.

### 2.2 Logs récents

```bash
# API uniquement
docker compose -f docker-compose.prod.yml logs --tail=200 api

# Tous les services applicatifs
docker compose -f docker-compose.prod.yml logs --tail=100 api beat worker-default worker-polling worker-generation worker-publication worker-notification

# Suivre en live
docker compose -f docker-compose.prod.yml logs -f api
```

### 2.3 Restart d'un service spécifique

```bash
# Restart api uniquement
docker compose -f docker-compose.prod.yml restart api

# Force recreate si problème de config / env vars
docker compose -f docker-compose.prod.yml up -d --force-recreate --no-deps api
```

### 2.4 Tout redémarrer (cas grave)

```bash
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
```

⚠️ Ça interrompt brièvement Postgres et Redis aussi. À utiliser en dernier recours.

---

## 3. Postgres : password / connection refused

### 3.1 Symptôme

API logs montrent :
> `psycopg.OperationalError: FATAL: password authentication failed for user "postgres"`

### 3.2 Cause typique

Désynchronisation entre `DATABASE_URL` dans `.env` et le password réel du user `postgres` en DB. Possible après une rotation cron mal exécutée.

### 3.3 Fix

```bash
# Récupérer le password actuel de .env
grep '^DATABASE_URL' ~/gbp-pilot-review/.env
# Copier la partie entre "postgres:" et "@postgres:5432"

# Reset le password Postgres avec cette valeur
docker compose -f docker-compose.prod.yml exec postgres psql -U postgres
# Dans psql :
# ALTER USER postgres WITH PASSWORD '<PASSWORD_FROM_ENV>';
# \q

# Re-deploy
bash scripts/deploy.sh
```

---

## 4. Tokens OAuth Google expirés / révoqués

### 4.1 Symptôme

API renvoie 401/403 sur les calls Google Business Profile. Polling Celery échoue.

### 4.2 Action immédiate

Vérifier le statut OAuth du client concerné dans le dashboard admin.

```bash
# Forcer un refresh des tokens
docker compose -f docker-compose.prod.yml exec api python -c "
from app.tasks.maintenance_tasks import refresh_oauth_tokens
refresh_oauth_tokens.apply()
"
```

Si le refresh échoue → contacter le client pour ré-autoriser OAuth.

---

## 5. Restore Postgres depuis un backup R2

Procédure testée le 2026-06-02. À rejouer en cas de corruption de la DB prod.

### 5.1 Lister les backups disponibles

```bash
rclone ls r2:gbp-pilot-review-backup | sort -k2 | tail -10
```

### 5.2 Test de restore (sans toucher la prod) dans un container jetable

```bash
BACKUP_FILE="db-20260601T030233Z.sql.gz"  # adapter
rclone copy r2:gbp-pilot-review-backup/$BACKUP_FILE /tmp/

docker run --rm -d --name pg-restore-test \
  -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=restore_test \
  postgres:16-alpine
sleep 8

zcat /tmp/$BACKUP_FILE | \
  docker exec -i pg-restore-test psql -U postgres -d restore_test

# Vérifier
docker exec pg-restore-test psql -U postgres -d restore_test -c "
SELECT 'users' AS t, count(*) FROM users
UNION ALL SELECT 'clients', count(*) FROM clients;
"

# Cleanup
docker stop pg-restore-test
rm /tmp/$BACKUP_FILE
```

### 5.3 Restore en prod (situation critique uniquement)

⚠️ DANGER : écrase la DB prod. À ne faire que si la DB prod est corrompue et qu'on a confirmation que le backup contient des données récentes.

```bash
# 1. Stopper l'API et les workers pour éviter les writes pendant le restore
docker compose -f docker-compose.prod.yml stop api beat worker-default worker-polling worker-generation worker-publication worker-notification

# 2. Drop puis recréer la DB
docker compose -f docker-compose.prod.yml exec postgres psql -U postgres -c "DROP DATABASE gbp_pilot_review;"
docker compose -f docker-compose.prod.yml exec postgres psql -U postgres -c "CREATE DATABASE gbp_pilot_review;"

# 3. Restore le dump
rclone copy r2:gbp-pilot-review-backup/$BACKUP_FILE /tmp/
zcat /tmp/$BACKUP_FILE | \
  docker compose -f docker-compose.prod.yml exec -T postgres psql -U postgres -d gbp_pilot_review

# 4. Redémarrer les services
docker compose -f docker-compose.prod.yml up -d

# 5. Vérifier l'état
docker compose -f docker-compose.prod.yml ps
curl https://api.pilot-review.com/healthz
```

---

## 6. Rotation des secrets

### 6.1 OAUTH_TOKEN_ENCRYPTION_KEY (Fernet)

⚠️ Si tu changes cette clé, tous les tokens OAuth déjà chiffrés en DB deviennent **illisibles**. Procédure de rotation propre = re-chiffrer la DB avec la nouvelle clé. Pour l'instant : ne pas la changer en prod sans plan de rotation.

### 6.2 JWT_SECRET

Si tu changes cette clé, **tous les utilisateurs sont déconnectés** (les JWT existants deviennent invalides).

```bash
# Générer une nouvelle clé
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# Sur le VPS, éditer .env
nano ~/gbp-pilot-review/.env  # remplacer JWT_SECRET

# Restart api + workers pour qu'ils relisent .env
docker compose -f docker-compose.prod.yml up -d --force-recreate --no-deps api beat worker-default worker-polling worker-generation worker-publication worker-notification
```

### 6.3 Postgres password

Procédure : `ALTER USER postgres WITH PASSWORD '...'` puis update `.env` puis `up -d --force-recreate --no-deps`. Voir section 3 ci-dessus.

---

## 7. Déploiement manuel (si GitHub Actions plante)

```bash
ssh vps
cd ~/gbp-pilot-review
git pull --ff-only
bash scripts/deploy.sh
```

Le script gère build → up → alembic upgrade.

---

## 8. Rollback en urgence

```bash
ssh vps
cd ~/gbp-pilot-review
git log --oneline -10  # noter le SHA du dernier commit OK
git checkout <SHA_OK>
bash scripts/deploy.sh
```

⚠️ Si des migrations Alembic ont été appliquées entre les deux SHAs, le rollback ne défait PAS les migrations. À faire à la main si besoin :

```bash
docker compose -f docker-compose.prod.yml exec api alembic downgrade <revision>
```

---

## 9. Contacts d'urgence

- **Anthropic API** : status.anthropic.com
- **Cloudflare** : cloudflarestatus.com, support via dashboard
- **Oracle Cloud** : status.oraclecloud.com, support via console
- **Lemon Squeezy** : support@lemonsqueezy.com
- **Resend** : status.resend.com, support@resend.com
- **Sentry** : status.sentry.io
- **UptimeRobot** : (notifications email automatiques en cas de panne détectée)

---

## 10. Notes opérationnelles

- Cron polling Celery : 11h, 14h, 17h, 20h Europe/Paris
- Backup automatique : 03:00 UTC chaque jour vers R2 (rétention 14j)
- Healthcheck : tous services Docker `(healthy)` après 30s
- Reverse proxy : Caddy avec Cloudflare Origin Cert (15 ans)
- TLS mode Cloudflare : Full (strict)
