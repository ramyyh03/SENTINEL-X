# 🤖 Ollama — diagnostic IA en langage naturel (optionnel, 100% local)

> Ajoute au dashboard un **chat expert** qui explique les anomalies. Gratuit, local, sans cloud.
> Tout marche **sans** Ollama (dégradé) ; l'installer **active** le chat.

## 1. Installer Ollama
- Télécharge sur **https://ollama.ai** (Windows / Mac / Linux).

## 2. Lancer le serveur + le modèle
```bash
ollama serve            # (terminal séparé) démarre le serveur local :11434
ollama pull mistral     # télécharge le modèle Mistral (~4 Go, une fois)
```

## 3. Vérifier
```bash
make ollama-check       # (Windows : .\make.bat ollama-check)
# ou : curl http://localhost:11434/api/tags
```
→ `🟢 Ollama EN LIGNE`.

## 4. Utiliser
Sur **http://localhost:3000/dashboard** :
- l'indicateur passe à **🟢 Ollama en ligne**,
- tape une question (« pourquoi le gaz est haut ? ») → **Demander** → réponse technique.

## Dépannage
| Souci | Solution |
|---|---|
| 🔴 hors ligne | `ollama serve` n'est pas lancé |
| réponse vide | `ollama pull mistral` pas fait |
| port occupé | fermer une autre instance d'Ollama |

> ⚙️ Config (facultative) dans `.env` : `OLLAMA_URL=http://localhost:11434` · `OLLAMA_MODEL=mistral`
