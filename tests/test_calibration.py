"""Tests de l'assistant de calibration (api/server.py)."""
from api import server


def test_page_calibration_contient_le_wizard():
    html = server._page_calibration()
    assert "Assistant de calibration" in html
    assert "/api/v1/calibration/live" in html      # observation live
    assert "/api/v1/calibration/save" in html      # questionnaire -> sauvegarde
    assert "presence_danger" in html               # la présence est-elle un danger ?


def test_snapshot_live_structure(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "VISION_STATUS", tmp_path / "cam.json")
    snap = server._snapshot_live(tmp_path / "vide.db")
    assert set(snap) >= {"temp", "humidity", "gas", "presence", "persons", "maj"}
    assert snap["persons"] == 0


def test_save_rejette_seuils_incoherents(tmp_path, monkeypatch):
    monkeypatch.setattr("predictive.profil.PROFIL_PATH", tmp_path / "p.json")
    app = server.create_app()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test"      # simule une session connectée
    resp = client.post("/api/v1/calibration/save",
                       json={"temp_jaune": 40, "temp_rouge": 30})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_save_accepte_profil_valide(tmp_path, monkeypatch):
    monkeypatch.setattr("predictive.profil.PROFIL_PATH", tmp_path / "p.json")
    app = server.create_app()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test"
    resp = client.post("/api/v1/calibration/save", json={
        "nom": "Boulangerie", "temp_jaune": 35, "temp_rouge": 45,
        "gaz_jaune": 150, "gaz_rouge": 400, "cam_ok": 2, "presence_danger": False})
    assert resp.status_code == 201
    assert resp.get_json()["seuils"]["cam_ok"] == 2
