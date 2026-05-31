# Checklist de vérification — Correction UI globale

À cocher manuellement après déploiement de la branche `feature/ui-overhaul`.

## Frontend (pilot-review.com)

- [ ] Header : lien "Se connecter" visible (déconnecté) → mène à /login
- [ ] Header : bouton "Essai gratuit 14 jours" visible (déconnecté) → mène à /signup
- [ ] Header : menu utilisateur visible (connecté) avec Dashboard / Paramètres / Déconnexion
- [ ] Footer : colonne "Compte" présente
- [ ] Mobile : burger menu fonctionne avec auth links
- [ ] Dashboard : bouton "Connecter Google Business Profile" présent si non connecté
- [ ] /dashboard/settings : onglet Publication save et persiste après reload
- [ ] /dashboard/settings : onglet Langue ne crash plus
- [ ] /dashboard/settings : section "Ton de réponse" avec 3 options multi-sélection
- [ ] /dashboard/settings : champ "Informations sur votre entreprise" présent et persiste
- [ ] /dashboard/settings : champs "Toujours mentionner" / "Jamais mentionner" présents
- [ ] /dashboard/settings : champ "Fréquence polling" supprimé de l'UI
- [ ] /dashboard/settings : onglet "Connexion Google" (statut + reconnecter + locations)
- [ ] /dashboard/billing : 3 plans Starter/Pro/Business avec bons prix (19/39/79€)
- [ ] /dashboard/billing : clic sur "Choisir ce plan" ne renvoie plus de 502
- [ ] /dashboard/billing : checkout Lemon Squeezy s'ouvre correctement
- [ ] Onboarding : déclenchement automatique au 1er login
- [ ] Onboarding : étape 0 (OAuth) → 1 (Location) → 2 (IA) avec transitions Framer Motion fluides
- [ ] Onboarding : bouton "Passer" → modale de confirmation
- [ ] Onboarding : skip applique les valeurs par défaut et termine
- [ ] /dashboard/test : mode "Avis fictif" génère une réponse sans consommer le quota
- [ ] /dashboard/test : mode "Avis réel" liste les avis et permet test sans publication
- [ ] /dashboard/test : non accessible (ou placeholder) si pas d'abo actif/essai

## Backend (api.pilot-review.com)

- [ ] Polling Celery exécuté à 11h / 14h / 17h / 20h (Europe/Paris)
- [ ] Migration Alembic 0003 appliquée (clients.tone, always_mention, never_mention)
- [ ] POST /api/v1/test/generate-response fonctionne sans toucher quota/DB
- [ ] POST /api/v1/subscription/checkout retourne une URL Lemon Squeezy valide
      (variantes LEMONSQUEEZY_VARIANT_{STARTER,PRO,BUSINESS} configurées ; sinon 503 explicite)
- [ ] GET /api/v1/oauth/google/status renvoie l'état de connexion + locations
- [ ] Endpoint settings/publication persiste correctement (publish_delay_range)
- [ ] client.onboarding_completed_at marqué après onboarding terminé (POST /onboarding/complete)

## Suite à valider en prod

- [ ] Tous les containers Docker healthy après deploy
- [ ] Aucune régression sur Notification / Filtrage (qui marchaient avant)
- [ ] Aucune erreur Sentry nouvelle après 24h
