# AIMarket Playground

[English](../README.md) · [Русский](README.ru.md) · [Español](README.es.md) · **Français** · [中文](README.zh.md) · [Glossaire](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)

Un accès sans configuration à un parcours réel : **invocation GAIA → vérification Metis → reçu Hub signé**.

## Objectif

Le Playground exécute un seul workflow de l’allowlist. Il n’exécute aucun code arbitraire envoyé par
le navigateur. Le panneau de code explique le parcours HTTP réel tandis que le serveur effectue une
requête délimitée sans exposer les secrets d’infrastructure au navigateur.

```text
navigateur → AIMarket Playground → Hub → GAIA → Metis → reçu vérifié → Alien Monitor
```

GAIA renvoie une lecture LIVE. Le reçu est vérifié avec Ed25519 et la clé publique du Hub d’origine ;
la seule présence de `signature` ne constitue pas une vérification. La lecture et le reçu vérifié
apparaissent d’abord ; Metis poursuit la vérification de manière asynchrone avec un minuteur visible.
Si Metis est indisponible, le résultat affiche honnêtement `PARTIAL`, jamais un faux `VERIFIED`.
Par défaut, Playground envoie à Metis une tâche explicite de cohérence interne via la route `fast` ;
`/v1/verify` exécute toujours un vérificateur réel. Le Council/MoA complet n’est pas utilisé pour une lecture
ordinaire. Une réponse sans `verify_performed: true` est affichée comme **non contrôlée**, jamais
comme un véritable verdict à score nul ; un déploiement ancien ou mal configuré échoue en mode fermé.
Le flag `verified` de Metis signifie que sa propre évaluation a passé le vérificateur, et non que la
lecture GAIA a automatiquement réussi le contrôle de plausibilité. Playground affiche `VERIFIED`
uniquement si cette évaluation contient `VERDICT: plausible` et si le reçu Hub est vérifié ; une
évaluation non plausible ou non structurée reste `PARTIAL`.
Pour un Metis de production authentifié, définissez `PLAYGROUND_METIS_KEY` uniquement côté serveur ; le navigateur ne le reçoit jamais.
La limite serveur de Metis est de 600 secondes, la limite externe de Playground de 620
secondes et le budget total de 640 secondes. Chaque type de fin est affiché séparément.

## Exécution locale

```bash
uv sync --extra dev
uv run pytest
uv run uvicorn playground.app:app --host 127.0.0.1 --port 8075
```

Ouvrez <http://127.0.0.1:8075/?lang=fr>.

## Docker

```bash
docker compose up --build
```

Compose publie le port uniquement sur `127.0.0.1`, utilise un filesystem en lecture seule, supprime
les Linux capabilities, limite les processus, ajoute un health check et active `no-new-privileges`.
Un déploiement public exige un reverse proxy HTTPS avec rate limit externe.

## Configuration et sécurité

Partez de `.env.example`. Les URL de Hub, GAIA et Metis doivent utiliser HTTPS par défaut.
`PLAYGROUND_EVENT_URL` exige `PLAYGROUND_EVENT_TOKEN`. Les variables `PLAYGROUND_MAX_*` délimitent
l’usage, la concurrence, les réponses upstream et l’historique. Les limites s’appliquent au visiteur
pseudonyme et à la source réseau : changer le browser visitor ID ne contourne pas la protection du
budget. Le reçu vérifié cryptographiquement doit aussi correspondre au `product_id`, au
`capability_id` et à une invocation réussie.

## Limite du produit

Use Cases Portal présente les possibilités et la carte de l’écosystème. Le Playground active un
développeur avec une invocation réelle. `create-aimarket-agent` crée un dépôt sous son contrôle.
Le générateur s’exécute actuellement depuis les sources du monorepo et n’est pas encore publié sur
PyPI ; la commande courte `uvx create-aimarket-agent ...` fonctionnera après la publication. Ce sont
des étapes reliées, pas des portails en double.

Les termes `lecture`, `reçu`, `vérification` et `rails` suivent le glossaire canonique. Les marques,
le code, les identifiants, les commandes CLI, les env vars, les URL, `LIVE` et `SIM` ne sont pas traduits.

## Licence

MIT — voir [LICENSE](../LICENSE).
