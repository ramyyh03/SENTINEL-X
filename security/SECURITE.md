# Matrice de sécurité — Sentinel-X

> Filière CYBER. Décrit l'état réel des mesures de sécurité de la chaîne capteurs → broker MQTT.

## Chiffrement des flux (TLS)
- Broker MQTT Mosquitto en MQTTS sur le port 8883, TLS 1.2 minimum (TLS 1.3 négocié lors des tests).
- Aucun port en clair sur le broker de production : le port 1883 n'est ni écouté ni publié.
- Chaîne de certificats signée par une CA interne (OpenSSL) : ca.crt, server.crt, server.key.
- Le certificat serveur contient l'adresse du broker (champ SAN) : un client refuse la connexion si l'adresse ne correspond pas. Vérifié avec `openssl s_client -verify_ip` (Verify return code: 0).
- Script `security/gen-certs.sh <IP>` : régénère le certificat serveur quand l'IP du PC broker change.

## Firmware ESP32
- Publication en MQTTS (port 8883) : plus aucun flux en clair côté capteur.
- L'ESP32 vérifie l'identité du broker avec le certificat public de la CA (`firmware/include/ca_cert.h`) : signature et adresse.
- Authentification MQTT par identifiant et mot de passe, saisis dans le portail de configuration et stockés dans la flash de la carte, jamais dans le code.
- Portail de configuration protégé par un mot de passe aléatoire propre à chaque carte, affiché sur l'écran OLED : il faut un accès physique pour reconfigurer.

## Authentification du broker
- Connexions anonymes interdites (allow_anonymous false).
- Compte sentinel protégé par mot de passe, stocké en empreinte (hash) dans le fichier passwd.

## Gestion des secrets
- Clés privées (*.key) et fichier passwd exclus du dépôt Git via .gitignore : aucun secret en ligne (historique vérifié).
- Clé privée de la CA rangée dans `security/ca/`, hors du dossier monté dans le conteneur : le broker n'a accès qu'à sa propre clé (moindre privilège).
- Fichier passwd : propriétaire restreint à l'utilisateur mosquitto, droits 0700.

## Limites connues
- Le broker de développement (`docker-compose.dev.yml`, port 1883, anonyme) existe toujours pour le simulateur : à ne jamais lancer sur le réseau de la démo.
- La clé privée de la CA n'est pas protégée par une phrase secrète.
- `.env.example` propose un identifiant et un mot de passe par défaut : à remplacer par des valeurs propres à l'équipe.
- Un seul compte MQTT pour tous les clients : pas encore de séparation des droits.

## À faire
- Valider le firmware MQTTS sur la carte réelle (compilation vérifiée, test matériel à faire).
- Comptes MQTT séparés avec ACL : ESP32 en écriture seule, collecteur en lecture seule.
- Capture Wireshark prouvant le chiffrement du port 8883 (sur le vrai réseau d'équipe).
- Durcissement du serveur hôte : pare-feu (UFW), SSH par clés uniquement, isolation Docker.
- Chiffrement de l'API en HTTPS (à caler avec le DEV).
