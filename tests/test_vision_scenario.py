"""Tests : la vision respecte le profil calibré (vision/detector.py)."""
from predictive.profil import Seuils


def test_vision_une_personne_defaut_warning(monkeypatch, tmp_path):
    monkeypatch.setattr("predictive.profil.PROFIL_PATH", tmp_path / "x.json")
    from vision import detector
    sc = detector.evaluer_scenario(1)
    assert sc.severite == "WARNING"


def test_vision_deux_personnes_defaut_critical(monkeypatch, tmp_path):
    monkeypatch.setattr("predictive.profil.PROFIL_PATH", tmp_path / "x.json")
    from vision import detector
    sc = detector.evaluer_scenario(2)
    assert sc.severite == "CRITICAL"


def test_vision_respecte_cam_ok(monkeypatch, tmp_path):
    # Boulangerie : 2 personnes = OK -> pas d'alerte (INFO).
    p = tmp_path / "profil.json"
    monkeypatch.setattr("predictive.profil.PROFIL_PATH", p)
    from predictive import profil
    profil.enregistrer_seuils({"nom": "Boulangerie", "temp_jaune": 35, "temp_rouge": 45,
                               "gaz_jaune": 150, "gaz_rouge": 400, "cam_ok": 2,
                               "presence_danger": False})
    from vision import detector
    assert detector.evaluer_scenario(2).severite == "INFO"       # toléré
    assert detector.evaluer_scenario(3).severite == "WARNING"    # 1 de trop
