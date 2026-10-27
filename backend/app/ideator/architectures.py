"""Las cinco arquitecturas base con las que trabaja Ideator.

Los escenarios A1 a A4 son los iniciales; A5 es el quinto escenario que agrega
el equipo. Para cambiarlos o ajustarlos basta con editar esta lista.
"""

from __future__ import annotations

from typing import Any

BASE_ARCHITECTURES: list[dict[str, Any]] = [
    {
        "id": "A1",
        "name": "Monolito modular en Python",
        "summary": "Una API FastAPI organizada por módulos, PostgreSQL y una SPA en React servida por Nginx. Todo corre con Docker Compose en una sola máquina virtual.",
        "when_to_use": [
            "MVP con lógica de negocio moderada y CRUD sobre datos relacionales",
            "Equipo pequeño que necesita entregar rápido y mantener todo en un repositorio",
            "Carga baja o media (cientos a pocos miles de usuarios)",
        ],
        "avoid_when": [
            "Se necesita escalar partes del sistema de forma independiente",
            "Hay muchos equipos trabajando en dominios separados",
        ],
        "persistence": "PostgreSQL 16 con migraciones Alembic",
        "backend": "Python 3.12 + FastAPI + SQLAlchemy 2 + Pydantic",
        "frontend": "React 18 + TypeScript + Vite, servido por Nginx",
        "communication": "REST/JSON sobre HTTPS; Nginx como proxy inverso hacia /api",
        "auth": "Login con correo y contraseña (argon2) + SSO OIDC (Microsoft Entra ID); sesión con JWT en cookie HttpOnly",
        "deployment": "Docker Compose (db, api, web) en una VM (Oracle Cloud Free Tier o Azure VM); secretos en Azure Key Vault",
        "observability": "Logs JSON con request_id, /health y /ready, métricas Prometheus en /metrics",
        "relational": True,
    },
    {
        "id": "A2",
        "name": "Full-stack TypeScript",
        "summary": "Next.js maneja interfaz y API (route handlers) en un solo proyecto TypeScript, con PostgreSQL vía Prisma y Auth.js para sesiones y SSO.",
        "when_to_use": [
            "Aplicaciones web con muchas pantallas y necesidad de renderizado en servidor o SEO",
            "Equipo que domina JavaScript/TypeScript y quiere un solo lenguaje",
        ],
        "avoid_when": [
            "Procesamiento pesado o tareas largas en segundo plano",
            "Integración con librerías de datos o IA que solo existen en Python",
        ],
        "persistence": "PostgreSQL 16 con Prisma ORM y migraciones de Prisma",
        "backend": "Next.js 14 (App Router, route handlers) sobre Node.js 20 / Deno",
        "frontend": "React 18 con Next.js + TypeScript",
        "communication": "Server actions y route handlers REST/JSON en el mismo origen",
        "auth": "Auth.js con proveedor OIDC (Microsoft Entra ID) y credenciales; sesión en cookie cifrada",
        "deployment": "Contenedor Docker en Azure App Service / Container Apps o Vercel; base de datos gestionada",
        "observability": "Logs estructurados (pino), /api/health, OpenTelemetry para trazas",
        "relational": True,
    },
    {
        "id": "A3",
        "name": "Serverless con Backend-as-a-Service",
        "summary": "Una SPA en React se conecta a Supabase (PostgreSQL, Auth con SSO, Storage y Edge Functions). La autorización se aplica con Row Level Security en la base de datos.",
        "when_to_use": [
            "Prototipos rápidos con poca lógica de servidor propia",
            "Necesidad de tiempo real (suscripciones) y almacenamiento de archivos sin operar servidores",
        ],
        "avoid_when": [
            "Reglas de negocio complejas o transaccionales en el servidor",
            "Restricciones que impiden depender de un proveedor externo",
        ],
        "persistence": "PostgreSQL gestionado por Supabase con políticas Row Level Security",
        "backend": "Supabase (API REST automática) + Edge Functions (Deno/TypeScript) para lógica propia",
        "frontend": "React 18 + TypeScript + Vite, desplegado como sitio estático",
        "communication": "Cliente supabase-js (REST/Realtime) sobre HTTPS",
        "auth": "Supabase Auth con proveedor OIDC/SAML (Azure AD) y correo; JWT de Supabase",
        "deployment": "Supabase Cloud + hosting estático (Azure Static Web Apps / Netlify)",
        "observability": "Logs y métricas del panel de Supabase; health check de Edge Functions",
        "relational": True,
    },
    {
        "id": "A4",
        "name": "Servicios independientes en contenedores",
        "summary": "Un API gateway enruta a servicios separados por dominio (FastAPI o Node), cada uno con su esquema en PostgreSQL. Los eventos asíncronos van por una cola (RabbitMQ) y Redis se usa como caché.",
        "when_to_use": [
            "Dominios claramente separados que evolucionan o escalan por separado",
            "Procesos asíncronos o integraciones lentas que no deben bloquear al usuario",
        ],
        "avoid_when": [
            "MVP pequeño o equipo de pocas personas: la complejidad operacional no se justifica",
        ],
        "persistence": "PostgreSQL 16 con un esquema por servicio; Redis para caché",
        "backend": "Servicios FastAPI/Node.js detrás de un gateway (Traefik o Nginx); RabbitMQ para eventos",
        "frontend": "React 18 + TypeScript + Vite",
        "communication": "REST/JSON vía gateway; eventos asíncronos por cola",
        "auth": "Gateway valida el JWT emitido tras SSO OIDC (Microsoft Entra ID); cada servicio verifica permisos",
        "deployment": "Docker Compose en desarrollo; Kubernetes o Azure Container Apps en producción",
        "observability": "OpenTelemetry (trazas distribuidas), Prometheus + Grafana, logs centralizados, health checks por servicio",
        "relational": True,
    },
    {
        "id": "A5",
        "name": "Aplicación con agentes de IA (quinto escenario)",
        "summary": "Backend FastAPI que orquesta agentes con Google ADK sobre un modelo gestionado (Azure OpenAI o Vertex AI Gemini), PostgreSQL con pgvector para memoria y búsqueda semántica, y un worker para tareas largas.",
        "when_to_use": [
            "El valor central del producto depende de IA generativa (chat, generación, clasificación, búsqueda semántica)",
            "Se requieren tareas largas de IA que no deben bloquear la interfaz",
        ],
        "avoid_when": [
            "El producto no usa IA de forma central: agrega costo y latencia sin beneficio",
        ],
        "persistence": "PostgreSQL 16 + pgvector; migraciones Alembic",
        "backend": "Python 3.12 + FastAPI + Google ADK; worker asíncrono (Celery/RQ con Redis)",
        "frontend": "React 18 + TypeScript + Vite con respuestas en streaming (SSE)",
        "communication": "REST/JSON + Server-Sent Events para respuestas de IA; cola para trabajos largos",
        "auth": "Correo y contraseña + SSO OIDC (Microsoft Entra ID); JWT en cookie HttpOnly; permisos por recurso en el backend",
        "deployment": "Docker Compose (db, api, worker, redis, web); secretos y claves del modelo en Azure Key Vault",
        "observability": "Logs JSON, métricas de latencia y tokens por llamada al modelo, trazas de agentes, /health y /ready",
        "relational": True,
    },
]

ARCHITECTURE_IDS = {a["id"] for a in BASE_ARCHITECTURES}


def get_architecture(scenario_id: str) -> dict[str, Any] | None:
    return next((a for a in BASE_ARCHITECTURES if a["id"] == scenario_id), None)
