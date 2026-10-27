@echo off
setlocal
cd /d "%~dp0backend"
echo === Ideator ===

rem Busca un Python 3.10+ real. "python" puede ser el acceso directo de la Microsoft Store, que no sirve.
set "PY="
call :check py -3
if not defined PY call :check python
if not defined PY call :check "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY call :check "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY call :check "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY call :check "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not defined PY call :check "%ProgramFiles%\Python312\python.exe"
if not defined PY call :check "%USERPROFILE%\anaconda3\python.exe"
if not defined PY call :check "%USERPROFILE%\miniconda3\python.exe"
if not defined PY call :check "%ProgramData%\anaconda3\python.exe"
if not defined PY goto :nopython

:found
echo Usando Python: %PY%
if exist ".venv\Scripts\python.exe" goto :env
echo Creando entorno virtual...
"%PY%" -m venv .venv
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
echo Instalando dependencias, solo la primera vez. Tarda unos minutos...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

:env
if exist ".env" goto :run
copy "..\.env.example" ".env" >nul
echo.
echo Se creo backend\.env. Completa AZURE_OPENAI_API_KEY, guarda y vuelve a abrir iniciar.bat.
notepad ".env"
pause
exit /b 0

:run
set FRONTEND_DIST=%~dp0frontend\dist
set FRONTEND_URL=http://localhost:8000
set BACKEND_PUBLIC_URL=http://localhost:8000
set CORS_ORIGINS=http://localhost:8000
if not defined DATABASE_URL set DATABASE_URL=sqlite:///./ideator.db
echo.
echo Abriendo http://localhost:8000  - si no carga, espera unos segundos y recarga. Ctrl+C para detener.
start "" http://localhost:8000
".venv\Scripts\python.exe" -m uvicorn app.main:create_app --factory --port 8000
pause
exit /b 0

:nopython
echo.
echo No encontre Python 3.10 o superior en este computador.
where winget >nul 2>nul
if errorlevel 1 goto :manual
choice /c SN /m "Quieres que instale Python 3.12 ahora"
if errorlevel 2 goto :manual
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :check "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY call :check "%ProgramFiles%\Python312\python.exe"
if defined PY goto :found
echo.
echo Python quedo instalado. Cierra esta ventana y vuelve a abrir iniciar.bat.
pause
exit /b 0

:manual
echo Instala Python 3.12 desde https://www.python.org/downloads/ marcando "Add python.exe to PATH" y vuelve a abrir iniciar.bat.
pause
exit /b 1

:fail
echo.
echo Algo fallo. Saca una captura de esta ventana.
pause
exit /b 1

rem Ejecuta el candidato; si es Python 3.10+ guarda la ruta real del ejecutable en PY.
:check
%* -c "import sys; print(sys.executable) if sys.version_info >= (3, 10) else sys.exit(1)" > "%TEMP%\ideator_py.txt" 2>nul || exit /b 0
set /p PY=<"%TEMP%\ideator_py.txt"
exit /b 0
