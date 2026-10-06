# 📡 Le broker MQTT — définition, rôle & connexion de l'équipe

> **SENTINEL-X — Workshop EPSI BAC+4** · signé rami yahyaoui

---

## 1. C'est quoi un « broker » ?

Un **broker MQTT** est un **serveur central de messagerie**. Il ne produit ni ne consomme de données lui-même : il **reçoit** des messages de ceux qui **publient** et les **redistribue** à ceux qui **écoutent**.

C'est le modèle **publish / subscribe** (publier / s'abonner) :

```
   ESP32 ──publish──►               ┌──────────────┐  ──►── mqtt_client.py (→ SQLite)
   (capteurs)         "sentinel/    │    BROKER     │
                       sensors"     │  (Mosquitto)  │  ──►── un autre abonné (dashboard, collègue…)
   autre capteur ──►                └──────────────┘  ──►── …
```

- On **publie** sur un **topic** (ici `sentinel/sensors`), pas vers une personne précise.
- Tous ceux **abonnés** à ce topic reçoivent le message, **en même temps**.

## 2. À quoi il sert dans SENTINEL-X (son rôle)

| Sans broker | Avec broker |
|---|---|
| L'ESP32 devrait connaître chaque PC qui veut ses données | L'ESP32 publie **une seule fois** sur le broker |
| Ajouter un collègue = reconfigurer l'ESP32 | Le collègue **s'abonne** au broker, l'ESP32 ne change pas |
| Couplage fort, fragile | **Découplage** : capteurs et consommateurs indépendants |

Concrètement, le broker permet :
- à l'**ESP32** d'envoyer ses mesures (temp/humidité/gaz/présence) **sans savoir qui les lit** ;
- à **plusieurs membres** de l'équipe de **lire les mêmes données en même temps** (abonné Python, dashboard, tests…) ;
- de **découpler** le matériel (capteurs) du logiciel (IA, API) : chacun évolue de son côté.

> En résumé : le broker est le **point de rendez-vous** des données. Les capteurs y **déposent**, tout le monde y **récupère**.

## 3. Les deux brokers du projet

| | DEV | PROD |
|---|---|---|
| Fichier | `docker-compose.dev.yml` | `docker/docker-compose.yml` |
| Port | **1883** (clair) | **8883** (**MQTTS / TLS chiffré**) |
| Auth | anonyme | **user + mot de passe** |
| Certificats | aucun | CA + `server.crt/key` (pôle CYBER) |
| Usage | tests, démo rapide | production / vraie sécurité |
| Lancer | `make broker` | `docker compose -f docker/docker-compose.yml up -d` |

---

## 4. Comment un collègue se connecte au broker

### Prérequis
- Être sur **le même réseau WiFi** que le PC qui héberge le broker.
- Connaître l'**IP du PC-broker** (ex. `192.168.43.45`) — sur ce PC : `ipconfig` (Windows) / `ifconfig` (Mac/Linux).

### a) Depuis un script Python (abonné)
Mettre dans son `.env` :
```ini
# Broker DEV (clair)
MQTT_HOST=192.168.43.45
MQTT_PORT=1883
MQTT_TOPIC=sentinel/sensors
```
Puis :
```bash
python scripts/mqtt_client.py        # reçoit les mesures → SQLite
```

Pour le broker **PROD** (chiffré), ajouter en plus :
```ini
MQTT_PORT=8883
MQTT_USER=sentinel
MQTT_PASSWORD=<mot de passe>
MQTT_CA_CERT=docker/mosquitto/certs/ca.crt
```

### b) Depuis l'ESP32 (publication)
Au **portail de config** (`SENTINEL-X-SETUP`), saisir l'**IP du PC-broker**. L'ESP32 publie alors sur `sentinel/sensors`.

### c) Pour juste observer (debug, n'importe quel PC)
Avec l'outil `mosquitto_sub` (client MQTT en ligne de commande) :
```bash
mosquitto_sub -h 192.168.43.45 -p 1883 -t "sentinel/sensors" -v
```
→ affiche en direct tous les messages publiés.

---

## 5. Le format des messages (topic `sentinel/sensors`)
```json
{"temp": 22.5, "humidity": 45.0, "gas": 150, "presence": 0, "timestamp": "2026-10-06T12:00:00Z"}
```
Tout ce qui publie sur ce topic **doit** respecter ce format (sinon l'abonné rejette le message).

---

## 6. Points d'attention
- **Même réseau obligatoire** : le PC-broker, l'ESP32 et les collègues doivent être sur le **même WiFi** (sinon ils ne se voient pas).
- **Pare-feu** : sur le PC-broker, autoriser le port (1883 ou 8883) en entrée.
- **Isolation du hotspot** : certains partages de connexion téléphone **isolent** les appareils → préférer un vrai routeur WiFi pour la démo.
