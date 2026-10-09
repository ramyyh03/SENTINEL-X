"""Tests de la fusion multi-capteurs (predictive/correlation.py).

Seuils décidés : température jaune > 28°C / rouge > 32°C ·
gaz jaune ≥ 100 / rouge ≥ 300 · présence (PIR ou caméra) = jaune.
"""
from predictive.correlation import analyser, humidex


def _v(temp=22, hum=50, gas=0, presence=0):
    return {"temp": temp, "humidity": hum, "gas": gas, "presence": presence}


# ---- GAZ ------------------------------------------------------------------- #
def test_gaz_rouge_fuite():
    s = analyser(_v(gas=300), {"dtemp": 0, "dhum": 0}, cam_personnes=0)
    assert s.nom == "FUITE_GAZ" and s.severite == "CRITICAL"


def test_gaz_jaune_leger():
    s = analyser(_v(gas=100), {}, cam_personnes=0)
    assert s.nom == "GAZ_FAIBLE" and s.severite == "WARNING"


def test_gaz_sous_seuil_reste_normal():
    s = analyser(_v(gas=99), {"dtemp": 0, "dhum": 0}, cam_personnes=0)
    assert s.nom == "NORMAL"


def test_incendie_gaz_eleve_plus_chaleur():
    s = analyser(_v(gas=400, temp=35), {"dtemp": 4, "dhum": -6}, cam_personnes=0)
    assert s.nom == "INCENDIE" and s.severite == "CRITICAL"


# ---- TEMPÉRATURE ----------------------------------------------------------- #
def test_temp_rouge_surchauffe():
    s = analyser(_v(temp=33), {}, cam_personnes=0)
    assert s.nom == "SURCHAUFFE" and s.severite == "CRITICAL"


def test_temp_jaune_chaleur():
    s = analyser(_v(temp=29), {}, cam_personnes=0)
    assert s.nom == "CHALEUR" and s.severite == "WARNING"


def test_temp_28_pile_reste_normal():
    # 28°C = limite basse : on ne colore qu'AU-DESSUS de 28.
    s = analyser(_v(temp=28), {}, cam_personnes=0)
    assert s.nom == "NORMAL"


# ---- PRÉSENCE (PIR / caméra) ---------------------------------------------- #
def test_presence_pir_est_warning():
    s = analyser(_v(presence=1), {}, cam_personnes=0)
    assert s.nom == "PRESENCE" and s.severite == "WARNING"


def test_presence_camera_une_personne_est_warning():
    s = analyser(_v(), {}, cam_personnes=1)
    assert s.nom == "PRESENCE" and s.severite == "WARNING"


def test_foule_camera_deux_personnes_est_critical():
    s = analyser(_v(), {}, cam_personnes=2)
    assert s.nom == "FOULE" and s.severite == "CRITICAL"


# ---- NORMAL / humidex ------------------------------------------------------ #
def test_normal_quand_tout_va_bien():
    s = analyser(_v(), {"dtemp": 0, "dhum": 0}, cam_personnes=0)
    assert s.nom == "NORMAL"


def test_humidex_augmente_avec_humidite():
    assert humidex(30, 80) > humidex(30, 30)
