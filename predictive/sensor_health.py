"""BRIQUE 6.2 — Surveillance de la SANTÉ des capteurs (DHT22, MQ-2, PIR).

Détecte les défaillances matérielles, indépendamment des anomalies « métier » :
- **failed**  : valeur hors limites physiques (capteur cassé / débranché),
- **stuck**   : même valeur figée N lectures (câble / alim),
- **drift**   : variation physiquement impossible (vitesse trop grande),
- **timeout** : trou de communication (le capteur n'a pas publié depuis longtemps).

Sert à distinguer « vraie anomalie » d'« anomalie due à un capteur HS ».
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

STUCK_COUNT = 10          # nb de valeurs identiques consécutives → figé
# Capteurs dont une valeur constante est NORMALE (ex. PIR à 0 = pièce vide) :
# on ne les signale pas comme "stuck".
STUCK_EXCLUS = {"presence"}


@dataclass
class SensorStatus:
    """État de santé d'un capteur à un instant donné."""
    name: str
    status: str          # healthy | drift | stuck | timeout | failed
    last_value: float
    last_timestamp: str
    reason: str
    recommendation: str
    severity: str        # INFO | WARNING | CRITICAL


class SensorHealthMonitor:
    """Surveille la santé physique des capteurs (historique glissant par capteur)."""

    def __init__(self, window_size: int = 100, timeout_seconds: int = 60) -> None:
        self.window_size = window_size
        self.timeout_seconds = timeout_seconds
        self.history: dict[str, deque] = {
            "temp": deque(maxlen=window_size),
            "humidity": deque(maxlen=window_size),
            "gas": deque(maxlen=window_size),
            "presence": deque(maxlen=window_size),
        }
        # Limites physiques + vitesse de variation max (par seconde)
        self.constraints = {
            "temp": {"min": -40, "max": 80, "max_delta_per_sec": 2.0},
            "humidity": {"min": 0, "max": 100, "max_delta_per_sec": 10.0},
            "gas": {"min": 0, "max": 5000, "max_delta_per_sec": 2000.0},
            "presence": {"min": 0, "max": 1, "max_delta_per_sec": 1.0},
        }

    # --- API publique -------------------------------------------------------
    def update(self, sensor_data: dict) -> dict:
        """Ajoute une mesure et retourne les statuts + alertes de santé.

        `sensor_data` : {temp, humidity, gas, presence, timestamp (ISO 8601)}.
        """
        ts = _parse_ts(sensor_data.get("timestamp"))
        statuses: dict[str, SensorStatus] = {}
        alerts: list[SensorStatus] = []

        for name in ("temp", "humidity", "gas", "presence"):
            if name not in sensor_data:
                continue
            hist = self.history[name]
            precedent = hist[-1] if hist else None     # avant d'ajouter la nouvelle
            value = float(sensor_data[name])
            hist.append({"value": value, "timestamp": ts})

            status = self._check(name, value, ts, precedent)
            statuses[name] = status
            if status.status != "healthy":
                alerts.append(status)

        return {
            "timestamp": sensor_data.get("timestamp"),
            "statuses": statuses,
            "alerts": alerts,
            "overall_health": self._overall(statuses),
        }

    # --- Vérifications internes --------------------------------------------
    def _check(self, name: str, value: float, ts: datetime, precedent: dict | None) -> SensorStatus:
        c = self.constraints[name]

        # 1) Hors limites → capteur HS
        if value < c["min"] or value > c["max"]:
            return self._status(name, "failed", value, ts,
                                 f"{name}={value} hors limites [{c['min']}, {c['max']}]",
                                 f"Vérifier le capteur {name} (valeur impossible)", "CRITICAL")

        hist = self.history[name]
        # 2) Figé : N dernières valeurs identiques (sauf capteurs à valeur constante normale)
        if name not in STUCK_EXCLUS and len(hist) >= STUCK_COUNT:
            dernieres = [h["value"] for h in list(hist)[-STUCK_COUNT:]]
            if len(set(dernieres)) == 1:
                return self._status(name, "stuck", value, ts,
                                    f"{name}={value} identique {STUCK_COUNT} fois",
                                    f"Capteur {name} figé — vérifier câble / alimentation", "WARNING")

        # 3) Dérive : variation trop rapide pour être physique
        if precedent is not None:
            dt = (ts - precedent["timestamp"]).total_seconds()
            if dt > 0:
                vitesse = abs(value - precedent["value"]) / dt
                if vitesse > c["max_delta_per_sec"]:
                    return self._status(name, "drift", value, ts,
                                        f"{name} varie de {vitesse:.1f}/s (max {c['max_delta_per_sec']})",
                                        f"Dérive — recalibrage {name} recommandé", "WARNING")
            # 4) Timeout : trou de communication avant cette mesure
            if dt > self.timeout_seconds:
                return self._status(name, "timeout", value, ts,
                                    f"{name} absent {dt:.0f}s (timeout {self.timeout_seconds}s)",
                                    f"Capteur {name} a cessé d'émettre — vérifier l'ESP32", "CRITICAL")

        # 5) Sain
        return self._status(name, "healthy", value, ts, "OK", "", "INFO")

    @staticmethod
    def _status(name, status, value, ts, reason, reco, severity) -> SensorStatus:
        return SensorStatus(name=name, status=status, last_value=value,
                            last_timestamp=ts.isoformat(), reason=reason,
                            recommendation=reco, severity=severity)

    @staticmethod
    def _overall(statuses: dict[str, SensorStatus]) -> dict:
        critical = sum(1 for s in statuses.values() if s.severity == "CRITICAL")
        warning = sum(1 for s in statuses.values() if s.severity == "WARNING")
        if critical:
            return {"level": "CRITICAL", "count": critical}
        if warning:
            return {"level": "WARNING", "count": warning}
        return {"level": "HEALTHY", "count": 0}


def _parse_ts(ts: str | None) -> datetime:
    """Parse un timestamp ISO 8601 (avec ou sans Z). Fallback = maintenant."""
    from datetime import timezone
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return datetime.now(timezone.utc)
