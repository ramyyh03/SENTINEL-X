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
if "%1"=="test-unit"   goto testunit
if "%1"=="test-materiel" goto testmateriel
if "%1"=="check-materiel" goto checkmateriel
if "%1"=="monitor-esp32" goto monitoresp32
if "%1"=="config-esp32" goto configesp32
if "%1"=="setup-2fa"   goto setup2fa
if "%1"=="reset-db"    goto resetdb
if "%1"=="run-all"     goto runall
if "%1"=="api"         goto api
if "%1"=="api-stop"    goto apistop
if "%1"=="api-logs"    goto apilogs
if "%1"=="train-ensemble" goto trainensemble
if "%1"=="ollama-check"   goto ollamacheck
if "%1"=="security-audit" goto securityaudit
if "%1"=="security-fix"   goto securityfix
if "%1"=="app"         goto app
if "%1"=="start"       goto start
if "%1"=="stop"        goto stop
if "%1"=="flash-base"  goto flashbase
if "%1"=="flash-leds"  goto flashleds
if "%1"=="flash-full"  goto flashfull
if "%1"=="test-ensemble"  goto testensemble
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

:testunit
%PY% -m pytest tests\ -q
goto end

:testmateriel
%PY% scripts\test_materiel.py
goto end

:checkmateriel
%PY% scripts\test_materiel.py --scan
goto end

:monitoresp32
%PY% scripts\esp32_monitor.py
goto end

:configesp32
%PY% scripts\config_esp32.py
goto end

:setup2fa
%PY% scripts\setup_2fa.py
goto end

:resetdb
%PY% scripts\reset_db.py
goto end

:runall
echo Lancement du systeme complet SENTINEL-X (plusieurs fenetres)...
docker compose -f docker-compose.dev.yml up -d
start "SENTINEL - API" cmd /k "%PY% -m api.server"
start "SENTINEL - Ingestion MQTT" cmd /k "%PY% scripts\mqtt_client.py"
start "SENTINEL - Detection" cmd /k "%PY% -m predictive.main_brique6 detect"
start "SENTINEL - Vision webcam" cmd /k "%PY% -m vision.detector --camera 1"
echo.
echo   Dashboard alertes : http://localhost:3000/dashboard
echo   Capteurs en direct: http://localhost:3000/live
echo   Camera (vision)   : http://localhost:3000/camera
echo.
echo   (4 fenetres ouvertes ; ferme-les avec Ctrl+C pour tout arreter)
goto end

:api
echo API sur http://localhost:3000/dashboard  (Ctrl+C pour arreter)
%PY% -m api.server
goto end

:apistop
echo Arret de l'API (port 3000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
echo [OK] API arretee (si elle tournait).
goto end

:apilogs
powershell -NoProfile -Command "Get-Content logs\api.log -Wait -Tail 20"
goto end

:trainensemble
%PY% scripts\train_ensemble.py
goto end

:ollamacheck
%PY% scripts\ollama_health_check.py
goto end

:securityaudit
%PY% scripts\security_audit.py --explain
goto end

:securityfix
%PY% scripts\security_audit.py --fix
goto end

:app
%PY% -m app.sentinel_app
goto end

:start
%PY% scripts\launch_all.py
goto end

:stop
%PY% scripts\launch_all.py --stop
goto end

:flashbase
echo === Flash ESP32 : firmware de base (capteurs + OLED) ===
set "PIO=pio"
if exist "%USERPROFILE%\.platformio\penv\Scripts\pio.exe" set "PIO=%USERPROFILE%\.platformio\penv\Scripts\pio.exe"
if exist "venv\Scripts\pio.exe" set "PIO=venv\Scripts\pio.exe"
echo PlatformIO utilise : %PIO%
"%PIO%" run -d firmware -e esp32dev-secrets -t upload
if errorlevel 1 echo [X] Echec. PlatformIO installe ? -^> %PY% -m pip install platformio   (puis reessaie)
goto end

:flashleds
echo === Flash ESP32 : capteurs + OLED + LEDs de statut ===
set "PIO=pio"
if exist "%USERPROFILE%\.platformio\penv\Scripts\pio.exe" set "PIO=%USERPROFILE%\.platformio\penv\Scripts\pio.exe"
if exist "venv\Scripts\pio.exe" set "PIO=venv\Scripts\pio.exe"
echo PlatformIO utilise : %PIO%
"%PIO%" run -d firmware -e esp32dev-secrets-leds -t upload
if errorlevel 1 echo [X] Echec. PlatformIO installe ? -^> %PY% -m pip install platformio   (puis reessaie)
goto end

:flashfull
echo === Flash ESP32 : COMPLET (OLED-alertes + LEDs + HMAC) ===
set "PIO=pio"
if exist "%USERPROFILE%\.platformio\penv\Scripts\pio.exe" set "PIO=%USERPROFILE%\.platformio\penv\Scripts\pio.exe"
if exist "venv\Scripts\pio.exe" set "PIO=venv\Scripts\pio.exe"
echo PlatformIO utilise : %PIO%
"%PIO%" run -d firmware -e esp32dev-full -t upload
if errorlevel 1 echo [X] Echec. PlatformIO installe ? -^> %PY% -m pip install platformio   (puis reessaie)
goto end

:testensemble
%PY% -m pytest tests\test_ensemble.py -q
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
echo   run-all            Lance TOUT (broker + API + ingestion + detection + vision)
echo   api / api-stop / api-logs   API : lancer / arreter / logs
echo   test / test-full   Healthcheck rapide / Test d'integration complet
echo   config-esp32       Prepare secrets.h de l'ESP32 (IP auto) et l'ouvre
echo   monitor-esp32      Lit le port serie de l'ESP32 (mesures en direct)
echo   app                APPLI bureau : fenetre unique (analyse + dashboard + webcam)
echo   start              Lance tout en fond + ouvre le cockpit dans le navigateur
echo   stop               Arrete tout ce que `start`/`app` a lance
echo   flash-base         Flashe l'ESP32 : capteurs + OLED (verifie le materiel)
echo   flash-leds         Flashe l'ESP32 : capteurs + OLED + LEDs de statut
echo   flash-full         Flashe l'ESP32 : COMPLET (OLED-alertes + LEDs + HMAC)
echo   setup-2fa          Cree un compte dashboard (login + 2FA)
echo   security-audit     Suis-je securise ? (secrets, auth, XSS, MQTT, API)
echo   security-fix       Applique les correctifs de securite surs
echo   reset-db           Vide la base (enleve les donnees de test)
echo   train / detect / replay     IA predictive (Brique 6)
echo   detect-vision / -sim        Vision webcam (reelle / simulee)
echo   test-materiel / check-materiel   Webcam + ESP32
echo   broker / broker-stop        Broker MQTT dev (Docker)
echo   simulate / check            Simulateur ESP32 / verif deps
echo.
echo   Premiere fois ?   make.bat install    puis    make.bat app
goto end

:end
endlocal
