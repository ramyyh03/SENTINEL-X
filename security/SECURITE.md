# Matrice de sécurité — Sentinel-X

> Filière CYBER. Décrit l'état réel des mesures de sécurité du broker MQTT.

## Chiffrement des flux (TLS)
- Broker MQTT Mosquitto configuré en MQTTS sur le port 8883.
- Chaîne de certificats générée avec une CA interne (OpenSSL) : ca.crt, server.crt, server.key.
- tls_version limitée à TLS 1.2 minimum.

## Authentification
- Connexions anonymes interdites (allow_anonymous false).
- Compte sentinel protégé par mot de passe, stocké en empreinte (hash) dans le fichier passwd.

## Durcissement (hardening)
- Fichier de secrets passwd : propriétaire restreint à l'utilisateur mosquitto, droits 0700 (lisible par ce seul service). Correctif appliqué et vérifié (plus aucun warning au démarrage).
- Clés privées (*.key) et fichier passwd exclus du dépôt Git via .gitignore : aucun secret en clair en ligne (vérifié sur GitHub).

## Emplacement dans le dépôt
- Broker intégré dans la structure de l'équipe : docker/docker-compose.yml, docker/mosquitto/config/, docker/mosquitto/certs/.

## À faire
- Fermer le port 1883 (MQTT en clair) pour la démo finale : décision à valider avec l'INFRA.
- Capture Wireshark prouvant le chiffrement du port 8883 (sur le vrai réseau d'équipe).
- Durcissement du serveur hôte : pare-feu (UFW), SSH par clés uniquement, isolation Docker.
- Chiffrement de l'API en HTTPS (à caler avec le DEV).
