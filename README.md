# Ideator

Ideator acompaña a un equipo desde una idea suelta hasta una especificación de software completa, consistente y lista para que **otra IA la implemente sin tener que inventar decisiones**. El resultado son dos archivos Markdown: `especificacion-producto.md` y `arquitectura.md`.

Proyecto semestral de **TICS420 Programación Profesional** (UAI, 2026).

## Cómo funciona

| Etapa | Qué hace Ideator | Qué hace el equipo |
|---|---|---|
| 1. Definición del producto | Conversa por rondas: arma la definición (problema, usuarios, MVP, recorrido, requisitos, reglas, casos borde) y pregunta lo que falta. Marca como **bloqueante** toda decisión que cambia datos, API, pantallas, permisos o arquitectura. | Responde, delega decisiones («Que decida Ideator») y acepta los supuestos menores. No puede aprobar con bloqueantes abiertas. |
| 2. Modelo de datos | Propone el modelo físico PostgreSQL (tipos, PK, FK, únicos, índices, CHECK) con diagrama ER y DDL. | Edita tablas y columnas en un editor, pide cambios a la IA y aprueba. |
| 3. Backend y API | Especifica cada endpoint: método, ruta, parámetros, cuerpo, respuestas y errores (400/401/403/404/409/422…). | Revisa, edita o pide cambios y aprueba. |
| 4. Pantallas | Bocetos de cada pantalla, acciones ligadas a endpoints y mapa de navegación. | Revisa y aprueba. |
| 5. Arquitectura | Evalúa las 5 arquitecturas base (A1–A4 iniciales + **A5, agentes de IA**, el quinto escenario del grupo) y detalla la elegida: stack, SSO, autorización, variables de entorno, despliegue y observabilidad. | Elige el escenario y aprueba. |
| 6. Revisión final | Validación automática de todo el proyecto + revisión de consistencia por IA. Los hallazgos críticos bloquean. | Corrige o acepta hallazgos con justificación. |
| Documentos | Genera los dos `.md` de forma **determinista** desde lo aprobado: los mismos nombres, rutas y códigos en todas las secciones, más DDL, diagramas Mermaid y checklist de verificación. | Descarga los archivos (o el .zip). |

Cada etapa usa como contexto lo aprobado antes, y validadores deterministas revisan la consistencia en cada paso: FKs que apuntan a tablas reales, endpoints con 401/403/404 cuando corresponde, requisitos sin endpoint, acciones de pantalla que llaman endpoints inexistentes, pasos del recorrido sin pantalla, etc.

## Colaboración, seguridad y trazabilidad

- **Multiusuario** con login por correo y contraseña (argon2) y **SSO OpenID Connect** (Microsoft Entra ID y Google).
- Proyectos **privados por defecto**. Se accede solo por invitación, con roles dueño, editor y lector. La autorización se valida **siempre en el backend**: sin sesión → 401, sin permiso → 403, inexistente → 404.
- **Control de concurrencia optimista**: cada etapa tiene versión, y si alguien guardó antes la API responde 409 con quién y cuándo.
- **Trazabilidad**: historial de versiones por etapa (autor y origen IA/usuario), registro de actividad y quién respondió cada pregunta.
- Sesión en cookie HttpOnly + SameSite, límite de intentos de login, secretos por variables de entorno o **Azure Key Vault**.
- **Observabilidad**: logs JSON con `request_id`, métricas Prometheus en `/metrics`, `/api/health` y `/api/ready`.

## Arquitectura

```
frontend (React + TypeScript + Vite) ──/api──▶ backend (FastAPI + SQLAlchemy) ──▶ PostgreSQL
                                                    │
                                                    └──▶ GPT-5 (Azure OpenAI, salidas estructuradas)
```

- `backend/app/ideator/`: el motor. `schemas.py` (estructura de cada etapa), `prompts.py`, `engine.py` (flujo y estados), `validation.py`, `render.py` (Mermaid y DDL), `documents.py` (Markdown final), `architectures.py` (las 5 arquitecturas base), `llm.py` (cliente GPT-5) y `fake.py` (IA simulada para pruebas y demo).
- `backend/app/routers/`: API REST. La documentación interactiva queda en `/api/docs`.
- `frontend/src/`: interfaz.

## Ejecutar

### Con Docker (recomendado)

```bash
cp .env.example .env        # completa AZURE_OPENAI_API_KEY y SECRET_KEY
docker compose up --build   # http://localhost:8080
```

### En Windows sin Docker

Doble clic en `iniciar.bat`. La primera vez crea el entorno e instala las dependencias (requiere Python 3.10 o superior, por ejemplo el de Anaconda). Después abre http://localhost:8000.

### Desarrollo

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend && uvicorn app.main:create_app --factory --reload      # API en :8000
cd frontend && npm install && npm run dev                          # interfaz en :5173
```

Con `LLM_PROVIDER=fake` todo funciona sin IA real, usando un caso de ejemplo («ReservaCancha»).

## Pruebas

```bash
cd backend && pytest                      # unitarias + funcionales (58)
python e2e/walkthrough.py URL capturas    # recorrido end-to-end en navegador (Playwright)
python backend/scripts/simular_caso.py --idea "..."   # caso completo con GPT-5 real, guarda los .md
```

- **Unitarias**: validadores, DDL y diagramas, documentos, seguridad (hash, JWT, rate limit) y cliente de IA (esquema estricto, reintento, errores).
- **Funcionales (API)**: autenticación, privacidad 401/403/404, invitaciones y roles, flujo completo hasta los documentos, conflictos 409, caída del modelo (503 sin perder respuestas) y bloqueo de generación concurrente.
- **End-to-end**: recorrido completo en Chromium, también en vista móvil.

## Configurar SSO con Microsoft Entra ID

1. Azure Portal → Entra ID → Registros de aplicaciones → Nuevo registro.
2. URI de redirección (Web): `<BACKEND_PUBLIC_URL>/api/auth/sso/microsoft/callback`.
3. Crea un secreto de cliente y completa `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` y `MICROSOFT_TENANT` (el id del tenant, o `organizations`).

Google es análogo, con el callback `/api/auth/sso/google/callback`.

## Limitaciones conocidas

- Los correos no se verifican: una invitación la acepta quien inicie sesión con ese correo. En producción conviene restringir el SSO a un tenant y verificar el correo.
- El esquema se crea al iniciar (`create_all`). Para cambios de esquema en producción se recomienda agregar migraciones con Alembic.

## Proceso de trabajo (Jira + GitHub)

- Cada épica de Jira corresponde a una rama `feature/<epica>`. Las ramas se integran a `develop` por pull request y `develop` se publica en `main`.
- Commits con el formato `tipo: SCRUM-N descripción` (`feat`, `fix`, `docs`, `style`, `test`, `chore`), siempre asociados a una tarea.
