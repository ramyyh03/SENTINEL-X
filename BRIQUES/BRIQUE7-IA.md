# BRIQUE 7 : API de réception des alertes

> **SENTINEL-X — Workshop EPSI BAC+4**
> Serveur **Flask** (port 3000) qui reçoit, valide, stocke et affiche les alertes Vision + Prédictif.

---

## 🎯 Ce que fait le serveur

C'est le **point de collecte** de tout SENTINEL-X : les Briques 5 (Vision) et 6 (Prédictif) **POSTent** leurs alertes ici ; le serveur les **valide**, les **stocke** dans `data/sentinel.db` (table `alerts`) et les **affiche** sur un dashboard auto-rafraîchi.

```
Brique 5 (Vision) ┐
                  ├── POST /api/v1/alerts ──► [API Flask] ──► SQLite (table alerts) ──► GET /dashboard
Brique 6 (Prédictif) ┘                          (valide + rate limit + log IP)
```

---

## 🔌 Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/api/v1/alerts` | Reçoit une alerte (JSON). `201` si OK, `400` si invalide, `415` si mauvais Content-Type, `429` si rate limit |
| `GET` | `/dashboard` | Page HTML : 50 dernières alertes, code couleur par sévérité, auto-refresh 5 s |
| `GET` | `/live` | Mesures capteurs EN DIRECT (temp/humidité/gaz/présence), auto-refresh 3 s |
| `GET` | `/health` | `{"status":"ok","alerts_count":N,"uptime":"..."}` |

### Exemples `curl`

```bash
# Alerte valide (format immuable) → 201
curl -X POST http://localhost:3000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"source":"ia_vision","type":"intrusion_detected","confidence":0.91,
       "timestamp":"2026-10-06T10:00:00Z","details":{"persons_detected":1}}'

# État du serveur
curl http://localhost:3000/health

# Alerte invalide (champ manquant) → 400 avec le détail des erreurs
curl -X POST http://localhost:3000/api/v1/alerts \
  -H "Content-Type: application/json" -d '{"source":"ia_vision"}'
```

Dashboard : ouvrir **http://localhost:3000/dashboard** dans un navigateur.

---

## 🏃 Lancer / arrêter

```bash
make api        # lance le serveur en arrière-plan (→ http://localhost:3000/dashboard)
make api-logs   # suit les logs en direct
make api-stop   # arrête le serveur
make run        # lance l'API + l'abonné MQTT (système complet)
```

> 🪟 **Windows** (sans `make`) :
> ```powershell
> venv\Scripts\python -m api.server        # démarre l'API (Ctrl+C pour arrêter)
> ```

---

## 🧪 Tester SANS les Briques 5/6

Le serveur est **indépendant** : on peut l'alimenter à la main avec `curl` (exemples ci-dessus) ou l'inclure dans le healthcheck global :

```bash
make test       # teste l'API (POST valide/invalide + /health) parmi les 9 contrôles
```

Pour voir la **chaîne réelle** : lancer `make api` puis `make detect` (Brique 6) ou `make detect-vision` (Brique 5) → les alertes apparaissent sur le dashboard. *(Validé : 26 alertes Prédictif → reçues et affichées.)*

---

## 🔒 Sécurité — alignement avec le CYBER (pas de doublon)

Le collègue CYBER gère la couche **MQTT** (TLS 8883, auth, certificats — voir `security/SECURITE.md`). L'API est une couche **HTTP distincte** : je n'y duplique donc **rien** du MQTT. J'ajoute uniquement ce qui manquait **côté HTTP** :

| Mesure | Détail |
|---|---|
| Validation stricte | champs obligatoires + types + `confidence ∈ [0,1]` → `400` sinon |
| Content-Type | `application/json` obligatoire → `415` sinon |
| Rate limiting | 100 req/min par IP (en mémoire) → `429` sinon |
| Log des requêtes | chaque requête loggée avec l'**IP source** (`logs/api.log`) |
| Bind local | `127.0.0.1` par défaut (pas exposé sur le LAN sans raison) |

> ⚠️ Le **HTTPS de l'API** reste une tâche **CYBER** (listée dans son « À faire » de `SECURITE.md`). On est en HTTP pour le dev ; je n'ai pas pris cette décision à sa place.

---

## 🛠️ Choix techniques

- **Flask** : micro-framework minimal, idéal pour 3 routes ; cross-plateforme (Windows inclus), zéro dépendance système. Un gros framework (Django) serait disproportionné.
- **Même base `sentinel.db`** que la Brique 6 (table `alerts` séparée de `sensor_data`) : une seule source de vérité, simple à requêter.
- **Dashboard HTML/CSS inline** (pas de framework CSS externe) : aucune dépendance réseau, fonctionne hors-ligne, auto-refresh via `<meta refresh>`.
- **Factory `create_app()`** : permet de tester les endpoints en in-process (`test_client`) sans ouvrir de port → healthcheck rapide et fiable.

---

## 📘 Ce que j'ai fait — Brique 7 (API alertes)

**Ce que le CYBER avait déjà fait et comment je m'y suis aligné :** il a sécurisé toute la couche **MQTT** (broker TLS 8883, authentification, certificats avec SAN, firmware en MQTTS). J'ai d'abord **récupéré et intégré** tout son travail dans `main`, puis j'ai construit l'API **à côté**, sans toucher à sa config ni dupliquer son chiffrement. Le HTTPS de l'API étant dans **son** « à faire », je suis resté en HTTP dev.

**Ce que j'ai ajouté sans dupliquer :** la couche **HTTP** qui manquait — validation du JSON, Content-Type obligatoire, rate limiting par IP, log des requêtes, et un bind local par défaut. Rien de tout ça n'existait ; rien ne recoupe le MQTT.

**Comment les alertes Vision + Prédictif arrivent maintenant jusqu'au dashboard :** les deux IA émettent déjà le **même format JSON** vers `POST /api/v1/alerts`. L'API les valide, les écrit dans la table `alerts`, et `/dashboard` les affiche (50 dernières, code couleur par sévérité, refresh 5 s). La boucle est **bouclée** : capteurs → IA → **API → dashboard**. *(J'ai aussi corrigé au passage un bug où la Brique 6 postait sur `/` au lieu de `/api/v1/alerts` quand le `.env` n'avait que l'URL de base.)*
