# 🔐 Sécurité du dashboard — login + double authentification (2FA)

> **SENTINEL-X** · signé rami yahyaoui · **100 % local** (aucun cloud, aucun compte Microsoft requis)

---

## Le principe
Le dashboard est **en lecture seule** (les visiteurs ne peuvent que regarder). On ajoute :
- un **login** (identifiant + mot de passe haché),
- une **double authentification (2FA)** via une app **Authenticator** (Microsoft Authenticator, Google Authenticator…) — un code à 6 chiffres qui change toutes les 30 s (standard **TOTP**).

**L'admin décide qui a accès** : il crée un compte par personne. Tant qu'**aucun** compte n'existe, le dashboard n'est consultable que **depuis le PC serveur lui-même** (pour ne pas se verrouiller dehors) et il est **refusé depuis le réseau** ; **dès le 1er compte créé, le login devient obligatoire** pour tout le monde.

---

## 1. L'admin crée un compte (pour soi et pour chaque personne autorisée)
```bash
make setup-2fa                 # (Windows : .\make.bat setup-2fa)
# → demande un identifiant + un mot de passe
# → affiche un QR code dans le terminal
```
La personne **scanne le QR** dans **Microsoft Authenticator** (Ajouter un compte → Autre compte → scanner). Un code à 6 chiffres apparaît alors dans l'app.

> 🔁 Refais `make setup-2fa` pour **chaque** personne à qui tu donnes accès (un compte chacun).

## 2. Lancer le serveur
```bash
make api            # ou make run-all
```

## 3. Se connecter
Ouvrir **http://\<IP-du-PC\>:3000/login** et saisir :
- identifiant + mot de passe,
- le **code à 6 chiffres** de l'app Authenticator.

→ Accès au dashboard / capteurs / caméra. Bouton **« déconnexion »** en haut.

---

## Ce qui est protégé
| Route | Protégée ? |
|---|---|
| `/dashboard`, `/live`, `/camera` | ✅ login + 2FA requis |
| `/health` | ❌ ouvert (supervision) |
| `POST /api/v1/alerts` | ✅ réservé au PC serveur (les IA postent depuis le PC) ; depuis une autre machine : refusé, sauf jeton `API_ALERT_TOKEN` (en-tête `X-Sentinel-Token`) |
| `POST /login` | ✅ blocage temporaire après 5 échecs par adresse (5 min) |

> Tout ce qui est affiché (alertes, mesures) est **échappé** : un contenu piégé s'affiche comme du texte et n'est jamais exécuté (anti-XSS, tests dans `tests/`).

## Fichiers (jamais dans Git)
- `data/dashboard_users.json` — comptes (mot de passe **haché** + secret TOTP). Gitignoré.
- `data/.flask_secret` — clé de session. Gitignoré.

## Bonnes pratiques
- **Exposer sur le réseau** : `API_HOST=0.0.0.0` dans `.env` + autoriser le port 3000 au pare-feu.
- **Sauvegarde** : garde `data/dashboard_users.json` à l'abri ; sa perte = recréer les comptes.
- **Révoquer un accès** : supprimer l'utilisateur du fichier `data/dashboard_users.json`.

---

## Et le « vrai » max sécurité (Microsoft Entra ID + MFA cloud) ?
C'est la **phase B** (évoquée) : SSO Microsoft + gestion des accès depuis l'admin Entra.
Elle nécessite d'**héberger le dashboard en HTTPS** (hors laptop) + un **tenant Microsoft**.
La solution ci-dessus (login + 2FA TOTP local) couvre déjà l'essentiel **sans cloud**.
