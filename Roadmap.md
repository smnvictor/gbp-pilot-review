# Roadmap — Projet d'automatisation des réponses aux avis Google

Roadmap complète et chronologique pour le développement, le déploiement et le lancement du SaaS d'automatisation de réponses aux avis Google Business Profile. Les étapes sont ordonnées pour minimiser les blocages : préparation Google en amont (validation OAuth longue), fondations techniques avant features, et expansion après validation produit.

---

## Phase 0 — Préparation et fondations

### Setup légal et administratif
- Création ou adaptation du statut juridique (micro-entrepreneur si pas encore fait)
- Ouverture d'un compte bancaire professionnel dédié
- Rédaction des documents légaux : Terms of Service, Privacy Policy, DPA, mentions légales
- Inscription au registre RGPD si nécessaire

### Réservation des assets
- Achat du nom de domaine
- Création du repo GitHub avec licence (BUSL-1.1 ou AGPL)
- Création des comptes : Google Cloud Console, Lemon Squeezy, Sentry, UptimeRobot, Cloudflare
- Configuration du VPS Oracle Free Tier (OS, SSH keys, user non-root, firewall UFW)

### Setup Google Cloud pour OAuth
- Création du projet Google Cloud
- Activation de l'API Google Business Profile
- Configuration de l'écran de consentement OAuth
- Génération des credentials client ID / client secret
- Prise de connaissance du processus de verification et constitution du dossier initial

---

## Phase 1 — Architecture et conception

### Conception de la base de données
- Modélisation des entités (User, Client, Location, Review, Response, Notification, Subscription, etc.)
- Définition des relations et contraintes
- Schéma Alembic initial
- Stratégie d'indexation pour les requêtes fréquentes

### Conception de l'architecture backend
- Structure modulaire du projet Python
- Séparation services / repositories / models / tasks
- Design des interfaces entre modules
- Stratégie de configuration (variables d'environnement, secrets)

### Conception de l'architecture frontend
- Arborescence des routes Next.js
- Structure des composants réutilisables
- Design system avec shadcn/ui
- Stratégie d'authentification et de session

### Conception des flux critiques
- Flow OAuth Google Business Profile (authorization code, refresh token, gestion des scopes)
- Flow de polling → génération → validation → publication
- Flow de notifications multi-canal
- Flow de gestion des erreurs et retries

### Design du prompt IA
- Définition de la nomenclature du JSON de réponse (tous les codes `details` possibles)
- Structuration du prompt standardisé
- Gestion des variables dynamiques (contexte client, ton, avis)
- Stratégie de versioning des prompts

---

## Phase 2 — Infrastructure et fondations techniques

### Setup du VPS
- Installation Docker et Docker Compose
- Configuration Caddy comme reverse proxy
- Installation Postgres 16
- Installation Redis
- Configuration du firewall et sécurité SSH

### Setup CI/CD
- Workflows GitHub Actions pour lint / tests / build
- Pipeline de déploiement automatique sur push main
- Gestion des secrets via GitHub Secrets
- Stratégie de rollback

### Setup des environnements
- Environnement local (Docker Compose)
- Environnement de staging (optionnel sur le VPS)
- Environnement de production
- Gestion des variables d'environnement par environnement

### Setup monitoring
- Configuration Sentry (backend + frontend)
- Configuration UptimeRobot sur endpoints critiques
- Configuration Loguru avec rotation des logs
- Backups automatiques Postgres vers Cloudflare R2

---

## Phase 3 — Développement backend core

### Authentification et gestion utilisateur
- Système d'inscription / connexion
- Gestion des sessions et tokens
- Récupération de mot de passe
- Gestion du profil utilisateur

### Intégration OAuth Google Business Profile
- Flow d'authorization
- Stockage chiffré des tokens
- Refresh automatique des tokens
- Détection et gestion des tokens expirés/révoqués
- Récupération des locations du client

### Module Polling
- Job Celery planifié par client avec fréquence configurable
- Récupération des nouveaux avis via API
- Détection des avis non vus (deduplication)
- Gestion des erreurs API Google (rate limiting, 5xx, 401/403)

### Module Filtering
- Système de filtre regex configurable par client
- Détection de langue
- Règles de routing (note 1-3 obligatoire validation, avis sans texte, etc.)
- Déclenchement des notifications de filtrage

### Module Generation (IA)
- Intégration Claude API (Sonnet 4.6)
- Construction dynamique du prompt avec contexte client
- Parsing et validation du JSON de réponse
- Gestion des erreurs IA (timeout, malformation JSON, refus)
- Stockage des réponses générées

### Module Publication
- Job programmé avec délai aléatoire dans la fourchette configurée
- Respect des plages horaires configurables
- Publication via API Google Business Profile
- Gestion du délai de grâce "undo" de 10 minutes
- Gestion des retries avec backoff exponentiel

### Module Notification
- Intégration email (Resend ou similaire)
- Intégration Telegram (Bot API)
- Architecture extensible pour ajouter SMS plus tard
- Templates de notification par contexte
- Mode individuel vs digest quotidien

### Module Subscription
- Intégration Lemon Squeezy
- Webhooks pour événements (nouveau paiement, renouvellement, résiliation, échec paiement)
- Gestion des quotas par tier
- Gestion de l'essai gratuit de 2 semaines
- Gestion des upgrades/downgrades

### Module de gestion des erreurs et reliability
- Stratégie de retry par type d'erreur
- Dead letter queue pour les jobs échoués définitivement
- Alertes automatiques vers le dashboard admin
- Circuit breaker sur les APIs externes

---

## Phase 4 — Développement frontend client ✅ (migré hors dépôt)

> **Mai 2026** : Le frontend a été migré vers le dépôt voisin
> [`~/Projects/gbp-pilot-review-website/`](../gbp-pilot-review-website/) après une
> refonte complète de la charte graphique (Fraunces + Inter, palette marine `#0B1E3F`,
> design Astro 5 porté en Next.js 15). Le périmètre couvert :

### Pages publiques ✅ (dans `gbp-pilot-review-website/app/(marketing)/`)
- Landing page (Home) avec hero + steps + testimonials + targets + CTA
- Pages Features, Pricing (3 plans + FAQ), About, Contact (Formspree)
- Pages légales : Terms, Privacy, Mentions légales, DPA
- Formulaire de contact via Formspree (statique)

### Flow d'inscription et onboarding ✅
- `/signup` + `/verify-email` + `/login` + `/forgot-password` + `/reset-password`
- Stepper `/onboarding/{welcome,connect-google,connected,customize,complete}`

### Dashboard client ✅
- `/dashboard` (métriques calculées côté front depuis `/reviews`)
- `/reviews` (filtres status, pagination), `/reviews/[id]`
- `/pending`, `/settings` (4 onglets), `/billing` (Lemon Squeezy)

### Composants transversaux ✅
- Gestion des états de chargement (`loading.tsx`) et erreurs (`error.tsx`, `not-found.tsx`)
- Responsive design mobile-first (CSS modules + Tailwind)
- i18n : **FR uniquement** au lancement (next-intl retiré pour simplifier — réintégrable plus tard)

### Gaps backend à résoudre (cf. README.md)
- Endpoint `GET /reviews/{id}/responses` (réponse active) → débloque `/reviews/[id]`
- Customisation IA fine (tone, signature) → hors-scope Phase 4
- Endpoint `/api/v1/metrics` → métriques actuellement calculées côté front
- Notifications in-app → reportées Phase 5

---

## Phase 5 — Développement dashboard admin

### Vue clients
- Liste des clients avec recherche et filtres
- Détail d'un client (historique, métriques, statut)
- Actions admin (suspension, annotations)

### Vue validation
- Queue centralisée des réponses en attente (mode Pro/Business)
- Tri chronologique avec filtres par client
- Actions rapides (valider, regénérer, rédiger, supprimer)

### Vue monitoring technique
- Statut des jobs Celery (Flower ou dashboard custom)
- Erreurs récentes
- Tokens OAuth en alerte
- Métriques opérationnelles globales

### Vue suppression
- Interface pour supprimer des réponses publiées par erreur
- Historique des suppressions

---

## Phase 6 — Tests

### Tests unitaires
- Modules de génération de réponse (logique de filtering, parsing JSON IA)
- Modules de calcul de délai
- Repositories
- Utilitaires

### Tests d'intégration
- Flow complet polling → génération → publication (avec mocks Google et Claude)
- Flow OAuth
- Webhooks Lemon Squeezy
- Gestion des erreurs et retries

### Tests end-to-end
- Parcours d'inscription complet
- Parcours de validation d'une réponse
- Parcours de configuration

### Tests de charge légers
- Simulation de 20 clients actifs en simultané
- Vérification du comportement de la queue sous charge
- Mesure des temps de réponse

---

## Phase 7 — Sécurité et conformité

### Audit sécurité
- Revue des permissions et scopes OAuth
- Vérification du chiffrement des tokens au repos
- Audit des logs (pas de données sensibles en clair)
- Protection contre les injections (SQL, XSS, CSRF)
- Rate limiting sur les endpoints publics
- Sécurisation des webhooks (signatures Lemon Squeezy)

### Conformité RGPD
- Validation du DPA avec un juriste ou template sérieux
- Implémentation du droit à l'oubli (suppression complète J+30)
- Implémentation du droit d'accès (export des données)
- Cookie banner si nécessaire
- Registre des traitements

### Validation OAuth Google
- Finalisation du dossier de vérification
- Tournage de la vidéo de démonstration
- Soumission à Google
- Suivi et itérations si feedback de Google

---

## Phase 8 — Préparation lancement

### Préparation du premier client pilote
- Utilisation de l'agence d'assurance familiale comme bêta-testeur réel
- Collecte de feedback et ajustements
- Validation du workflow complet en conditions réelles

### Documentation
- Guide d'onboarding client (format vidéo ou PDF)
- FAQ sur le site
- Documentation interne pour debug (runbooks pour les incidents courants)
- Documentation de l'API interne pour toi

### Préparation opérationnelle
- Processus de réponse aux emails support
- Templates de réponse pour les cas courants
- Checklist d'onboarding d'un nouveau client
- Procédure de suspension / réactivation

---

## Phase 9 — Lancement bêta restreint

### Ouverture progressive
- 3 à 5 premiers clients payants (cercle proche, recommandations)
- Accès en dev mode OAuth (en attendant validation Google)
- Monitoring rapproché des premiers usages
- Feedback loops courts et itération rapide

### Ajustements post-bêta
- Correction des bugs prioritaires
- Ajustements UX suite aux retours
- Optimisation des prompts IA selon les résultats réels
- Enrichissement de la nomenclature `details` du JSON si nouveaux cas détectés

---

## Phase 10 — Lancement public

### Passage en production OAuth
- Validation Google reçue
- Ouverture au-delà du dev mode
- Communication publique

### Stratégie de contenu SEO
- Rédaction d'articles sur les sujets cibles ("comment répondre aux avis négatifs", "modèles de réponse avis restaurant", etc.)
- Optimisation on-page de la landing
- Inscription aux annuaires pertinents

### Démarchage actif (module séparé)
- Conception du pipeline de démarchage (Places API + enrichissement + cold email)
- Setup de l'outil d'emailing conforme (Instantly, Lemlist ou custom)
- Premières campagnes ciblées par zone et catégorie
- Itération sur les scripts et templates

### Partenariats
- Identification des agences de communication locale et consultants SEO local
- Mise en place du programme d'affiliation avec commission récurrente
- Documentation partenaires

---

## Phase 11 — Post-lancement et croissance

### Opérations continues
- Monitoring quotidien des clients en mode validation humaine
- Support client réactif
- Maintenance technique (mises à jour, patches sécurité)
- Review régulière des métriques business

### Amélioration continue
- Analyse des refus de réponses IA par les clients pour améliorer les prompts
- A/B testing sur les formulations de réponses
- Optimisation des coûts IA (caching, prompts plus courts si pertinent)
- Feedback systématique des clients

### Développement V2
- Priorisation des features secondaires selon les demandes clients
- SMS comme canal de notification
- Export de données pour clients
- Détection des avis modifiés
- CRM de démarchage dans le dashboard admin
- Multi-utilisateurs par compte client
- Extension à d'autres plateformes d'avis (Trustpilot, TripAdvisor, Pages Jaunes)
- Mode agence / white-label

### Expansion géographique
- Activation de la locale anglaise
- Adaptation des prompts IA pour l'anglais
- Validation OAuth pour usage international
- Adaptation des documents légaux
- Stratégie de pricing par marché