# BRIQUE 5 : Vision IA — Détection d'intrusion (YOLOv8n)

> **SENTINEL-X — Workshop EPSI BAC+4**
> Détection de **personnes** sur le flux webcam → alerte `intrusion_detected` vers l'API.

---

## 🎯 Ce que fait le module

`vision/detector.py` capture le flux webcam (640×480), détecte les personnes avec
**YOLOv8n**, et émet une **alerte JSON** (format SENTINEL-X) vers l'API dès qu'au
moins une personne est repérée.

```
webcam (640×480) ──► YOLOv8n ──► filtre "person" (conf ≥ 0.50) ──► alerte JSON ──► POST API
        │                                                                  anti-spam 5 s
        └── pas de webcam ? → MODE SIMULATION automatique (frames synthétiques)
```

Format d'alerte (**immuable**) :
```json
{
  "source": "ia_vision",
  "type": "intrusion_detected",
  "confidence": 0.91,
  "timestamp": "2026-10-06T08:38:19Z",
  "details": {
    "persons_detected": 2,
    "max_confidence": 0.91,
    "bounding_boxes": [[0.1, 0.2, 0.3, 0.8], [0.5, 0.1, 0.7, 0.9]]
  }
}
```
> `bounding_boxes` = coordonnées **normalisées** `[x1, y1, x2, y2]` dans `[0,1]` (indépendantes de la résolution).

---

## 🏃 Commandes de test

```bash
make detect-vision        # webcam réelle
make detect-vision-sim    # SANS webcam (frames synthétiques) — pour tester le pipeline
make detect-vision-show   # avec fenêtre OpenCV (debug visuel)
```

Options directes :
```bash
python -m vision.detector --simulate --frames 5   # borne à 5 frames (test rapide)
python -m vision.detector --show                  # affichage debug
python -m vision.detector --api http://IP:3000/api/v1/alerts
```

> Au **1er lancement**, `ultralytics` télécharge `yolov8n.pt` (~6 Mo) automatiquement (non commité, gitignoré).

---

## 📊 Métriques attendues

| Métrique | Valeur | Mesuré ici |
|---|---|---|
| Latence par frame (après warmup) | **< 100 ms** | ~21 ms (CPU, Apple Silicon) |
| Seuil de confiance | **≥ 0.50** | configurable |
| Anti-spam | 1 alerte / **5 s** max | ✅ |
| Classe détectée | `person` (COCO id 0) | ✅ |

> La **1ʳᵉ inférence** est lente (~1.5 s : allocation mémoire / JIT) → un *warmup* est fait au chargement pour que la latence mesurée en boucle soit réaliste.

---

## 🍎 Compatibilité macOS

- **Permissions caméra (TCC)** : au 1er accès, macOS demande l'autorisation. En cas de refus, un message clair invite à : *Réglages → Confidentialité & sécurité → Caméra → autoriser le Terminal*. Sans accès, le module bascule **automatiquement en simulation**.
- **Pas de `cv2.imshow()` par défaut** (peut bloquer en headless) — l'affichage n'est activé qu'avec `--show`.

---

## ⚠️ Limites connues

- **Faux positifs** possibles sur reflets, affiches/photos de personnes, mannequins.
- **Luminosité faible** : la détection chute dans le noir (YOLO entraîné sur images éclairées) → prévoir un éclairage minimal.
- **Mode simulation** : les rectangles colorés ne sont PAS détectés comme des personnes (normal) — la simulation valide le *pipeline* (capture → inférence → alerte), pas la précision de détection. Pour tester une vraie alerte : se placer devant la webcam.
- YOLOv8n (nano) privilégie la **vitesse** : une variante `s`/`m` serait plus précise mais trop lourde pour du temps réel sans GPU.

---

## 📘 Ce que j'ai fait — Brique 5 (Vision IA)

**Pourquoi YOLOv8n et pas un autre modèle :** c'est le plus **léger** de la famille YOLOv8 (~3 M paramètres). Il tourne en **temps réel sur CPU** (y compris Mac Apple Silicon, ~20 ms/frame mesuré), là où les variantes `s/m/l/x` — plus précises — demanderaient un GPU. Pour notre besoin (repérer une **présence humaine**, pas distinguer qui), le nano suffit largement. D'autres pistes (Haar cascades) sont plus rapides mais beaucoup moins fiables ; un modèle lourd serait du gâchis.

**Comment la détection s'intègre dans SENTINEL-X :** le module produit exactement le **même format d'alerte** que l'IA prédictive (Brique 6), avec `source: "ia_vision"`. Les deux sources envoient leurs alertes au **même endpoint** (`POST /api/v1/alerts`) → le DEV et le dashboard les traitent de façon uniforme. La vision couvre la menace « intrusion physique », le prédictif couvre les « anomalies capteurs » : deux yeux complémentaires de l'avant-poste.

**Ce que « confidence ≥ 0.50 » signifie concrètement :** YOLO attribue à chaque détection un score de **0 à 1** = « à quel point je suis sûr que c'est une personne ». Le seuil 0.50 = on ne déclenche une alerte que si le modèle est **sûr à au moins 50 %**. Plus bas (ex. 0.30) → on détecte plus de personnes mais plus de **fausses alertes** (ombres, objets). Plus haut (ex. 0.70) → moins de fausses alertes mais on risque de **rater** une vraie personne mal éclairée. 0.50 est le compromis classique pour de la surveillance.
