# 🖥️ Application de bureau + 💡 LEDs de statut

## L'application (une seule commande)

```powershell
cd C:\workshop\SENTINEL-X
git pull origin main
.\make.bat install     # une fois (installe pywebview)
.\make.bat app
```

`make app` démarre **tout en arrière-plan** (broker MQTT, API, ingestion,
détection IA, webcam) **sans ouvrir de terminal**, puis affiche une **fenêtre
d'application** : le **Cockpit**.

### Ce que montre le Cockpit
- **Analyse de connectivité en direct** (rafraîchie toutes les 3 s) : API, Broker
  MQTT, ESP32/capteurs, Webcam, Détection IA, Ollama, **Mistral**. Vert = connecté.
- Un **aperçu webcam live** en haut à droite (flux annoté YOLO).
- Un bouton **« Tester l'IA (Mistral) »** qui interroge réellement le modèle et
  affiche sa réponse → prouve que l'IA fonctionne.
- Des onglets **Alertes / Capteurs / Caméra / Sécurité** affichés **dans l'app**.

Fermer la fenêtre arrête tout proprement. Forcer l'arrêt : `.\make.bat stop`.

> Repli : si la fenêtre native ne se charge pas (runtime WebView2 absent), l'app
> ouvre automatiquement le cockpit dans le navigateur. `.\make.bat start` fait
> directement la version navigateur.

## Les LEDs de statut (ESP32)

Câblage : **Vert → D26**, **Orange → D14**, **Rouge → D13**.

| LED | État |
|---|---|
| 🟢 Vert (D26) | Tout va bien : WiFi + MQTT connectés, aucune alerte |
| 🟠 Orange (D14) | Avertissement récent **ou** déconnecté (état au démarrage) |
| 🔴 Rouge (D13) | Alerte **critique** reçue du serveur |

Le serveur envoie la gravité (`severity`) avec chaque alerte : la LED rouge
s'allume sur une alerte `CRITICAL`, l'orange sur un `WARNING`.

### Activer les LEDs (flash du firmware)
```powershell
pio run -e esp32dev-full -t upload       # secrets + HMAC + OLED-alertes + LEDs
# ou LEDs seules :
pio run -e esp32dev-secrets-leds -t upload
```

> Pour que les alertes atteignent l'OLED et les LEDs, mettre `ALERT_MQTT_ENABLED=true`
> dans le `.env` du PC (la détection publie alors sur le topic `sentinel/alerts`).
