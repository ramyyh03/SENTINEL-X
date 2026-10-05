# Matrice de sécurité — Sentinel-X

## Chiffrement des flux (TLS)
- Broker MQTT Mosquitto configuré en MQTTS sur le port 8883 (MQTT en clair 1883 non ouvert).
- Chaîne de certificats générée avec une CA interne (OpenSSL) : ca.crt, server.crt, server.key.
- tls_version limitée à TLS 1.2 minimum.

## Authentification
- Connexions anonymes interdites (allow_anonymous false).
- Compte sentinel protégé par mot de passe, stocké en empreinte (hash) dans le fichier passwd.

## Durcissement (hardening)
- Fichier de secrets passwd : propriétaire restreint à l'utilisateur mosquitto, droits 0700 (lisible par ce seul service).
- Clés privées (*.key) exclues du dépôt Git via .gitignore : aucun secret en clair dans le code.

## À faire plus tard
- Capture Wireshark prouvant le chiffrement du port 8883 (sur le vrai réseau d'équipe).
