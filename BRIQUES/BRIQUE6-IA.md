# BRIQUE 6 : IA Prédictive — Isolation Forest + LOF

> **SENTINEL-X — Workshop EPSI BAC+4**
> Détection d'anomalies **cinétiques** (corrélations suspectes) **avant** le seuil critique.

---

## 🎯 Vue d'ensemble (30 secondes)

La Brique 6 lit les séries temporelles des capteurs (`data/sentinel.db`, alimentée par la Brique 3), calcule **27 features** (vitesses, corrélations, écarts à la baseline), et combine **deux modèles non supervisés** (Isolation Forest + Local Outlier Factor) pour détecter les comportements anormaux. Chaque anomalie génère une **alerte JSON** envoyée à l'API (`POST /api/v1/alerts`).

```
sentinel.db ──► feature_engineer (27 features) ──► Forest + LOF (ensemble)
                                                          │
                              baseline 1h ◄───────────────┤
                                                          ▼
                        alerte JSON (sévérité + contexte + reco) ──► POST API
```

---

## 🏃 Lancer en 3 commandes

```bash
make train     # génère données + entraîne Forest/LOF + évalue
make replay    # teste l'IA sur le dataset synthétique (sans DB ni broker)
make detect    # détection temps réel sur data/sentinel.db → POST API
```

> `make detect --once` (ou `python -m predictive.main_brique6 detect --once`) traite les lignes existantes puis s'arrête — pratique pour tester.

---

## 🧠 Architecture IA

### 1. Données synthétiques (`data_generator.py`)
2880 lectures (48 h, 1/min) : profils **normaux** (nuit stable, jour actif, ventilation, repos) + **8 types d'anomalies** injectées (~10 %) : intrusion, fuite gaz lente, surchauffe, condensation, capteur figé, corrélation inverse, dérive lente, combinaison multi-facteurs. Étiquetées → `data/training_data.csv`.

### 2. Feature engineering (`feature_engineer.py`) — 27 features
| Famille | Exemples |
|---|---|
| Brutes normalisées | `temp_n`, `gas_n`, … |
| Dérivées (vitesses/accél.) | `gas_velocity`, `temp_accel`, `temp_delta_5` |
| Glissantes (fenêtre 5) | `temp_roll_std`, `gas_roll_range` |
| Corrélations inter-capteurs | `corr_gas_presence`, `corr_humidity_temp`, `ratio_gas_temp` |
| Écarts baseline 1h | `z_score_temp`, `z_score_gas`, `baseline_distance` |

### 3. Ensemble (`forest_trainer.py` + `scoring.py`)
- **Isolation Forest** (100 arbres) : aberrances globales.
- **LOF** (20 voisins, `novelty=True`) : anomalies locales de densité.
- Score ramené dans **[0,1]** avec la **frontière de décision centrée sur 0.5** ; ensemble = moyenne pondérée. Seuil d'alerte par défaut **0.4**.

### 4. Détection temps réel (`anomaly_detector.py`)
Score la dernière lecture sur un tampon glissant ; détecte les **capteurs figés** (même valeur 25×) ; explicabilité = **top 3 features** les plus éloignées de la normale.

### 5. Alertes (`alert_generator.py` + `alert_aggregator.py`)
JSON unifié (`source/type/confidence/timestamp/details`), **sévérité** INFO/WARNING/CRITICAL, **contexte** + **recommandation** par règles métier, **anti-spam** (1 alerte/min) et **escalade** (3+ en 5 min → CRITICAL).

### 6. Prévision ARIMA (`arima_trainer.py`) — optionnel
Désactivé par défaut (`ARIMA_ENABLED=false`), import protégé (pas de dépendance obligatoire).

---

## 📊 Résultats d'entraînement (seuil 0.4)

| Métrique | Valeur | Lecture |
|---|---|---|
| **Rappel par ÉPISODE** | **1.000** | ✅ **22/22 incidents détectés** |
| ROC-AUC | 0.805 | bonne discrimination normal/anomalie |
| Précision (point) | 0.37 | — |
| Rappel (point) | 0.46 | — |
| Matrice | TP=126 FP=211 FN=149 TN=2394 | sur 2880 lectures |

> **Pourquoi précision/rappel *point par point* sont modestes — et pourquoi ce n'est pas un problème.**
> Beaucoup de points étiquetés « anomalie » sont **indiscernables du normal** pris isolément (minute 1 d'une dérive de −0.1 °C/min, capteur figé sur une valeur plausible…). La métrique qui compte pour de la **surveillance** est : *a-t-on attrapé l'incident ?* → **oui, les 22 épisodes**. Les faux positifs point-par-point sont absorbés par l'**agrégation** (1 alerte/min + escalade).

---

## 🧪 Tests réalisés

| Test | Résultat |
|---|---|
| Entraînement sur synthétique | ✅ rappel épisode 1.0, ROC-AUC 0.80 |
| `replay` du dataset complet | ✅ alertes générées sur les épisodes connus |
| `detect --once` sur base réelle | ✅ scoring + logs + POST (API absente → tolérée) |
| Injection manuelle (`temp=50, gas=3500`) | ✅ **score 1.0 CRITICAL → « Gaz élevé sans présence → fuite possible »** |

---

## ⚙️ Configuration (`.env`)

```
FOREST_CONTAMINATION=0.1     FOREST_THRESHOLD=0.4     LOF_NEIGHBORS=20
ALERT_WINDOW=300             ALERT_MIN_INTERVAL=60    GENERATE_SYNTHETIC_DATA=true
ARIMA_ENABLED=false          API_ENDPOINT=http://localhost:3000/api/v1/alerts
```

---

## ⚠️ Limites honnêtes

- **Modèle entraîné sur des profils réalistes lissés** (DHT22 réel). Le **simulateur** `fake_sensors_esp32.py` produit du bruit *aléatoire uniforme* → l'IA le trouve « atypique » et sur-alerte. Sur le **vrai ESP32** (mesures lisses), le comportement est bien plus calme.
- `gas` = valeur brute ADC du MQ-2 (pas de ppm calibrés) — l'IA travaille très bien sur le brut.
- Modèles (`models/*.pkl`) **non commités** (binaires régénérables) : `make train` les recrée en ~2 s.

---

## 📁 Fichiers livrés

```
predictive/
├── data_generator.py      feature_engineer.py    scoring.py
├── forest_trainer.py      metrics_evaluator.py   baseline_analyzer.py
├── anomaly_detector.py    alert_generator.py     alert_aggregator.py
├── arima_trainer.py       main_brique6.py        collector.py (Brique 3)
data/training_data.csv     ← dataset synthétique étiqueté (commité)
models/  logs/             ← générés par `make train` (ignorés par Git)
```

---

## 📘 Ce que j'ai fait — Brique 6 (IA prédictive)

**En une phrase :** un détecteur d'anomalies qui apprend le comportement « normal » des capteurs et lève des alertes explicables **avant** qu'un seuil critique ne soit franchi.

**Pourquoi ces choix techniques :** **ensemble** Forest + LOF car ils capturent des anomalies de natures différentes (globales vs locales). **Feature engineering** (vitesses, corrélations, z-scores) pour détecter des dynamiques *cinétiques* — une fuite se voit à la **vitesse** du gaz, pas à sa valeur instantanée. Scoring recalé sur la **frontière de décision** pour un seuil interprétable.

**Comment ça s'intègre dans SENTINEL-X :** lit `data/sentinel.db` (Brique 3) → envoie des alertes au format unifié vers l'**API DEV** (`POST /api/v1/alerts`), aux côtés des alertes Vision (Brique 5). C'est la « matière grise » prédictive de l'avant-poste.

**Pour tester sans matériel :** `make train` puis `make replay` (100 % autonome) ; ou `make detect --once` après avoir injecté une anomalie dans la base.
