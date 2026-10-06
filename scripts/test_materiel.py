"""SENTINEL-X — Test matériel automatique de la webcam (+ YOLOv8).

Détecte la webcam (ex. UGREEN CM678), capture 3 images réelles, fait tourner
YOLOv8n dessus, et génère un rapport RAPPORT-MATERIEL.md.

Cross-plateforme (Windows inclus : backend DirectShow choisi automatiquement).
Signé : rami yahyaoui.

Usage :
    python scripts/test_materiel.py                 # auto-détecte la 1re caméra qui marche
    python scripts/test_materiel.py --camera 1      # force un index (webcam USB souvent 1)
    python scripts/test_materiel.py --max 8         # élargit le scan d'index
"""
from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from vision.detector import FRAME_H, FRAME_W, _backend_cv2  # noqa: E402

CAPTURES_DIR = PROJECT_ROOT / "data" / "captures"
RAPPORT = PROJECT_ROOT / "RAPPORT-MATERIEL.md"
NB_FRAMES = 3           # nombre d'images à capturer
WARMUP_FRAMES = 5       # images jetées au début (le temps que l'expo se stabilise)


def scanner_cameras(maxi: int = 5) -> list[int]:
    """Retourne la liste des index de caméra réellement ouvrables ET lisibles."""
    trouvees = []
    for idx in range(maxi + 1):
        cap = cv2.VideoCapture(idx, _backend_cv2())
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                trouvees.append(idx)
        cap.release()
    return trouvees


def capturer(index: int) -> list[Path]:
    """Capture NB_FRAMES images sur la caméra `index` et les enregistre en JPG."""
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(index, _backend_cv2())
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir la caméra index {index}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)

    for _ in range(WARMUP_FRAMES):  # on « réchauffe » le capteur (expo/balance)
        cap.read()

    chemins = []
    for i in range(1, NB_FRAMES + 1):
        ok, frame = cap.read()
        if not ok:
            cap.release()
            raise RuntimeError(f"Lecture de l'image {i} échouée (caméra {index})")
        chemin = CAPTURES_DIR / f"capture_{i}.jpg"
        cv2.imwrite(str(chemin), frame)
        chemins.append(chemin)
    cap.release()
    return chemins


def analyser(chemins: list[Path]) -> list[dict]:
    """Fait tourner YOLOv8n sur chaque image et retourne les détections + latence."""
    from vision.detector import VisionDetector

    detecteur = VisionDetector()
    resultats = []
    for chemin in chemins:
        frame = cv2.imread(str(chemin))
        detections, latence = detecteur.detecter(frame)
        resultats.append({
            "image": chemin.name,
            "personnes": len(detections),
            "confiance_max": max((d["confidence"] for d in detections), default=0.0),
            "latence_ms": round(latence, 1),
        })
    return resultats


def ecrire_rapport(index: int | None, cameras: list[int],
                   resultats: list[dict], erreur: str | None) -> None:
    """Génère RAPPORT-MATERIEL.md (résumé lisible du test webcam)."""
    maintenant = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lignes = [
        "# RAPPORT MATÉRIEL — SENTINEL-X",
        "",
        f"> Généré le {maintenant} · OS : {platform.system()} {platform.release()}",
        "> Signé : rami yahyaoui",
        "",
        "## Webcam",
        "",
        f"- Caméras détectées (index ouvrables) : **{cameras if cameras else 'aucune'}**",
        f"- Caméra testée : **{index if index is not None else '—'}**",
        "",
    ]

    if erreur:
        lignes += [f"❌ **Échec** : {erreur}", "",
                   "Vérifier : branchement USB, permissions caméra Windows, index (`--camera`)."]
    elif resultats:
        lignes += ["### YOLOv8n sur les images capturées", "",
                   "| Image | Personnes | Confiance max | Latence |",
                   "|---|---|---|---|"]
        for r in resultats:
            lignes.append(
                f"| {r['image']} | {r['personnes']} | {r['confiance_max']} | {r['latence_ms']} ms |")
        latence_moy = sum(r["latence_ms"] for r in resultats) / len(resultats)
        total_pers = sum(r["personnes"] for r in resultats)
        lignes += [
            "",
            f"- Latence moyenne : **{latence_moy:.0f} ms** (objectif < 100 ms)",
            f"- Personnes détectées (total sur {len(resultats)} images) : **{total_pers}**",
            f"- Images sauvegardées : `{CAPTURES_DIR.relative_to(PROJECT_ROOT)}/`",
            "",
            "✅ **Webcam fonctionnelle** : capture + inférence YOLOv8 OK."
            if latence_moy < 300 else
            "⚠️ Webcam OK mais latence élevée (CPU chargé ?).",
            "",
            "> ℹ️ 0 personne détectée est NORMAL si personne n'est devant la caméra. "
            "Pour valider la détection, se placer dans le champ et relancer.",
        ]
    lignes += ["", "## ESP32", "",
               "Non testé par ce script (nécessite le flash + le moniteur série).",
               "Voir la checklist : `BRIQUES/CHECKLIST-MATERIEL.md`.", ""]

    RAPPORT.write_text("\n".join(lignes), encoding="utf-8")


def main() -> int:
    """Point d'entrée : scan → capture → analyse → rapport."""
    parser = argparse.ArgumentParser(description="SENTINEL-X — Test matériel webcam")
    parser.add_argument("--camera", type=int, default=None, help="index caméra à tester")
    parser.add_argument("--max", type=int, default=5, help="index max pour le scan auto")
    args = parser.parse_args()

    print("🔍 Recherche des caméras…")
    cameras = scanner_cameras(args.max)
    print(f"   Caméras détectées : {cameras if cameras else 'AUCUNE'}")

    index = args.camera if args.camera is not None else (cameras[0] if cameras else None)
    resultats, erreur = [], None

    if index is None:
        erreur = "aucune caméra détectée (branchement USB ? permissions Windows ?)"
        print(f"❌ {erreur}")
    else:
        try:
            print(f"📸 Capture de {NB_FRAMES} images sur la caméra {index}…")
            chemins = capturer(index)
            print("🧠 Analyse YOLOv8n…")
            resultats = analyser(chemins)
            for r in resultats:
                print(f"   {r['image']} : {r['personnes']} personne(s), "
                      f"{r['latence_ms']} ms")
        except Exception as exc:
            erreur = f"{exc.__class__.__name__}: {exc}"
            print(f"❌ {erreur}")

    ecrire_rapport(index, cameras, resultats, erreur)
    print(f"\n📄 Rapport écrit : {RAPPORT.relative_to(PROJECT_ROOT)}")
    return 0 if (resultats and not erreur) else 1


if __name__ == "__main__":
    sys.exit(main())
