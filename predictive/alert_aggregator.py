"""BRIQUE 6 — Agrégation des alertes (anti-spam + escalade).

- Coalescence : au plus 1 alerte émise par minute (les autres sont comptées, pas émises).
- Escalade : 3+ anomalies dans la fenêtre (5 min) → sévérité forcée à CRITICAL.
Évite de noyer le dashboard tout en remontant les rafales d'anomalies.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta


class Agregateur:
    """État glissant des anomalies récentes pour décider quoi émettre."""

    def __init__(self, min_interval_s: int = 60, window_s: int = 300,
                 escalade_count: int = 3) -> None:
        self.min_interval = timedelta(seconds=min_interval_s)
        self.window = timedelta(seconds=window_s)
        self.escalade_count = escalade_count
        self._historique: deque[datetime] = deque()  # horodatages d'anomalies
        self._derniere_emission: datetime | None = None
        self._supprimees = 0

    def soumettre(self, alerte: dict, maintenant: datetime) -> dict | None:
        """Prend une alerte + l'instant courant. Retourne l'alerte à émettre, ou None.

        None = alerte volontairement supprimée (coalescence) mais comptabilisée.
        """
        # 1) Historique glissant des anomalies dans la fenêtre
        self._historique.append(maintenant)
        limite = maintenant - self.window
        while self._historique and self._historique[0] < limite:
            self._historique.popleft()
        nb_fenetre = len(self._historique)

        # 2) Escalade automatique si rafale
        if nb_fenetre >= self.escalade_count:
            alerte["details"]["severity"] = "CRITICAL"
        alerte["details"]["alert_count_5min"] = nb_fenetre

        # 3) Coalescence : pas plus d'une émission par minute
        if (self._derniere_emission is not None
                and maintenant - self._derniere_emission < self.min_interval):
            self._supprimees += 1
            return None

        # 4) Émission : on joint le nombre d'alertes agrégées depuis la dernière
        alerte["details"]["aggregated_suppressed"] = self._supprimees
        self._supprimees = 0
        self._derniere_emission = maintenant
        return alerte
