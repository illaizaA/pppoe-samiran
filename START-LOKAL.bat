@echo off
setlocal
cd /d "%~dp0"
title PPPoE Monitoring
echo Menyiapkan aplikasi. Tunggu sampai alamat website muncul.
echo.
python -c "import flask, dotenv" >nul 2>&1
if not errorlevel 1 goto existing
if exist ".venv\Scripts\python.exe" goto install
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Buka alamat website yang muncul di bawah melalui browser.
echo Biarkan jendela ini terbuka selama aplikasi dipakai.
".venv\Scripts\python.exe" app.py
goto done
:existing
echo Aplikasi siap. Buka alamat website yang muncul di bawah.
python app.py
goto done
:failed
echo.
echo Persiapan gagal. Kirim tulisan error di jendela ini untuk diperiksa.
:done
pause
