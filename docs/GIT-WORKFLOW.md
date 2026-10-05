# 🔐 Git Workflow — SENTINEL-X

> Repo : `https://github.com/ramyyh03/SENTINEL-X`
> Dossier local : `~/SENTINEL-X/sentinel-x-ia/`

---

## Règles d'Or

✅ **DO** :
- Pousser **seulement** sur ta branche `feature-*`
- Faire des commits clairs : `"BRIQUE X: description"`
- Vérifier `git status` avant de pousser
- Pousser **après** chaque brique terminée

❌ **DON'T** :
- Jamais pousser sur `main` (c'est protégé)
- Jamais merger sans review
- Jamais modifier le code des autres
- Jamais committer un `.env` réel

---

## Branches par personne

| Branche | Usage |
|---|---|
| `feature-vision` | Vision YOLOv8 |
| `feature-predictive` | Isolation Forest |
| `feature-docker` | Docker MQTT |
| `feature-mqtt` | MQTT Client |
| `feature-security` | CYBER (pas pour l'IA) |

---

## Workflow complet (ex. Mardi = BRIQUE 5 Vision)

### 1. Créer / vérifier la branche
```bash
cd ~/SENTINEL-X/sentinel-x-ia
git checkout feature-vision
git status          # → On branch feature-vision
```

### 2. Coder la brique
Tu codes normalement (Claude Code génère les fichiers).

### 3. Vérifier ce qu'on va pousser
```bash
git status                       # fichiers modifiés/créés
git diff scripts/vision_yolo.py  # changements (optionnel)
```

### 4. Ajouter les fichiers
```bash
git add scripts/vision_yolo.py scripts/utils_vision.py
# ou pour tout ajouter :
git add .
```

### 5. Faire un commit
```bash
git commit -m "BRIQUE 5: YOLOv8 detection with mock MQTT data"
```
Format du message :
- `"BRIQUE X: description courte"`
- Une seule ligne
- Français OK

### 6. Vérifier avant de pousser
```bash
git log --oneline -3   # tes 3 derniers commits
git status             # doit être clean
```

### 7. Pousser sur GitHub
```bash
git push origin feature-vision
# → * [new branch]  feature-vision -> feature-vision
```

### 8. Vérifier sur GitHub.com
Va sur https://github.com/ramyyh03/SENTINEL-X :
- Vérifie que ta branche est listée (`feature-vision`)
- Clique dessus, vois tes commits

---

## Troubleshooting

**Q : « fatal: Could not read from remote repository »**
→ Le token est peut-être expiré. Régénère-le et mets à jour `~/.github-token`, puis relance la config du remote (voir Annexe).

**Q : « Permission denied » / 403**
→ Vérifie le remote : `git remote -v`
   Doit pointer sur `github.com/ramyyh03/SENTINEL-X.git`. Vérifie que le token a le scope `repo`.

**Q : « Updates were rejected » (non-fast-forward)**
→ Quelqu'un a poussé avant toi. Fais `git pull --rebase origin feature-vision` puis repousse.

**Q : Je veux annuler le dernier commit**
→ `git reset --soft HEAD~1` (les fichiers restent, seul le commit disparaît).

---

## Questions avant de pousser

Avant chaque `git push`, demande-toi :
- ☐ Je suis sur la bonne branche ? (`git status`)
- ☐ J'ai tout committé ? (`git status` = clean)
- ☐ Mon code tourne ? (j'ai testé en `--simulate` ?)
- ☐ Je ne modifie que **mes** fichiers ? (`scripts/vision_*.py`, pas autre chose)
- ☐ J'ai pas committé `.env` ou un secret ? (check `.gitignore`)

Si tout est ✅ → `git push origin feature-*`

---

## Mercredi : merge dans `main`

**Tu pousses, tu ne merges pas.** Le·la responsable projet va :
1. Voir la branche `feature-vision` sur GitHub
2. Créer une Pull Request
3. Reviewer le code
4. Merger dans `main` (si OK)

---

## Annexe — Configurer l'authentification par token (une seule fois)

> ⚠️ Cette méthode écrit le token **en clair** dans `.git/config`. Pratique pour un workshop court, mais à ne pas réutiliser sur une machine partagée. Voir plus bas pour l'alternative sécurisée.

```bash
TOKEN=$(cat ~/.github-token)
cd ~/SENTINEL-X/sentinel-x-ia
git remote set-url origin "https://ramyyh03:$TOKEN@github.com/ramyyh03/SENTINEL-X.git"
git remote -v   # le token apparaît dans l'URL — ne pas partager cette sortie
```

### Alternative plus sûre (recommandée hors workshop)
Garder l'URL **sans** token et laisser le gestionnaire d'identifiants macOS stocker le token :
```bash
git config --global credential.helper osxkeychain
# L'URL reste : https://github.com/ramyyh03/SENTINEL-X.git
# Au premier push, saisir : user = ramyyh03, password = <le token>
```
Ou, si `gh` est installé : `gh auth login` (gère tout automatiquement, rien en clair dans le repo).
