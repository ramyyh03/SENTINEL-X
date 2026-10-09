"""Tests du profil d'environnement calibrable (predictive/profil.py)."""
import pytest

from predictive import profil
from predictive.profil import Seuils


def test_defaut_sans_fichier(tmp_path, monkeypatch):
    monkeypatch.setattr(profil, "PROFIL_PATH", tmp_path / "absent.json")
    s = profil.charger_seuils()
    assert s == Seuils() and s.temp_jaune == 28.0


def test_enregistrer_puis_charger(tmp_path, monkeypatch):
    monkeypatch.setattr(profil, "PROFIL_PATH", tmp_path / "p.json")
    profil.enregistrer_seuils({
        "nom": "Boulangerie", "temp_jaune": 35, "temp_rouge": 45,
        "gaz_jaune": 150, "gaz_rouge": 400, "cam_ok": 2, "presence_danger": False})
    s = profil.charger_seuils()
    assert s.nom == "Boulangerie" and s.cam_ok == 2 and s.presence_danger is False


def test_validation_jaune_sous_rouge():
    with pytest.raises(ValueError):
        profil.valider({"temp_jaune": 40, "temp_rouge": 30})


def test_validation_gaz_coherent():
    with pytest.raises(ValueError):
        profil.valider({"gaz_jaune": 500, "gaz_rouge": 100})


def test_validation_temp_hors_plage():
    with pytest.raises(ValueError):
        profil.valider({"temp_jaune": 200, "temp_rouge": 300})


def test_suggestions_ajoutent_des_marges():
    sug = profil.suggerer({"temp_max": 30, "gaz_max": 120,
                           "personnes_max": 2, "presence_vue": True})
    assert sug["temp_jaune"] >= 32 and sug["temp_rouge"] > sug["temp_jaune"]
    assert sug["gaz_jaune"] >= 200
    assert sug["cam_ok"] == 2
    assert sug["presence_danger"] is False      # présence vue = considérée normale
