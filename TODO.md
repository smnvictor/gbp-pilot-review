# TODO — Dette technique et points à traiter plus tard
Liste extensible des sujets identifiés mais reportés. Format : un bullet par sujet, avec date d'ouverture, contexte, et impact.
---
## Backend
- **[2026-05-19] Tests asyncpg cassés sous Python 3.13 en local**
- **Symptôme** : 55 tests sur 110 échouent avec `asyncpg.InterfaceError: cannot perform operation: another operation is in progress`
- **Contexte** : apparu après mise à jour Arch Python 3.12 → 3.13. Le code n'a pas changé.
- **Cause probable** : régression d'isolation entre tests dans `pytest-asyncio` / `asyncpg` sur Python 3.13 (event loop mal nettoyée entre tests, sessions zombies)
- **Impact** : tests fonctionnent toujours sur CI (Python 3.12 fixé par le Dockerfile) — bloque uniquement le run local sous Arch
- **Pistes** : downgrade local en 3.12 via `uv python install 3.12`, ou fix conftest pour forcer le close des sessions
---
## Infrastructure / Déploiement
- **[2026-05-29] Cloudflare Email Routing — bouton "Enable" qui charge dans le vide**
- **Symptôme** : clic sur "Enable Email Routing" depuis l'écran Overview ne répond pas, la page tourne sans aboutir
- **Contexte** : tentative d'activation après suppression du forwarding Namecheap (DNS délégué à Cloudflare donc forwarding Namecheap inopérant) et désinscription d'ImprovMX. Email Routing est partiellement configuré (1 custom address + 1 destination address déjà créés) mais reste en état "disabled". Conflits DNS détectés (5 MX `eforward*.registrar-servers.com` à supprimer, 2 SPF apex obsolètes à fusionner) non encore résolus côté UI.
- **Impact** : aucun email forwarding pro disponible. Pas de `contact@pilot-review.com`, `victor.simon@pilot-review.com`, etc. Les mails entrants tombent dans le vide.
- **Pistes** : retry plus tard (possiblement un incident Cloudflare ponctuel), forcer le fix DNS manuellement depuis l'onglet DNS (supprimer les 5 MX Namecheap + consolider les SPF en un seul `v=spf1 include:_spf.mx.cloudflare.net ~all`) puis retry Enable, contact support Cloudflare si persistant
- **[2026-05-30] Cron rotation Postgres password — désynchronisation entre `.env` et DB**
- **Symptôme** : `psycopg.OperationalError: FATAL: password authentication failed for user "postgres"` lors d'un déploiement, alors que `.env` et l'API container avaient le même `DATABASE_URL`
- **Contexte** : la cron qui rotate le password Postgres via `ALTER USER` + update du `.env` a probablement désynchronisé l'un des deux côtés à un moment. Fix manuel appliqué via `ALTER USER postgres WITH PASSWORD '...'` depuis le container, en se basant sur la valeur de `.env`
- **Impact** : tout déploiement futur peut planter au `alembic upgrade head` si la cron diverge à nouveau. Risque de downtime au pire moment
- **Pistes** : auditer le script cron (probablement dans `/etc/cron.d/` ou crontab root sur le VPS), s'assurer que les deux opérations sont atomiques (l'une échoue → l'autre est revertée), logger explicitement chaque rotation pour debug, alternative envisageable : passer à un secret manager (Vault, AWS Secrets Manager) si la rotation devient critique
---
## Sécurité / Conformité
_(rien pour l'instant)_
