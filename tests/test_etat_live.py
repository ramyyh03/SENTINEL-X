"""Tests de l'état consolidé partagé app/OLED/LEDs (api/server.py)."""
from datetime import datetime, timedelta, timezone

from api import server
from predictive.alert_publisher import _texte_oled


def _iso(secondes_dans_le_passe: float = 0.0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(seconds=secondes_dans_le_passe)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class _FakeMagasin:
    """Magasin minimal : juste ce qu'utilise _etat_consolide."""

    def __init__(self, alertes):
        self._alertes = alertes
        self.db_path = "memoire"

    def recent(self, limit=50):
        return self._alertes[:limit]


def test_etat_normal_sans_alerte():
    etat = server._etat_consolide(_FakeMagasin([]))
    assert etat["niveau"] == "vert" and etat["severity"] == "INFO"


def test_etat_critique_alerte_recente():
    alerte = {"type": "FUITE_GAZ", "timestamp": _iso(2),
              "details": {"severity": "CRITICAL", "context": "Gaz eleve"}}
    etat = server._etat_consolide(_FakeMagasin([alerte]))
    assert etat["niveau"] == "rouge" and etat["severity"] == "CRITICAL"
    assert etat["context"] == "Gaz eleve"


def test_etat_warning_alerte_recente():
    alerte = {"type": "PRESENCE", "timestamp": _iso(2),
              "details": {"severity": "WARNING", "context": "Presence"}}
    etat = server._etat_consolide(_FakeMagasin([alerte]))
    assert etat["niveau"] == "orange" and etat["severity"] == "WARNING"


def test_etat_revient_vert_apres_fenetre():
    # Une alerte critique trop vieille (> 30 s) ne colore plus l'état.
    alerte = {"type": "FUITE_GAZ", "timestamp": _iso(120),
              "details": {"severity": "CRITICAL", "context": "Gaz"}}
    etat = server._etat_consolide(_FakeMagasin([alerte]))
    assert etat["niveau"] == "vert"


def test_camera_live_prend_le_dessus(tmp_path, monkeypatch):
    # Caméra : 2 personnes => rouge, même sans alerte capteur.
    vs = tmp_path / "vision_status.json"
    vs.write_text('{"persons": 2}', encoding="utf-8")
    monkeypatch.setattr(server, "VISION_STATUS", vs)
    etat = server._etat_consolide(_FakeMagasin([]))
    assert etat["niveau"] == "rouge" and etat["severity"] == "CRITICAL"


def test_texte_oled_retire_emoji_et_tronque():
    propre = _texte_oled("🔥 Fumée + température en hausse → incendie probable danger")
    assert all(ord(c) < 128 for c in propre)      # ASCII pur (lisible sur l'OLED)
    assert len(propre) <= 40
