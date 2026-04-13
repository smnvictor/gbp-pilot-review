# Contexte du projet — SaaS d'automatisation des réponses aux avis Google Business Profile

## 1. Vision et positionnement

Le projet est un SaaS qui automatise la gestion et la réponse aux avis Google Business Profile pour des petits et moyens commerces (restaurants, artisans, médecins, salons, garages, agences d'assurance, etc.). Le produit se positionne comme une alternative française, abordable et RGPD-compliant aux solutions américaines existantes (Birdeye, Podium, Grade.us) qui sont hors de prix pour une PME française (250-500€/mois).

Le cœur de la proposition de valeur est le gain de temps : au lieu que le gérant rédige lui-même chaque réponse aux avis (ce qu'il ne fait souvent pas, d'où un impact négatif sur son e-réputation et son SEO local), le SaaS génère des réponses personnalisées via IA, respectueuses du ton de l'entreprise, publiées automatiquement ou après validation selon le plan choisi.

Le marché cible initial est la France, avec une architecture prévue pour étendre à l'UK et aux US dans un second temps (internationalisation prévue dès l'architecture mais pas activée au MVP).

## 2. Modèle économique

### Plans tarifaires (modulables, non définitifs)

**Starter — 19€/mois**
- 1 établissement Google Business Profile
- 10 réponses IA par mois
- Mode "suggestion" uniquement (le client valide chaque réponse avant publication)
- 1 tentative de regénération par avis
- Notifications email uniquement
- Pas de gestion des réponses multiples (thread)

**Pro — 39€/mois**
- Jusqu'à 3 établissements
- 50 réponses IA par mois
- Mode suggestion OU mode validation humaine par l'équipe
- 3 tentatives de regénération par avis
- Notifications email ou Telegram
- Gestion des réponses multiples (thread complet envoyé à l'IA)

**Business — 79€/mois**
- Établissements illimités
- Réponses illimitées
- Mode validation humaine par l'équipe disponible
- Regénérations illimitées
- Notifications email, Telegram, ou SMS (SMS en V2)
- Gestion des réponses multiples

### Essai et facturation

- Essai gratuit de 2 semaines sans carte bancaire requise
- Facturation via Lemon Squeezy (Merchant of Record, gère automatiquement la TVA française et européenne)
- Engagement mensuel sans contrainte (l'annuel avec remise sera envisagé plus tard)
- À la résiliation : polling désactivé immédiatement, données conservées 30 jours puis suppression complète

### Quota de réponses — règle de comptage

Chaque appel au LLM compte dans le quota mensuel du client, y compris les regénérations. Cela reflète le coût réel côté infrastructure. Les tentatives qui échouent (IA refuse de répondre) ne sont pas comptées.

## 3. Périmètre MVP et contraintes

Le MVP doit rester simple et shippable rapidement. Les features secondaires sont identifiées et documentées mais reportées en V2. L'architecture doit être modulable et orientée objet pour permettre d'ajouter facilement des fonctionnalités (nouvelles métriques dashboard, nouveaux canaux de notification, nouveaux types de traitement) sans refonte.

Contraintes techniques : stack gratuite uniquement (VPS Oracle Free Tier pour l'hébergement, Redis, Postgres, Claude API comme seul coût variable), tout hébergé sur le même VPS pour simplifier le CI/CD et le monitoring.

## 4. Workflow fonctionnel complet

### Étape 1 — Onboarding

Le client est déjà converti (le démarchage n'est pas inclus dans le MVP, ce sera un module séparé plus tard). Une réunion de kickoff en visio est organisée. Elle sert à :
- Présenter le produit et répondre aux questions
- Montrer des exemples de réponses générées (utilisation de l'agence d'assurance familiale comme démo)
- Remplir ensemble le formulaire guidé de customisation
- Initier le flow OAuth Google Business Profile

Le formulaire de customisation combine des questions guidées (type d'activité, valeurs de l'entreprise, tutoiement/vouvoiement, longueur préférée des réponses, signature, éléments à toujours mentionner, éléments à ne jamais mentionner) ET un champ texte libre pour que le client ajoute toute nuance qu'il juge importante.

Après connexion OAuth, le polling démarre uniquement sur les nouveaux avis. Les avis historiques non-répondus ne sont pas traités (trop risqué, trop de volume potentiel, et certains sont très anciens).

### Étape 2 — Polling et génération de réponse

Un job de polling interroge l'API Google Business Profile à intervalle configurable :
- Par défaut : 1 fois par jour
- Customisable jusqu'à 1 fois par heure pour les plans Pro et Business
- Si plusieurs avis sont détectés dans le même polling, ils sont traités avec 4-5 minutes d'intervalle pour étaler la charge

**Important à vérifier en pré-lancement** : la Google Business Profile API n'offre pas de webhooks natifs pour les nouveaux avis, le polling est la seule option officielle. Cette limitation doit être confirmée et documentée au moment du développement.

Quand un nouvel avis est détecté, il passe par plusieurs étapes :

**Filtrage préalable par regex** — Un système de filtre regex analyse le contenu de l'avis avant tout appel IA. Le client configure depuis son dashboard une liste de mots-clés ou expressions bannis (ex : "intoxication", "police", "porter plainte", noms de concurrents, etc.). Si un mot banni est détecté, aucune réponse IA n'est générée : une notification est envoyée au client pour qu'il réponde manuellement. Ce filtre protège contre les sujets sensibles nécessitant une réponse humaine.

**Détection de la langue** — Par défaut, la réponse est générée dans la langue de l'avis (un touriste anglais laisse un avis en anglais → réponse en anglais). Le client peut désactiver ce comportement dans les préférences pour forcer une langue spécifique.

**Note de l'avis et règle des avis négatifs** — Indépendamment du mode choisi par le client (suggestion ou auto), tout avis avec une note de 1 à 3 étoiles est automatiquement routé vers une validation humaine obligatoire. Cette règle est non-négociable et protège contre les catastrophes de communication sur les avis sensibles.

**Avis sans texte** — Les avis avec uniquement une note (pas de commentaire texte) font l'objet d'une option configurable par le client : soit on les ignore, soit on y répond avec un message court standardisé ("Merci pour votre note !"). Par défaut, cette option est activée pour les 4-5 étoiles uniquement.

**Avis modifiés après réponse** — Point d'attention pour la V2 : si l'auteur d'un avis modifie son avis après que notre système a répondu, le MVP ignore cette modification. À améliorer plus tard (stratégies possibles : détection de la modification, suppression de la réponse obsolète, génération d'une nouvelle réponse).

**Réponses multiples (threads)** — Pour les plans Pro et Business uniquement, si un client laisse un commentaire supplémentaire après notre réponse, le thread complet est renvoyé à l'IA qui génère une nouvelle réponse suivant le même workflow qu'une réponse initiale. Pour le plan Starter, les threads sont ignorés.

**Génération de réponse via Claude Sonnet 4.6** — L'appel LLM utilise un prompt standardisé structuré comme suit :
1. Consignes universelles de réponse (politesse, pas de promesses irréalistes, pas d'informations commerciales sensibles, gestion des avis problématiques)
2. Contexte custom de l'entreprise (fourni par le client)
3. Ton custom des réponses (fourni par le client)
4. L'avis à traiter (ou le thread complet pour les réponses multiples)

L'IA répond obligatoirement en JSON structuré :
```json
{
  "status": 0 ou 1,
  "content": "texte de la réponse, vide si status 0",
  "details": "raison si status 0, nomenclature à définir (ex: 'content_too_sensitive', 'unclear_request', 'language_not_supported')"
}
```

Le champ `details` suit une nomenclature interne qui détermine les actions suivantes (à qui notifier, quel template, etc.). Cette nomenclature sera enrichie au fil du temps. Si `status: 0`, la réponse bascule en validation humaine obligatoire avec la raison affichée.

### Étape 3 — Délai de réponse configurable

Une fois la réponse générée et validée (ou en attente de validation), elle est programmée pour publication selon le délai choisi par le client parmi : 1h-2h, 2h-5h, 5h-1j, 1j-2j, 2j-5j.

Le timing de publication réel est randomisé dans la fourchette choisie (ex : choix 1j-2j → publication effective entre 24h et 48h après détection de l'avis). Cette randomisation évite de donner l'impression d'une réponse automatique trop régulière.

Des plages horaires de publication sont respectées : par défaut entre 9h et 21h (configurable par le client). Si le timing calculé tombe hors plage, la publication est décalée au prochain créneau disponible.

### Étape 4 — Publication

Deux modes selon le plan et les préférences du client :

**Mode suggestion (tous plans)** — Le client reçoit une notification (email, Telegram ou SMS selon son canal configuré) avec :
- L'avis original
- La réponse générée
- Un lien sécurisé vers le dashboard pour valider, refuser, regénérer ou rédiger manuellement

La notification par défaut est individuelle (une par avis). Le client peut configurer un mode digest quotidien s'il préfère recevoir tous les avis du jour groupés dans une seule notification.

Sur le dashboard, le client peut :
- Valider → la réponse est programmée pour publication selon le délai configuré
- Refuser et regénérer (limité par tier)
- Refuser et rédiger manuellement
- Ignorer (pas de réponse)

**Mode validation humaine (Pro et Business uniquement)** — L'équipe (moi au début) valide manuellement les réponses via le dashboard admin. Le client a visibilité totale sur son dashboard : il voit en temps réel le statut de chaque avis (reçu, en attente de validation équipe, publié). Il peut à tout moment reprendre la main sur un avis spécifique en cliquant "Je valide moi-même celui-ci", ce qui retire l'avis de ma file de validation.

Capacité maximale du mode validation humaine : 20 clients maximum. Au-delà, liste d'attente. Aucun SLA formel sur les délais de validation côté équipe.

### Étape 5 — Gestion des erreurs et reliability

**Échec de publication Google** — Si la publication Google échoue (API indisponible, erreur réseau, rate limit), le job retry automatiquement 3 fois avec backoff exponentiel (1 min, 5 min, 30 min). Après 3 échecs, le client reçoit une notification avec le contenu de la réponse qu'il peut publier manuellement depuis son interface Google Business Profile.

**Token OAuth expiré** — Si le token d'un client expire ou est révoqué, le système le détecte à la première requête en erreur 401/403. Actions automatiques :
1. Le job de polling spécifique à ce client est mis en pause (inutile d'interroger Google avec un token mort)
2. Les jobs de publication en attente dans la queue restent en attente (ils seront rejoués quand le token sera ré-autorisé)
3. Un email automatique est envoyé au client avec un lien de réautorisation OAuth
4. Si pas de réautorisation sous 48h, notification à l'équipe (moi)
5. Si le token revient avant 7 jours, les réponses en attente sont publiées automatiquement avec réajustement des délais
6. Au-delà de 7 jours sans réautorisation, les jobs de publication en attente sont annulés et le client est notifié

Ce design exploite la nature découplée de la queue : l'ingestion (polling) et la publication sont indépendantes, ce qui permet d'encaisser les pannes externes sans perdre de travail.

### Étape 6 — Suppression de réponses

L'API Google Business Profile permet de supprimer une réponse publiée via `accounts.locations.reviews.deleteReply`. Cette fonctionnalité est réservée à l'équipe (moi) depuis le dashboard admin, pas accessible au client en self-service. Note : l'API ne permet pas d'éditer une réponse existante, seulement de la supprimer puis en poster une nouvelle (`updateReply` fait cette opération automatiquement en un appel).

**Délai de grâce "undo"** — Avant toute publication effective (après validation), un délai de 10 minutes est observé pendant lequel le client (ou l'équipe pour le mode validation) peut annuler la publication depuis le dashboard. Au-delà de 10 minutes, la réponse part vers Google et la seule option est la suppression post-publication par l'équipe.

## 5. Stack technique

### Backend

- **Langage** : Python 3.12+
- **Framework API** : FastAPI (moderne, typé, async natif, performant)
- **ORM** : SQLAlchemy 2.0 avec Alembic pour les migrations
- **Architecture** : orientée objet avec séparation claire services / repositories / models, structure modulaire pour faciliter l'ajout de features
- **Queue** : Celery + Redis (Python-natif, robuste, tourne sur le VPS, gratuit). Alternative envisagée : Dramatiq + Redis si Celery se révèle trop complexe. La queue est essentielle pour :
  - Programmer les publications avec délai aléatoire configurable
  - Retry automatique avec backoff en cas d'échec
  - Découplage polling/génération/publication pour la reliability
  - Dashboard de monitoring des jobs (Flower pour Celery, BullBoard pour BullMQ)

### Frontend

- **Framework** : Next.js 14+ (App Router), déployé sur le VPS
- **UI** : Tailwind CSS + shadcn/ui pour un design moderne et maintenable
- **Authentification client** : NextAuth.js avec provider Google (cohérent avec le flow OAuth principal)
- **i18n** : next-intl dès le départ, avec extraction des strings dans des fichiers de locale (fr/en), même si seul le français est actif au MVP, pour faciliter l'expansion UK/US future

### Base de données

- **Postgres 16** hébergé sur le VPS
- Sauvegardes automatiques quotidiennes vers Cloudflare R2 (gratuit jusqu'à 10 Go)
- Rétention des backups : 30 jours

### Reverse proxy et HTTPS

- **Caddy** pour le reverse proxy (HTTPS automatique via Let's Encrypt, configuration en 5 lignes)

### Facturation

- **Lemon Squeezy** comme Merchant of Record. Justification : gère automatiquement la TVA EU et les taxes US, évite les complications fiscales en France pour un solo maker, tier gratuit à 5% + 0.50$ par transaction. Stripe serait plus flexible mais demanderait de gérer soi-même la TVA, ce qui n'est pas un bon usage du temps au démarrage.

### Monitoring

- **Uptime** : UptimeRobot (gratuit, pings externes)
- **Erreurs applicatives** : Sentry (tier gratuit généreux pour un MVP)
- **Logs structurés** : Loguru en Python, écrits localement + consultables depuis le dashboard admin
- **Métriques business** : dashboard admin custom (les métriques comme MRR et churn sont fournies par Lemon Squeezy, pas besoin de dupliquer). Mon dashboard se concentre sur les métriques opérationnelles : nombre de réponses traitées, taux de succès, latences moyennes, tokens OAuth en erreur, jobs en échec, alertes techniques.

### Infrastructure

- **Hébergement unique** : VPS Oracle Cloud Free Tier (ARM Ampere, 4 vCPU, 24 Go RAM)
- Tout (frontend Next.js, backend FastAPI, Postgres, Redis, Celery workers) tourne sur le même VPS pour simplicité CI/CD et monitoring centralisé
- **CI/CD** : GitHub Actions pour build/test/deploy automatique sur push main
- **Domaine** : à acheter (~10€/an en .com)

### Open source et licence

Le code est open source avec une **licence Business Source License (BUSL-1.1)** ou **PolyForm Noncommercial**. Ces licences permettent la consultation publique (bonus CV et crédibilité) tout en interdisant toute utilisation commerciale par un tiers. Alternative plus simple : **AGPL v3** (copyleft fort qui décourage les clones commerciaux). Le choix final se fera au moment de la publication du repo.

## 6. Dashboard client

### Fonctionnalités MVP

- Page d'accueil avec métriques : nombre d'avis reçus sur la période, note moyenne, pourcentage de réponse, temps moyen de réponse, répartition par note
- Page "Avis" avec historique paginé, filtres par statut (en attente, publié, refusé), recherche
- Page "En attente" avec la liste des avis nécessitant action (validation, regénération, rédaction manuelle)
- Page "Configuration" avec modification des préférences self-service : horaires de publication, délais de réponse, canal de notification, liste de mots-clés bannis, option de réponse aux avis sans texte, langue forcée ou non
- Page "Abonnement" avec gestion via Lemon Squeezy (upgrade, downgrade, résiliation, factures)
- Page "About" et accès aux Terms of Service, DPA, politique de confidentialité

Note importante : le ton custom et le contexte d'entreprise ne sont PAS modifiables en self-service. Toute modification passe par un échange avec l'équipe pour garantir la qualité des réponses. C'est un choix délibéré qui évite les dégradations de qualité.

### Features secondaires (V2)

- Export CSV/PDF des données pour reporting interne du client
- Graphiques d'évolution temporelle plus poussés
- Comparaison période sur période
- Alertes configurables (ex : "préviens-moi si ma note moyenne baisse en dessous de 4.0")
- Gestion multi-utilisateurs par compte (plusieurs employés d'une même PME)

L'architecture du dashboard doit rester modulable pour permettre d'ajouter facilement de nouvelles métriques ou sections sans refonte.

## 7. Dashboard admin (interne, équipe uniquement)

### Fonctionnalités MVP

- Liste de tous les clients actifs avec statut abonnement et métriques clés
- Page de validation des réponses (mode Pro/Business) avec queue des réponses en attente, triée par ordre chronologique, filtrable par client
- Page de monitoring technique : statut des jobs Celery, erreurs récentes, tokens OAuth en alerte, publications en échec
- Alertes critiques : polling échoué pour un client depuis X heures, token expiré non réautorisé depuis 48h, taux d'erreur anormal

### Features secondaires (V2)

- CRM de démarchage : tracking des prospects, rendez-vous planifiés, historique des interactions
- Analytics business avancées
- Gestion multi-admin (si une équipe rejoint le projet)
- Outils de support client intégrés

Le dashboard admin reste minimaliste au MVP pour ne pas se disperser. L'objectif est de pouvoir opérer 20 clients sans friction, pas de construire un outil entreprise.

## 8. Notifications et communication avec le client

Chaque client choisit un canal de contact principal depuis son dashboard parmi : email, Telegram, SMS (SMS réservé au plan Business et livré en V2 car coût par message non-négligeable).

Les notifications sont contextuelles, avec un template spécifique pour chaque situation :
- Nouvelle réponse générée en attente de validation (mode suggestion)
- Réponse publiée avec succès
- Avis filtré par regex (mot banni détecté)
- Avis en validation humaine obligatoire (note 1-3 étoiles)
- Token OAuth expiré, réautorisation nécessaire
- Échec de publication après 3 retries
- Seuil de quota mensuel atteint (80%, 100%)
- Rapport hebdomadaire optionnel

Les canaux et préférences sont stockés dans le profil client et respectés à chaque envoi.

## 9. Conformité et sécurité

### RGPD

- Hébergement des données en UE (VPS Oracle, backups Cloudflare R2 EU)
- DPA (Data Processing Agreement) proposé aux clients, accessible depuis le dashboard, signé au moment de l'inscription
- Droit à l'oubli : suppression complète des données sous 30 jours après résiliation
- Droit d'accès : export des données sur demande
- Les avis Google contiennent des noms de personnes physiques, donc le SaaS est sous-traitant de données pour le compte des clients

### OAuth et secrets

- Tokens OAuth Google chiffrés au repos dans la base de données (chiffrement applicatif avec clé dans variables d'environnement)
- Jamais de token en clair dans les logs
- Rotation possible des refresh tokens via l'interface client
- HTTPS obligatoire partout (Caddy + Let's Encrypt)

### Validation OAuth Google (point critique pré-lancement)

**Étape obligatoire avant le lancement public** : Google exige une validation OAuth ("OAuth App Verification") pour toute application accédant à Google Business Profile API au-delà d'un nombre limité d'utilisateurs (autour de 100 utilisateurs en dev mode). Le processus de vérification par Google prend 2 à 6 semaines et inclut :
- Review de la homepage et des Terms of Service
- Vérification du logo et du branding
- Démo vidéo du produit
- Validation du domaine
- Justification de l'utilisation des scopes demandés

Cette étape doit être initiée dès que possible dans le développement pour ne pas bloquer le lancement. Les premiers utilisateurs (bêta) peuvent utiliser le service en dev mode en étant ajoutés manuellement comme utilisateurs de test, en attendant la validation.

## 10. Principes d'architecture

L'architecture suit ces principes directeurs :

**Modularité** — Chaque fonctionnalité (génération de réponse, filtrage regex, notification, publication) est un module indépendant avec une interface claire. Ajouter un nouveau type de notification ou un nouveau critère de filtrage ne doit pas nécessiter de refonte.

**Orientation objet** — Modèles métier clairs (Client, Location, Review, Response, NotificationChannel, etc.), services métier qui orchestrent, repositories qui encapsulent l'accès DB.

**Découplage via queue** — La queue Celery découple les phases (ingestion, traitement, publication) pour que chaque étape puisse échouer et retry indépendamment, sans perdre le travail des autres.

**Configurabilité** — Tout ce qui concerne le client (délais, horaires, canal de notification, filtres regex, options de réponse) est configurable depuis son dashboard. Pas de magic numbers dans le code.

**Monitoring dès le départ** — Chaque action importante (nouvelle réponse générée, publication, échec) est loggée de façon structurée pour faciliter le debug et les métriques.

**Simplicité au MVP** — Tout ce qui n'est pas critique au lancement est documenté dans les features V2 mais n'est pas implémenté. Le MVP doit être shippable en 2-3 mois solo.

## 11. Points d'attention et features V2

Points identifiés pour amélioration future, à ne pas traiter au MVP :

- Gestion des avis modifiés après réponse (détection + re-réponse)
- Canal SMS pour les notifications (coûts de message à intégrer)
- Export de données CSV/PDF pour clients
- CRM de démarchage intégré au dashboard admin
- Multi-utilisateurs par compte client
- Webhooks Google si l'API les supporte un jour
- Intégration de services annexes (Trustpilot, TripAdvisor, Pages Jaunes avis) pour une gestion multi-plateformes
- Analytics avancées et recommandations IA proactives (ex : "vos avis négatifs mentionnent souvent le temps d'attente, voici des pistes")
- Mode agence / white-label pour que des consultants SEO local puissent revendre le service
- Suggestion de réponses proactives aux avis anciens non-répondus (opt-in uniquement)

## 12. Ce dont j'ai besoin d'aide

Architecture technique détaillée (structure du code Python, organisation FastAPI, schéma de base de données, design des modèles), implémentation OAuth Google Business Profile, intégration Celery + Redis, configuration Caddy et déploiement VPS, rédaction du frontend Next.js (dashboard client et dashboard admin), intégration Lemon Squeezy, design des prompts Claude pour la génération de réponses, nomenclature du JSON de réponse IA, structure des notifications multi-canal, gestion des migrations Alembic, stratégie de tests (unitaires, intégration, end-to-end), rédaction des documents légaux (Terms, DPA, privacy policy), préparation de la validation OAuth Google, conseil go-to-market et pricing.
