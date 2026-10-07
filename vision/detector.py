"""BRIQUE 5 — Vision IA : détection d'intrusion (personnes) par YOLOv8n.

Capture le flux webcam (640×480), détecte les personnes avec YOLOv8n, et émet une
alerte JSON (format SENTINEL-X) vers l'API dès qu'une personne est détectée.

Pourquoi YOLOv8n ? C'est le plus LÉGER de la famille YOLOv8 (~3 M paramètres) :
rapide sur CPU (y compris Mac Apple Silicon), suffisant pour détecter une
personne. Les variantes s/m/l/x sont plus précises mais trop lourdes pour du
temps réel sans GPU — inutile ici, on ne cherche qu'à repérer une présence.

Usage :
    python -m vision.detector                 # webcam réelle
    python -m vision.detector --simulate      # sans webcam (frames synthétiques)
    python -m vision.detector --show          # affichage debug (fenêtre OpenCV)

Testable SANS webcam : bascule automatique en mode simulation si la caméra
est indisponible (ou refus de permission macOS).
"""
from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
colorama_init(autoreset=True)

# --- Constantes ---
MODEL_NAME = "yolov8n.pt"      # nano : léger + rapide (CPU / Apple Silicon)
PERSON_CLASS_ID = 0            # classe "person" dans COCO
CONF_THRESHOLD = 0.50         # on ne garde que les détections sûres à ≥ 50 %
FRAME_W, FRAME_H = 640, 480   # résolution d'inférence
# Dernière image annotée (lue par le dashboard pour afficher la caméra)
LATEST_FRAME = PROJECT_ROOT / "data" / "captures" / "latest.jpg"
LATEST_WRITE_INTERVAL = 0.3   # s : on n'écrit pas le JPG à chaque frame (throttle)
MAX_LATENCY_MS = 100          # objectif : traiter une frame en < 100 ms
ALERT_COOLDOWN_S = 5          # anti-spam : pas 2 alertes identiques en < 5 s
# Index caméra : 0 = 1re caméra. Sur un PC avec webcam intégrée, la webcam USB
# (UGREEN CM678) est souvent l'index 1 → configurable via .env ou --camera.
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))

API_URL = os.getenv("API_URL", "http://localhost:3000")
API_PATH = os.getenv("API_ALERTS_ENDPOINT", "/api/v1/alerts")
API_ENDPOINT = os.getenv("API_ENDPOINT") or f"{API_URL.rstrip('/')}/{API_PATH.lstrip('/')}"


def log(prefix: str, color: str, message: str) -> None:
    """Log console coloré et lisible."""
    print(f"{color}[{prefix}]{Style.RESET_ALL} {message}")


class VisionDetector:
    """Encapsule le modèle YOLO et la logique de détection d'une frame."""

    def __init__(self, conf_threshold: float = CONF_THRESHOLD) -> None:
        """Charge YOLOv8n (téléchargé automatiquement au 1er lancement)."""
        from ultralytics import YOLO  # import tardif : évite de charger torch pour --help

        log("MODÈLE", Fore.MAGENTA, f"Chargement de {MODEL_NAME}…")
        self.model = YOLO(MODEL_NAME)
        self.conf_threshold = conf_threshold
        # Warmup : la 1ʳᵉ inférence est toujours lente (allocation mémoire, JIT).
        # On la « brûle » ici pour que la latence mesurée ensuite soit réaliste.
        self.model(np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8),
                   verbose=False, classes=[PERSON_CLASS_ID])

    def detecter(self, frame: np.ndarray) -> tuple[list[dict], float]:
        """Détecte les personnes dans une frame. Retourne (détections, latence_ms).

        Chaque détection : {confidence, box:[x1,y1,x2,y2] normalisés dans [0,1]}.
        """
        frame = cv2.resize(frame, (FRAME_W, FRAME_H))
        debut = time.perf_counter()
        resultats = self.model(frame, verbose=False, classes=[PERSON_CLASS_ID])
        latence_ms = (time.perf_counter() - debut) * 1000.0

        detections: list[dict] = []
        for res in resultats:
            for box in res.boxes:
                conf = float(box.conf[0])
                if conf < self.conf_threshold:
                    continue
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                detections.append({
                    "confidence": round(conf, 3),
                    "box": [round(x1 / FRAME_W, 3), round(y1 / FRAME_H, 3),
                            round(x2 / FRAME_W, 3), round(y2 / FRAME_H, 3)],
                })
        return detections, latence_ms


def construire_alerte(detections: list[dict]) -> dict:
    """Construit l'alerte JSON au format SENTINEL-X (immuable)."""
    confiances = [d["confidence"] for d in detections]
    nb = len(detections)
    # Sévérité : une présence = WARNING ; plusieurs personnes = CRITICAL.
    # (La "confidence" YOLO mesure la certitude de détection, PAS la gravité.)
    severite = "CRITICAL" if nb >= 2 else "WARNING"
    return {
        "source": "ia_vision",
        "type": "intrusion_detected",
        "confidence": max(confiances),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "details": {
            "persons_detected": nb,
            "max_confidence": max(confiances),
            "bounding_boxes": [d["box"] for d in detections],
            "severity": severite,
            "context": f"{nb} personne(s) détectée(s) par la caméra",
        },
    }


def poster_alerte(alerte: dict) -> bool:
    """POST l'alerte vers l'API. Tolérant : si l'API est absente, on log et on continue."""
    try:
        r = requests.post(API_ENDPOINT, json=alerte, timeout=2)
        return 200 <= r.status_code < 300
    except requests.RequestException as exc:
        log("API", Fore.YELLOW, f"API injoignable ({exc.__class__.__name__}) — alerte loggée seulement")
        return False


def frame_simulee(compteur: int) -> np.ndarray:
    """Génère une frame noire avec des rectangles colorés (fausses « personnes »)."""
    frame = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
    decalage = (compteur * 15) % 300
    cv2.rectangle(frame, (50 + decalage, 120), (160 + decalage, 400), (0, 140, 255), -1)
    cv2.rectangle(frame, (350, 100), (470, 420), (0, 200, 120), -1)
    return frame


def _backend_cv2() -> int:
    """Backend OpenCV adapté à l'OS (crucial pour l'ouverture webcam).

    Windows : DirectShow (CAP_DSHOW) = ouverture rapide et fiable des webcams USB.
    macOS / Linux : backend par défaut (AVFoundation / V4L2).
    """
    return cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY


def _message_permission() -> str:
    """Message d'aide aux permissions caméra selon l'OS."""
    systeme = platform.system()
    if systeme == "Darwin":
        return "macOS : Réglages → Confidentialité & sécurité → Caméra → autoriser le Terminal."
    if systeme == "Windows":
        return "Windows : Paramètres → Confidentialité → Caméra → autoriser les applis de bureau."
    return "Linux : vérifier les permissions /dev/video* (ajouter l'utilisateur au groupe 'video')."


def _ouvrir_webcam(index: int = CAMERA_INDEX) -> cv2.VideoCapture | None:
    """Tente d'ouvrir la webcam `index`. Retourne None si indisponible (→ simulation)."""
    cap = cv2.VideoCapture(index, _backend_cv2())
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    ok, _ = cap.read()  # une lecture test : révèle un refus de permission (TCC macOS / Windows)
    if not ok:
        cap.release()
        return None
    return cap


def _ouvrir_webcam_auto(prefere: int = CAMERA_INDEX, maxi: int = 3):
    """Essaie l'index préféré puis balaie 0..maxi. Retourne (cap, index) ou (None, -1).

    Utile car la webcam USB (UGREEN CM678) est souvent sur l'index 1, pas 0.
    """
    candidats = [prefere] + [i for i in range(maxi + 1) if i != prefere]
    for idx in candidats:
        cap = _ouvrir_webcam(idx)
        if cap is not None:
            return cap, idx
    return None, -1


def lister_cameras(maxi: int = 5) -> None:
    """Scanne les index 0..maxi et affiche les caméras ouvrables (pour trouver la bonne)."""
    log("SCAN", Fore.MAGENTA, f"Recherche des caméras (index 0 à {maxi})…")
    trouvees = 0
    for idx in range(maxi + 1):
        cap = cv2.VideoCapture(idx, _backend_cv2())
        if cap.isOpened():
            ok, _ = cap.read()
            etat = "OK (lecture)" if ok else "ouverte mais lecture KO (permission ?)"
            log("CAMÉRA", Fore.GREEN, f"  index {idx} : {etat}")
            trouvees += 1
        cap.release()
    if not trouvees:
        log("CAMÉRA", Fore.YELLOW, "Aucune caméra détectée.")
        log("AIDE", Fore.YELLOW, _message_permission())


def run_detection(api_url: str | None = None, simulate: bool = False,
                  show: bool = False, frames: int = 0,
                  camera_index: int = CAMERA_INDEX) -> int:
    """Boucle principale : capture → détecte → alerte si personne. Ctrl+C pour arrêter.

    `frames` > 0 limite le nombre d'itérations (utile pour les tests) ; 0 = infini.
    `camera_index` : 0 = 1re caméra ; la webcam USB (UGREEN CM678) est souvent 1.
    """
    global API_ENDPOINT
    if api_url:
        API_ENDPOINT = api_url

    detector = VisionDetector()

    cap = None
    if not simulate:
        cap, idx_trouve = _ouvrir_webcam_auto(camera_index)
        if cap is None:
            log("CAMÉRA", Fore.YELLOW,
                f"Aucune webcam trouvée (index testés : {camera_index}, 0-3).")
            log("AIDE", Fore.YELLOW, _message_permission())
            log("AIDE", Fore.YELLOW, "Branche la webcam USB puis relance, ou force : --camera 1")
            simulate = True
        elif idx_trouve != camera_index:
            log("CAMÉRA", Fore.GREEN, f"Webcam détectée automatiquement sur l'index {idx_trouve}.")

    if simulate:
        log("SIMULATION", Fore.CYAN, "MODE SIMULATION ACTIVÉ — frames synthétiques (pas de vraie caméra).")

    log("INFO", Fore.MAGENTA,
        f"Détection vision démarrée (seuil={detector.conf_threshold}, API={API_ENDPOINT}). Ctrl+C pour arrêter.")

    derniere_alerte = 0.0
    derniere_ecriture = 0.0
    i = 0
    try:
        while True:
            if simulate:
                frame = frame_simulee(i)
            else:
                ok, frame = cap.read()
                if not ok:
                    log("CAMÉRA", Fore.RED, "Lecture frame échouée — arrêt.")
                    break

            detections, latence = detector.detecter(frame)
            if latence > MAX_LATENCY_MS:
                log("PERF", Fore.YELLOW, f"Frame lente : {latence:.0f} ms (> {MAX_LATENCY_MS} ms)")

            if detections:
                maintenant = time.monotonic()
                if maintenant - derniere_alerte >= ALERT_COOLDOWN_S:
                    derniere_alerte = maintenant
                    alerte = construire_alerte(detections)
                    log("INTRUSION", Fore.RED,
                        f"{alerte['details']['persons_detected']} personne(s), "
                        f"confiance max {alerte['confidence']} ({latence:.0f} ms)")
                    poster_alerte(alerte)

            # Image annotée pour le dashboard (/camera) — écrite périodiquement
            _dessiner_boites(frame, detections)
            now = time.monotonic()
            if now - derniere_ecriture >= LATEST_WRITE_INTERVAL:
                derniere_ecriture = now
                _ecrire_latest(frame)

            if show:
                cv2.imshow("SENTINEL-X Vision", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            i += 1
            if frames and i >= frames:
                break
    except KeyboardInterrupt:
        log("STOP", Fore.MAGENTA, "Arrêt demandé (Ctrl+C).")
    finally:
        if cap is not None:
            cap.release()
        if show:
            cv2.destroyAllWindows()

    log("OK", Fore.GREEN, f"Terminé — {i} frame(s) traitée(s).")
    return 0


def _dessiner_boites(frame: np.ndarray, detections: list[dict]) -> np.ndarray:
    """Dessine les boîtes « person » sur la frame (modifiée en place)."""
    for d in detections:
        x1, y1, x2, y2 = d["box"]
        p1 = (int(x1 * FRAME_W), int(y1 * FRAME_H))
        p2 = (int(x2 * FRAME_W), int(y2 * FRAME_H))
        cv2.rectangle(frame, p1, p2, (0, 0, 255), 2)
        cv2.putText(frame, f"person {d['confidence']}", (p1[0], p1[1] - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    return frame


def _ecrire_latest(frame: np.ndarray) -> None:
    """Écrit la dernière image annotée pour le dashboard (/camera)."""
    try:
        LATEST_FRAME.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(LATEST_FRAME), frame)
    except Exception:
        pass  # l'affichage dashboard ne doit jamais casser la détection


def main() -> int:
    """Point d'entrée CLI."""
    parser = argparse.ArgumentParser(description="SENTINEL-X — Vision IA (Brique 5)")
    parser.add_argument("--simulate", action="store_true", help="mode sans webcam (frames synthétiques)")
    parser.add_argument("--show", action="store_true", help="affiche la fenêtre OpenCV (debug)")
    parser.add_argument("--frames", type=int, default=0, help="nb de frames max (0 = infini)")
    parser.add_argument("--camera", type=int, default=CAMERA_INDEX,
                        help="index de la caméra (0 = 1re ; webcam USB souvent 1)")
    parser.add_argument("--api", type=str, default=None, help="URL de l'API d'alertes")
    parser.add_argument("--list", action="store_true", help="liste les caméras disponibles puis quitte")
    args = parser.parse_args()
    if args.list:
        lister_cameras()
        return 0
    return run_detection(api_url=args.api, simulate=args.simulate, show=args.show,
                         frames=args.frames, camera_index=args.camera)


if __name__ == "__main__":
    sys.exit(main())
