@echo off
setlocal
rem Muestra las cuentas de Ideator guardadas en este computador y permite cambiar una contrasena.
rem El codigo Python va al final de este mismo archivo, despues de la marca.
echo === Cuentas de Ideator ===
if not exist "%~dp0backend\requirements.txt" goto :fuera
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" goto :noenv
".venv\Scripts\python.exe" -c "import sys; src = open(sys.argv[1], encoding='utf-8').read().split('#' + 'PY' + '#', 1)[1]; sys.argv = ['cuentas'] + sys.argv[2:]; exec(compile(src, 'cuentas', 'exec'))" "%~f0"
echo.
set "CORREO="
set /p CORREO=Para cambiar una contrasena escribe el correo de la cuenta, o aprieta Enter para salir: 
if not defined CORREO exit /b 0
".venv\Scripts\python.exe" -c "import sys; src = open(sys.argv[1], encoding='utf-8').read().split('#' + 'PY' + '#', 1)[1]; sys.argv = ['cuentas'] + sys.argv[2:]; exec(compile(src, 'cuentas', 'exec'))" "%~f0" --cambiar-clave "%CORREO%"
pause
exit /b 0

:fuera
echo Este archivo tiene que estar dentro de la carpeta ideator, al lado de la carpeta backend.
pause
exit /b 1

:noenv
echo Primero abre iniciar.bat una vez para que se instale Ideator.
pause
exit /b 1

#PY#
import argparse
import getpass
import os
import sys
from datetime import timezone
from pathlib import Path

sys.path.insert(0, os.getcwd())

from sqlalchemy import func, select

from app.db import SessionLocal, init_engine
from app.models import Project, ProjectMember, User
from app.security import hash_password


def fecha(d):
    if not d:
        return "nunca"
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone().strftime("%d-%m-%Y %H:%M")


def main():
    parser = argparse.ArgumentParser(prog="cuentas")
    parser.add_argument("--cambiar-clave", metavar="CORREO")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL", "sqlite:///./ideator.db")
    if url.startswith("sqlite:///") and not Path(url[len("sqlite:///"):]).exists():
        print("Todavia no hay base de datos: abre Ideator con iniciar.bat y crea tu cuenta ahi.")
        return
    init_engine(url)

    with SessionLocal() as db:
        if args.cambiar_clave:
            correo = args.cambiar_clave.strip().lower()
            user = db.scalar(select(User).where(func.lower(User.email) == correo))
            if not user:
                print(f"No existe una cuenta con el correo {correo}.")
                return
            clave = getpass.getpass("Nueva contrasena, minimo 8 caracteres (no se ve al escribir): ")
            if len(clave) < 8:
                print("Muy corta: debe tener al menos 8 caracteres. No se cambio nada.")
                return
            if clave != getpass.getpass("Repitela: "):
                print("No coinciden. No se cambio nada.")
                return
            user.password_hash = hash_password(clave)
            db.commit()
            print(f"Listo: la contrasena de {user.email} quedo cambiada. Ya puedes entrar a Ideator con ella.")
            return

        users = db.scalars(select(User).order_by(User.created_at)).all()
        if not users:
            print("No hay cuentas creadas. Abre http://localhost:8000 y usa 'Crear cuenta'.")
            return
        print(f"Cuentas guardadas en este computador ({len(users)}):")
        print()
        for u in users:
            proyectos = db.scalars(
                select(Project.name)
                .join(ProjectMember, ProjectMember.project_id == Project.id)
                .where(ProjectMember.user_id == u.id)
            ).all()
            print(f"  Correo:     {u.email}")
            print(f"  Nombre:     {u.name}")
            print(f"  Creada:     {fecha(u.created_at)}    Ultimo ingreso: {fecha(u.last_login_at)}")
            print(f"  Proyectos:  {', '.join(proyectos) if proyectos else 'ninguno'}")
            print()


main()
