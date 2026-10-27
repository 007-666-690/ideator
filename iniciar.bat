@echo off
setlocal
cd /d "%~dp0backend"
echo === Ideator ===

where python >nul 2>nul || (echo No se encontro Python. Instala Python 3.10+ o abre esto desde "Anaconda Prompt". & pause & exit /b 1)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || (echo Se necesita Python 3.10 o superior. & pause & exit /b 1)

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  python -m venv .venv || (pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  echo Instalando dependencias, solo la primera vez...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
)

if not exist ".env" (
  copy "..\.env.example" ".env" >nul
  echo.
  echo Se creo backend\.env. Abre ese archivo, completa AZURE_OPENAI_API_KEY y vuelve a ejecutar.
  notepad ".env"
  pause
  exit /b 0
)

set FRONTEND_DIST=%~dp0frontend\dist
set FRONTEND_URL=http://localhost:8000
set BACKEND_PUBLIC_URL=http://localhost:8000
set CORS_ORIGINS=http://localhost:8000
if not defined DATABASE_URL set DATABASE_URL=sqlite:///./ideator.db

echo.
echo Abriendo http://localhost:8000  (Ctrl+C para detener)
start "" http://localhost:8000
".venv\Scripts\python.exe" -m uvicorn app.main:create_app --factory --port 8000
pause
