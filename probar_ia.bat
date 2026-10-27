@echo off
rem Recorre Ideator completo con GPT-5 y guarda los .md en la carpeta "salida".
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (echo Primero ejecuta iniciar.bat & pause & exit /b 1)
set /p IDEA="Escribe la idea a probar: "
".venv\Scripts\python.exe" scripts\simular_caso.py --idea "%IDEA%" --salida "%~dp0salida" > "%~dp0salida-log.txt" 2>&1
type "%~dp0salida-log.txt"
echo.
echo Resultado en la carpeta "salida" y el registro en salida-log.txt
pause
