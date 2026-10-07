# Matrice de sécurité — Sentinel-X

> Filière CYBER. Décrit l'état **réel** des mesures de sécurité, y compris ce qui n'est pas couvert.
> Mise à jour : 7 octobre 2026.

## Vue d'ensemble

| Mesure | Implémentée | Vérifiée | Active en démo |
|---|---|---|---|
| Dashboard : login + double authentification (TOTP) | oui | oui | oui |
| Dashboard : contenu affiché échappé (anti-XSS) | oui | oui, tests automatiques | oui |
| API : envoi d'alertes réservé au PC serveur | oui | oui, tests automatiques | oui |
| API : blocage des essais de mot de passe | oui | oui, tests automatiques | oui |
| Broker MQTT chiffré et authentifié (MQTTS 8883) | oui | oui, côté broker | **à confirmer** |
| ESP32 en MQTTS avec vérification du broker | oui | compilation seulement | **à confirmer** |
| Aucun secret dans Git | oui | oui, historique complet | oui |
| Dashboard en HTTPS | non | — | non |

« À confirmer » : dépend du test sur la carte réelle (voir `security/DEMO-MQTTS.md`). Tant que ce
test n'est pas passé, la démo tourne avec le broker de développement, en clair.

## Dashboard et API (Flask)
- **Authentification** : identifiant + mot de passe haché (PBKDF2-SHA256) + code TOTP à 6 chiffres. Un compte par personne, créé par l'administrateur.
- **Faille XSS stockée corrigée** : une alerte ou une mesure contenant du HTML était recopiée telle quelle dans `/dashboard` et `/live`. Envoyée sans authentification, elle s'exécutait dans la session de l'administrateur connecté, ce qui contournait le login et la double authentification. Correctif : tout contenu affiché est échappé.
- **Envoi d'alertes** (`POST /api/v1/alerts`) : accepté seulement depuis le PC serveur. Une autre machine est refusée, sauf jeton partagé `API_ALERT_TOKEN` configuré explicitement.
- **Essais de mot de passe** : 5 échecs par adresse, puis blocage de 5 minutes, y compris pour un mot de passe correct.
- **Sans compte configuré** : le dashboard n'est visible que depuis le PC serveur, jamais depuis le réseau.
- **Preuve** : 14 tests automatiques dans `tests/` (`python -m pytest tests -q`).

## Chiffrement MQTT (TLS)
- Broker Mosquitto sécurisé sur le port 8883, TLS 1.2 minimum (TLS 1.3 négocié lors des tests), connexions anonymes interdites, mot de passe stocké haché.
- Chaîne de certificats signée par une CA interne (OpenSSL). Le certificat serveur contient l'adresse du broker (champ SAN) : un client refuse la connexion si l'adresse ne correspond pas. Vérifié avec `openssl s_client -verify_ip` (Verify return code: 0).
- Script `security/gen-certs.sh <IP>` : régénère le certificat serveur quand l'IP du PC broker change.

## Firmware ESP32
Quatre variantes de compilation existent. Seule la variante utilisée détermine le niveau de sécurité.

| Variante | Transport | Authentification | Configuration |
|---|---|---|---|
| `esp32dev` | MQTTS 8883 | compte MQTT | portail Wi-Fi, mot de passe aléatoire par carte |
| `esp32dev-secrets-tls` | MQTTS 8883 | compte MQTT | en dur dans `secrets.h` (ignoré par Git) |
| `esp32dev-secrets` | **clair 1883** | **aucune** | en dur dans `secrets.h` |
| `esp32dev-plain` | **clair 1883** | **aucune** | portail Wi-Fi |

Dans les deux variantes MQTTS, l'ESP32 vérifie l'identité du broker avec le certificat public de la CA (`firmware/include/ca_cert.h`).

## Gestion des secrets
- Exclus de Git et vérifiés absents de tout l'historique : clés privées, fichier `passwd` du broker, `secrets.h`, comptes du dashboard, clé de session, `.env`.
- Clé privée de la CA rangée dans `security/ca/`, hors du dossier monté dans le conteneur : le broker n'a accès qu'à sa propre clé (moindre privilège).

## Limites connues
- **Broker de développement** (port 1883, en clair, anonyme) : s'il est lancé sur le réseau de la démo, tout appareil de ce réseau peut lire les mesures et en injecter de fausses.
- **Pas de HTTPS sur le dashboard** : si l'API est exposée au réseau (`API_HOST=0.0.0.0`), le mot de passe et le code de double authentification circulent en clair sur le Wi-Fi.
- Le blocage des essais de mot de passe et la limite de requêtes sont en mémoire : ils repartent de zéro au redémarrage de l'API.
- Un seul compte MQTT pour tous les clients : pas de séparation des droits.
- La clé privée de la CA n'est pas protégée par une phrase secrète.
- `.env.example` propose un identifiant et un mot de passe MQTT par défaut, à remplacer.
- Le secret TOTP de chaque compte est stocké en clair dans `data/dashboard_users.json` (fichier local, ignoré par Git).

## À faire
- Valider la variante MQTTS sur la carte réelle et l'utiliser en démo (`security/DEMO-MQTTS.md`).
- HTTPS sur le dashboard.
- Comptes MQTT séparés avec ACL : ESP32 en écriture seule, collecteur en lecture seule.
- Capture Wireshark prouvant le chiffrement du port 8883.
- Durcissement du PC serveur : pare-feu limité aux ports utiles.
