#!/usr/bin/env bash
# ============================================================================
# scripts/deploy.sh — Déploiement de gbp-pilot-review en production
# ============================================================================
# Utilisation :
#   bash scripts/deploy.sh           # déploie HEAD de la branche main
#
# Pré-requis (sur le VPS) :
#   - Repo cloné dans ~/gbp-pilot-review
#   - Fichier .env présent et rempli
#   - Cloudflare Origin Certificate déposé dans /etc/caddy/
#   - Docker + Docker Compose v2 installés
#   - User dans le groupe docker (ou exécution en sudo)
# ============================================================================

# --- Configuration sécurité bash ---
# -e : exit immédiat si une commande échoue
# -u : exit si variable non définie
# -o pipefail : exit si une commande dans un pipe échoue
set -euo pipefail
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# --- Constantes ---
readonly COMPOSE_FILE="docker-compose.prod.yml"
readonly REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# --- Couleurs pour les logs (visibilité) ---
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m'  # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Vérifications préliminaires ---
cd "$REPO_DIR"

if [[ ! -f "$COMPOSE_FILE" ]]; then
    log_error "Fichier $COMPOSE_FILE introuvable dans $REPO_DIR"
    exit 1
fi

if [[ ! -f ".env" ]]; then
    log_error "Fichier .env introuvable. Copier depuis .env.prod.example et remplir."
    exit 1
fi

# --- Trap d'erreur : log si le script échoue à mi-chemin ---
trap 'log_error "Déploiement échoué à la ligne $LINENO. État containers ci-dessous :"; docker compose -f "$COMPOSE_FILE" ps || true' ERR

# --- 1. Pull du code ---
log_info "Pull du code depuis Git..."
git fetch --all
git pull --ff-only

readonly COMMIT_SHA=$(git rev-parse --short HEAD)
log_info "Déploiement du commit : $COMMIT_SHA"

# --- 2. Pull des images base (postgres, redis, caddy) ---
log_info "Pull des images Docker de base..."
docker compose -f "$COMPOSE_FILE" pull --quiet postgres redis caddy

# --- 3. Build de l'image backend ---
log_info "Build de l'image backend..."
docker compose -f "$COMPOSE_FILE" build --pull api

# --- 4. Démarrage des services ---
log_info "Démarrage des services (mode détaché)..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# --- 5. Attente que Postgres soit prêt avant migration ---
log_info "Attente que Postgres soit healthy..."
for i in {1..30}; do
    if docker compose -f "$COMPOSE_FILE" ps postgres --format json | grep -q '"Health":"healthy"'; then
        log_info "Postgres est prêt."
        break
    fi
    if [[ $i -eq 30 ]]; then
        log_error "Postgres n'est pas devenu healthy après 60 secondes."
        exit 1
    fi
    sleep 2
done

# --- 6. Migration de la base ---
log_info "Application des migrations Alembic..."
docker compose -f "$COMPOSE_FILE" exec -T api alembic upgrade head

# --- 7. Affichage final de l'état ---
log_info "État des services après déploiement :"
docker compose -f "$COMPOSE_FILE" ps

log_info "Déploiement de $COMMIT_SHA terminé avec succès ✅"
