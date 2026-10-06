@echo off
rem ============================================================
rem  SENTINEL-X - Lanceur Windows (equivalent du Makefile)
rem  Usage :  make.bat install     puis    make.bat test-full
rem  (en PowerShell : .\make.bat install)
rem ============================================================
setlocal
set PY=venv\Scripts\python.exe

if "%1"==""            goto help
if "%1"=="help"        goto help
if "%1"=="install"     goto install
if "%1"=="check"       goto check
if "%1"=="test"        goto test
if "%1"=="test-full"   goto testfull
if "%1"=="api"         goto api
if "%1"=="train"       goto train
if "%1"=="detect"      goto detect
if "%1"=="replay"      goto replay
if "%1"=="detect-vision"     goto dvision
if "%1"=="detect-vision-sim" goto dvisionsim
if "%1"=="broker"      goto broker
if "%1"=="broker-stop" goto brokerstop
if "%1"=="simulate"    goto simulate
echo Cible inconnue : %1
goto help

:install
echo SENTINEL-X - Installation
where python >nul 2>&1 || (echo [X] Python introuvable - installe Python 3.8+ && exit /b 1)
python -c "import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)" || (echo [X] Python 3.8+ requis && exit /b 1)
for /f "delims=" %%v in ('python -V') do echo [OK] %%v
if not exist venv ( echo Creation du venv... & python -m venv venv )
echo Installation des dependances...
%PY% -m pip install --upgrade pip -q
%PY% -m pip install -r requirements.txt
where docker >nul 2>&1 && (echo [OK] Docker detecte) || (echo [!] Docker absent - requis pour MQTT et test-full)
if not exist data   mkdir data
if not exist logs   mkdir logs
if not exist models mkdir models
echo [OK] Dossiers data\ logs\ models\ prets
if not exist .env ( copy .env.example .env >nul && echo [OK] .env cree depuis .env.example ) else ( echo [OK] .env deja present )
%PY% scripts\check_env.py
echo.
echo SETUP COMPLETE - etape suivante :  make.bat test-full
goto end

:check
%PY% scripts\check_env.py
goto end

:test
%PY% scripts\healthcheck.py
goto end

:testfull
%PY% scripts\test_full_integration.py
goto end

:api
echo API sur http://localhost:3000/dashboard  (Ctrl+C pour arreter)
%PY% -m api.server
goto end

:train
%PY% -m predictive.main_brique6 train
goto end

:detect
%PY% -m predictive.main_brique6 detect
goto end

:replay
%PY% -m predictive.main_brique6 replay
goto end

:dvision
%PY% -m vision.detector
goto end

:dvisionsim
%PY% -m vision.detector --simulate
goto end

:broker
docker compose -f docker-compose.dev.yml up -d
echo [OK] Broker MQTT dev lance sur localhost:1883
goto end

:brokerstop
docker compose -f docker-compose.dev.yml down
goto end

:simulate
%PY% simulate\fake_sensors_esp32.py --simulate
goto end

:help
echo.
echo SENTINEL-X - commandes Windows :  make.bat ^<cible^>
echo   install            Setup complet (venv + deps + dossiers + .env)
echo   test-full          Test d'integration complet (demarre broker + API)
echo   test               Healthcheck rapide (in-process)
echo   check              Verifie les dependances
echo   api                Lance l'API (http://localhost:3000/dashboard)
echo   train              Entraine l'IA predictive (Brique 6)
echo   detect             Detection d'anomalies temps reel
echo   replay             Test IA autonome (sans DB ni broker)
echo   detect-vision      Vision (webcam reelle)
echo   detect-vision-sim  Vision en simulation (sans webcam)
echo   broker / broker-stop   Broker MQTT dev (Docker)
echo   simulate           Simulateur ESP32
echo.
echo   Premiere fois ?   make.bat install    puis    make.bat test-full
goto end

:end
endlocal
