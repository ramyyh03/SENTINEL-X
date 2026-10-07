# 🪟 Installation SENTINEL-X — Nouveau PC Windows (de zéro)

Guide complet pour installer **tout** sur une machine Windows vierge, y compris
l'IA locale Ollama. Suis les étapes dans l'ordre.

---

## 1. Logiciels de base (à installer une seule fois)

Le plus simple : installer le gestionnaire de paquets **winget** (déjà présent
sur Windows 10/11 récents) puis tout tirer en ligne de commande.
Ouvre **PowerShell en administrateur** et lance :

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e          # IMPORTANT : 3.12, PAS 3.14
winget install --id Docker.DockerDesktop -e        # broker MQTT (Mosquitto)
winget install --id Ollama.Ollama -e               # IA locale (chat + audit)
winget install --id Nmap.Nmap -e                   # (pentest croisé, optionnel)
```

> ⚠️ **Ferme et rouvre PowerShell** après ces installations (pour recharger le PATH).
> ⚠️ **Python 3.12 obligatoire** : en 3.14 il n'existe pas encore de wheels pour
> `torch` / `ultralytics` / `scikit-learn` → l'install échoue.

### Vérifier que tout répond

```powershell
git --version
py -3.12 --version
docker --version
ollama --version
```

---

## 2. Pré-requis Docker (une fois, sinon le broker MQTT ne démarre pas)

Docker Desktop a besoin de WSL2. En PowerShell **admin** :

```powershell
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
```

Puis **redémarre le PC**, et après redémarrage :

```powershell
wsl --update
```

Enfin, **lance Docker Desktop** (icône) et attends qu'il affiche « Engine running ».

---

## 3. Récupérer le projet

```powershell
cd C:\
mkdir workshop
cd workshop
git clone https://github.com/ramyyh03/SENTINEL-X.git
cd SENTINEL-X\sentinel-x-ia
```

---

## 4. Installer Python + tous les modules du projet

```powershell
py -3.12 -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r requirements.txt
```

> Ceci installe TOUT : vision (`opencv`, `ultralytics`), ML (`scikit-learn`,
> `pandas`, `numpy`, `scipy`, `pyod`), MQTT (`paho-mqtt`), API (`flask`),
> série (`pyserial`), 2FA (`pyotp`, `qrcode`), sécurité (`python-dotenv`,
> `requests`), et les tests (`pytest`).

Raccourci équivalent (fait le venv + l'install pour toi) :

```powershell
.\make.bat install
```

> 🛡️ Si `torch`/`ultralytics` est bloqué par **Smart App Control** (erreur sur
> `_C.pyd`) : Paramètres Windows → « Smart App Control » → **Désactiver**, puis
> relance l'install.

---

## 5. Télécharger le modèle IA Ollama (Mistral)

```powershell
ollama serve      # démarre le service (laisse cette fenêtre ouverte)
```

Dans une **autre** fenêtre PowerShell :

```powershell
ollama pull mistral      # télécharge le modèle (~4 Go, une seule fois)
ollama list               # vérifie qu'il apparaît
```

> Test rapide : `ollama run mistral "dis bonjour"`

---

## 6. Configuration locale (.env)

```powershell
copy .env.example .env
notepad .env
```

Dans `.env`, pour que le **jury / les collègues** accèdent au dashboard via le
hotspot, mets :

```
API_HOST=0.0.0.0
```

> (`127.0.0.1` = accès local seulement ; `0.0.0.0` = visible sur le hotspot.)

---

## 7. Lancer le système

```powershell
.\make.bat run-all
```

Dashboard : **http://localhost:3000/dashboard**
Depuis un autre PC sur le même hotspot : **http://<IP_DE_CE_PC>:3000/dashboard**
(trouve l'IP avec `ipconfig`).

---

## 8. Première configuration (comptes + ESP32)

```powershell
.\make.bat setup-2fa        # crée ton compte dashboard (login + 2FA Authenticator)
.\make.bat config-esp32     # prépare secrets.h de l'ESP32 (détecte l'IP du PC)
.\make.bat security-audit   # « suis-je sécurisé ? » (vérifie nos failles)
```

Pour flasher l'ESP32 (si PlatformIO installé) : env `esp32dev-secrets`.

---

## 9. Réseau : utiliser le hotspot, PAS eduroam

Le Wi-Fi du campus (eduroam) isole les clients entre eux et bloque l'ESP32.
Utilise un **partage de connexion téléphone** (hotspot). Le PC, l'ESP32 et les
collègues doivent être sur **le même hotspot**.

---

## 10. Dépannage express

| Problème | Solution |
|---|---|
| `git` / `python` non reconnu | Ferme/rouvre PowerShell (PATH) |
| install pip échoue (torch/sklearn) | Vérifie `py -3.12` (pas 3.14) |
| `_C.pyd` bloqué | Désactive Smart App Control |
| Docker « VirtualMachinePlatform » | Étape 2 + redémarrage |
| `docker ps` erreur npipe | Lance Docker Desktop, attends « running » |
| dashboard inaccessible d'un autre PC | `API_HOST=0.0.0.0` + même hotspot + `ipconfig` |
| chat IA vide | `ollama serve` + `ollama pull mistral` faits ? |

> 📘 Le token GitHub ne doit **jamais** être écrit dans l'URL du remote.
> Utilise `git clone https://github.com/...` sans identifiants ; Windows
> demandera le login via **Git Credential Manager** (stocké de façon sûre).
