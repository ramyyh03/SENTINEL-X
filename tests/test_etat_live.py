"""Tests de l'état consolidé live (app/OLED/LEDs) — api/server.py.

L'état vient des mesures LIVE passées au moteur de corrélation + la caméra.
"""
import sqlite3
from datetime import datetime, timezone

from api import server
from predictive.alert_publisher import _texte_oled


def _db_avec_mesure(tmp_path, temp=22, humidity=50, gas=0, presence=0):
    """Crée une base sqlite avec UNE mesure fraîche (table sensor_data)."""
    db = tmp_path / "sentinel.db"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE sensor_data (id INTEGER PRIMARY KEY, timestamp TEXT, "
            "temp REAL, humidity REAL, gas REAL, presence INTEGER)")
        conn.execute(
            "INSERT INTO sensor_data (timestamp, temp, humidity, gas, presence) "
            "VALUES (?, ?, ?, ?, ?)", (ts, temp, humidity, gas, presence))
        conn.commit()
    return db


class _Magasin:
    def __init__(self, db_path):
        self.db_path = db_path


def _sans_profil(tmp_path, monkeypatch):
    """Force les seuils par défaut (aucun profil enregistré)."""
    monkeypatch.setattr("predictive.profil.PROFIL_PATH", tmp_path / "noprofile.json")


def _etat(tmp_path, monkeypatch, **mesure):
    # Pas de caméra ni de profil par défaut (fichiers inexistants).
    _sans_profil(tmp_path, monkeypatch)
    monkeypatch.setattr(server, "VISION_STATUS", tmp_path / "pas_de_cam.json")
    db = _db_avec_mesure(tmp_path, **mesure)
    return server._etat_consolide(_Magasin(db))


def test_etat_normal(tmp_path, monkeypatch):
    etat = _etat(tmp_path, monkeypatch, temp=22, gas=0, presence=0)
    assert etat["niveau"] == "vert" and etat["severity"] == "INFO"


def test_temp_rouge(tmp_path, monkeypatch):
    etat = _etat(tmp_path, monkeypatch, temp=33)
    assert etat["niveau"] == "rouge" and etat["severity"] == "CRITICAL"


def test_temp_jaune(tmp_path, monkeypatch):
    etat = _etat(tmp_path, monkeypatch, temp=29)
    assert etat["niveau"] == "orange" and etat["severity"] == "WARNING"


def test_gaz_rouge(tmp_path, monkeypatch):
    etat = _etat(tmp_path, monkeypatch, gas=300)
    assert etat["niveau"] == "rouge"


def test_gaz_jaune(tmp_path, monkeypatch):
    etat = _etat(tmp_path, monkeypatch, gas=120)
    assert etat["niveau"] == "orange"


def test_pir_presence_jaune(tmp_path, monkeypatch):
    etat = _etat(tmp_path, monkeypatch, presence=1)
    assert etat["niveau"] == "orange" and etat["severity"] == "WARNING"


def test_camera_live_prend_le_dessus(tmp_path, monkeypatch):
    # 2 personnes à la caméra => rouge, même avec des capteurs au calme.
    _sans_profil(tmp_path, monkeypatch)
    vs = tmp_path / "vision_status.json"
    vs.write_text('{"persons": 2}', encoding="utf-8")
    monkeypatch.setattr(server, "VISION_STATUS", vs)
    db = _db_avec_mesure(tmp_path, temp=22, gas=0, presence=0)
    etat = server._etat_consolide(_Magasin(db))
    assert etat["niveau"] == "rouge" and etat["severity"] == "CRITICAL"


def test_mesure_perimee_ignoree(tmp_path, monkeypatch):
    # Une mesure trop vieille ne doit pas colorer l'état (ESP32 déconnecté).
    _sans_profil(tmp_path, monkeypatch)
    monkeypatch.setattr(server, "VISION_STATUS", tmp_path / "pas_de_cam.json")
    db = tmp_path / "sentinel.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE sensor_data (id INTEGER PRIMARY KEY, timestamp TEXT, "
            "temp REAL, humidity REAL, gas REAL, presence INTEGER)")
        conn.execute(
            "INSERT INTO sensor_data (timestamp, temp, humidity, gas, presence) "
            "VALUES ('2000-01-01T00:00:00Z', 40, 50, 500, 1)")
        conn.commit()
    etat = server._etat_consolide(_Magasin(db))
    assert etat["niveau"] == "vert"


def test_texte_oled_retire_emoji_et_tronque():
    propre = _texte_oled("🔥 Fumée + température en hausse → incendie probable danger")
    assert all(ord(c) < 128 for c in propre)      # ASCII pur (lisible sur l'OLED)
    assert len(propre) <= 40
