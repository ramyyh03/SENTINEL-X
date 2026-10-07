# Démo en MQTT chiffré (MQTTS) — mode d'emploi

> Filière CYBER. Remplace le broker de dev (port 1883, en clair, anonyme) par le broker
> sécurisé (port 8883, TLS + mot de passe) pour la démo. Durée : 20 à 30 minutes à deux.

**Pourquoi** : le jury se connecte au même partage de connexion que nous. Avec le broker
de dev, n'importe quel appareil de ce réseau peut lire les mesures ou en injecter de fausses.

## 1. Sur le PC qui détient la CA (CYBER)

```bash
bash security/gen-certs.sh 192.168.43.45      # l'IP du PC serveur sur le partage de connexion
git add docker/mosquitto/certs/server.crt
git commit -m "chore(security): certificat serveur pour le PC de demo"
git push origin feature-security
```

Copier ensuite **`docker/mosquitto/certs/server.key`** sur une clé USB. Cette clé privée ne
passe ni par Git ni par une messagerie. `security/ca/ca.key` ne quitte jamais ce PC.

## 2. Sur le PC serveur (PowerShell, à la racine du projet)

```powershell
git pull
# copier server.key depuis la clé USB vers docker\mosquitto\certs\
```

Créer le compte MQTT (demande le mot de passe deux fois, rien ne s'affiche) :

```powershell
docker run --rm -it -v "${PWD}\docker\mosquitto\config:/mosquitto/config" eclipse-mosquitto:2 mosquitto_passwd -c /mosquitto/config/passwd sentinel
```

Dans `.env` :

```ini
MQTT_HOST=localhost
MQTT_PORT=8883
MQTT_USER=sentinel
MQTT_PASSWORD=<le mot de passe choisi>
MQTT_CA_CERT=docker/mosquitto/certs/ca.crt
```

## 3. ESP32

Dans `firmware/include/secrets.h`, ajouter sous les lignes existantes :

```c
#define MQTT_USER     "sentinel"
#define MQTT_PASSWORD "<le mot de passe choisi>"
```

Puis téléverser la variante chiffrée :

```powershell
cd firmware
..\venv\Scripts\python -m platformio run -e esp32dev-secrets-tls -t upload
cd ..
```

## 4. Lancer et vérifier

```powershell
.\make.bat run-all-secure
venv\Scripts\python scripts\esp32_monitor.py --seconds 30
```

Attendu sur le port série : `MQTTS connecte (TLS + authentification)`, puis les mesures dans `/live`.

Pare-feu Windows : autoriser le port **8883** en entrée (PowerShell administrateur) :

```powershell
New-NetFirewallRule -DisplayName "Sentinel MQTTS 8883" -Direction Inbound -Protocol TCP -LocalPort 8883 -Action Allow
```

## 5. Si ça ne se connecte pas

Le port série affiche `MQTTS : echec (state=N)` :

| state | Cause probable | Quoi faire |
|---|---|---|
| `-2` | Broker injoignable ou certificat refusé | Vérifier l'IP du PC (`ipconfig`), le pare-feu 8883, et que le certificat est émis pour cette IP (refaire l'étape 1 si l'IP a changé) |
| `4` ou `5` | Identifiant ou mot de passe refusé | `secrets.h` et le compte créé à l'étape 2 doivent être identiques |

Journal du broker : `docker logs sentinel-mosquitto --tail 20`.

## 6. Retour arrière (si le temps manque)

```powershell
cd firmware
..\venv\Scripts\python -m platformio run -e esp32dev-secrets -t upload
cd ..
.\make.bat run-all
```

Remettre `MQTT_PORT=1883` dans `.env`. Dans ce cas, dire au jury que le chiffrement est
implémenté mais non activé en démo, et ne pas affirmer le contraire dans les slides.
