"""Modelo de IA simulado: respuestas deterministas para pruebas y modo demo.

Siempre desarrolla el mismo caso de ejemplo («ReservaCancha»: reservas de canchas
de un club deportivo), con una primera ronda de preguntas (dos bloqueantes) y una
segunda ronda que completa la definición.
"""

from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel

from .llm import LLMClient

T = TypeVar("T", bound=BaseModel)


def _f(name, type_, required=True, description="", validation=""):
    return {"name": name, "type": type_, "required": required, "description": description, "validation": validation}


def _r(status, description, body_kind="error", fields=None):
    return {"status": status, "description": description, "body_kind": body_kind, "fields": fields or []}


def _p(name, location, type_, required=True, description=""):
    return {"name": name, "location": location, "type": type_, "required": required, "description": description}


def _col(name, type_, nullable=False, pk=False, unique=False, default=None, fk=None, description=""):
    return {
        "name": name,
        "type": type_,
        "nullable": nullable,
        "primary_key": pk,
        "unique": unique,
        "default": default,
        "foreign_key": fk,
        "description": description,
    }


def _fk(table, on_delete="CASCADE", column="id"):
    return {"table": table, "column": column, "on_delete": on_delete}


def _id():
    return _col("id", "uuid", pk=True, description="Identificador")


def _created():
    return _col("created_at", "timestamptz", default="now()", description="Fecha de creación")


R401 = _r(401, "Sin sesión o sesión expirada")
R403 = _r(403, "El usuario no tiene permiso")
R422 = _r(422, "Datos inválidos")

BRIEF_ROUND_1 = {
    "product_name": "ReservaCancha",
    "one_liner": "Reserva de canchas deportivas en línea para un club y sus socios",
    "problem": "Los socios reservan canchas por WhatsApp y teléfono; las reservas se pierden o se duplican y nadie conoce la ocupación real.",
    "context": "Club deportivo con canchas de tenis y pádel que hoy gestiona las reservas en una planilla manejada por la secretaría.",
    "current_situation": "",
    "desired_improvement": "",
    "user_types": [],
    "expected_outcomes": [],
    "mvp_in_scope": [],
    "mvp_out_of_scope": [],
    "main_journey": {"name": "", "actor": "", "goal": "", "preconditions": [], "steps": [], "success_result": ""},
    "functional_requirements": [],
    "business_rules": [],
    "technical_constraints": [],
    "integrations": [],
    "security_requirements": [],
    "non_functional_requirements": [],
    "edge_cases": [],
    "assumptions": [],
    "decisions": [],
    "glossary": [],
}

QUESTIONS_ROUND_1 = [
    {
        "text": "¿Qué tipos de usuario tendrá el producto y qué puede hacer cada uno?",
        "rationale": "Define los roles, los permisos de cada endpoint y qué pantallas ve cada persona.",
        "blocking": True,
        "affects": ["datos", "backend", "interfaz", "seguridad"],
        "options": ["Solo socios", "Socios y un administrador del club", "Socios, administrador y profesores"],
        "section": "user_types",
    },
    {
        "text": "¿El MVP incluye pagar la reserva en línea?",
        "rationale": "Un pago en línea agrega tablas de pagos, una integración externa y estados de reserva pendientes.",
        "blocking": True,
        "affects": ["datos", "backend", "arquitectura", "alcance"],
        "options": ["Sí, se paga al reservar", "No, se paga presencial o va en la mensualidad"],
        "section": "mvp_in_scope",
    },
    {
        "text": "¿Cuánto dura cada bloque de reserva?",
        "rationale": "Determina cómo se arma la grilla de disponibilidad.",
        "blocking": False,
        "affects": ["negocio"],
        "options": ["60 minutos", "90 minutos"],
        "section": "business_rules",
    },
]

BRIEF_COMPLETE = {
    "product_name": "ReservaCancha",
    "one_liner": "Reserva de canchas deportivas en línea para un club y sus socios",
    "problem": "Los socios reservan canchas por WhatsApp y teléfono; las reservas se pierden o se duplican y nadie conoce la ocupación real.",
    "context": "Club deportivo con 6 canchas (tenis y pádel) y cerca de 400 socios. La secretaría administra las reservas en una planilla compartida.",
    "current_situation": "La secretaría anota cada reserva a mano; no hay confirmación para el socio ni historial confiable.",
    "desired_improvement": "Que el socio vea la disponibilidad y reserve en menos de un minuto sin choques de horario, y que el administrador gestione canchas y bloqueos.",
    "user_types": [
        {
            "id": "U1",
            "name": "Socio",
            "description": "Persona inscrita en el club que reserva canchas",
            "goals": ["Reservar rápido un bloque libre", "Ver y cancelar sus reservas"],
            "permissions": ["Ver disponibilidad", "Crear reservas propias", "Cancelar sus reservas hasta 2 horas antes"],
            "restrictions": ["No ve los datos de otros socios", "No administra canchas ni bloqueos"],
        },
        {
            "id": "U2",
            "name": "Administrador del club",
            "description": "Personal de secretaría que administra canchas y reservas",
            "goals": ["Mantener actualizadas las canchas y sus bloqueos", "Ver la ocupación diaria"],
            "permissions": ["Crear y editar canchas", "Bloquear horarios", "Ver todas las reservas", "Cancelar cualquier reserva"],
            "restrictions": ["No reserva a nombre de un socio en el MVP"],
        },
    ],
    "expected_outcomes": [
        {"id": "R1", "description": "Reservas sin choques de horario", "metric": "Reservas duplicadas por mes", "target": "0"},
        {"id": "R2", "description": "Menos trabajo manual de secretaría", "metric": "Reservas gestionadas a mano", "target": "-80% en 3 meses"},
    ],
    "mvp_in_scope": [
        {"id": "A1", "description": "Registro e inicio de sesión con correo y contraseña o con Google", "reason": "Identificar a cada socio"},
        {"id": "A2", "description": "Disponibilidad por fecha y deporte", "reason": "Valor central"},
        {"id": "A3", "description": "Reserva de un bloque de 60 minutos", "reason": "Valor central"},
        {"id": "A4", "description": "Mis reservas y cancelación", "reason": "Evita reservas abandonadas"},
        {"id": "A5", "description": "Administración de canchas, bloqueos y reservas del día", "reason": "Operación del club"},
    ],
    "mvp_out_of_scope": [
        {"id": "X1", "description": "Pago en línea", "reason": "El cobro va en la mensualidad"},
        {"id": "X2", "description": "Notificaciones por WhatsApp", "reason": "Se evaluará después del MVP"},
        {"id": "X3", "description": "Aplicación móvil nativa", "reason": "La web responsive cubre el uso desde celular"},
    ],
    "main_journey": {
        "name": "Reservar una cancha",
        "actor": "U1",
        "goal": "Reservar un bloque libre",
        "preconditions": ["El socio tiene una cuenta activa"],
        "steps": [
            {"number": 1, "actor": "U1", "action": "Inicia sesión", "system_response": "Muestra la disponibilidad del día"},
            {"number": 2, "actor": "U1", "action": "Elige fecha y deporte", "system_response": "Muestra la grilla de bloques por cancha"},
            {"number": 3, "actor": "U1", "action": "Selecciona un bloque libre", "system_response": "Muestra el resumen de la reserva"},
            {"number": 4, "actor": "U1", "action": "Confirma la reserva", "system_response": "Crea la reserva si el bloque sigue libre y muestra la confirmación"},
            {"number": 5, "actor": "U1", "action": "Revisa Mis reservas", "system_response": "Lista la reserva confirmada"},
        ],
        "success_result": "La reserva queda confirmada y el bloque deja de estar disponible para otros socios.",
    },
    "functional_requirements": [
        {
            "id": "RF-01",
            "title": "Registro e inicio de sesión",
            "description": "El socio crea su cuenta con correo y contraseña o ingresa con Google.",
            "user_types": ["U1", "U2"],
            "priority": "must",
            "acceptance_criteria": [
                "Dado un correo no registrado, cuando se registra con una contraseña de 8 o más caracteres, entonces se crea la cuenta con rol U1",
                "Dadas credenciales inválidas, cuando intenta ingresar, entonces se rechaza con un mensaje genérico",
                "Cuando ingresa con Google por primera vez, entonces se crea su cuenta con rol U1",
            ],
        },
        {
            "id": "RF-02",
            "title": "Ver disponibilidad",
            "description": "Muestra los bloques libres y ocupados de cada cancha para una fecha y deporte.",
            "user_types": ["U1", "U2"],
            "priority": "must",
            "acceptance_criteria": ["Dada una fecha, cuando se consulta, entonces se ven los bloques de 08:00 a 22:00 de cada cancha activa con su estado"],
        },
        {
            "id": "RF-03",
            "title": "Reservar un bloque",
            "description": "El socio reserva un bloque libre de 60 minutos.",
            "user_types": ["U1"],
            "priority": "must",
            "acceptance_criteria": [
                "Dado un bloque libre, cuando el socio confirma, entonces la reserva queda confirmada",
                "Dado un bloque tomado o bloqueado, cuando confirma, entonces se rechaza y se actualiza la grilla",
                "Dado un socio con 2 reservas futuras, cuando intenta otra, entonces se rechaza",
            ],
        },
        {
            "id": "RF-04",
            "title": "Ver y cancelar mis reservas",
            "description": "El socio ve sus reservas y cancela hasta 2 horas antes del inicio.",
            "user_types": ["U1"],
            "priority": "must",
            "acceptance_criteria": ["Dada una reserva que empieza en más de 2 horas, cuando la cancela, entonces queda cancelada y el bloque se libera"],
        },
        {
            "id": "RF-05",
            "title": "Gestionar canchas",
            "description": "El administrador crea, edita, activa y desactiva canchas.",
            "user_types": ["U2"],
            "priority": "must",
            "acceptance_criteria": ["Cuando desactiva una cancha, entonces deja de aparecer en la disponibilidad"],
        },
        {
            "id": "RF-06",
            "title": "Bloquear horarios",
            "description": "El administrador bloquea una cancha en un rango de horas (mantención o torneo).",
            "user_types": ["U2"],
            "priority": "should",
            "acceptance_criteria": ["Dado un bloqueo creado, cuando un socio consulta ese horario, entonces aparece como no disponible"],
        },
        {
            "id": "RF-07",
            "title": "Ver reservas del día",
            "description": "El administrador ve todas las reservas de una fecha y puede cancelarlas.",
            "user_types": ["U2"],
            "priority": "should",
            "acceptance_criteria": ["Dada una fecha, cuando la consulta, entonces ve cancha, hora, socio y estado de cada reserva"],
        },
    ],
    "business_rules": [
        {"id": "RN-01", "description": "Los bloques son de 60 minutos entre las 08:00 y las 22:00 (hora de Chile)."},
        {"id": "RN-02", "description": "Un socio puede tener como máximo 2 reservas futuras confirmadas."},
        {"id": "RN-03", "description": "Un socio puede cancelar hasta 2 horas antes del inicio; el administrador, siempre."},
        {"id": "RN-04", "description": "No puede haber dos reservas confirmadas para la misma cancha y bloque."},
        {"id": "RN-05", "description": "No se puede reservar un bloque que se cruce con un bloqueo de la cancha."},
    ],
    "technical_constraints": ["Aplicación web responsive; el uso principal es desde el celular"],
    "integrations": [
        {
            "name": "Google (inicio de sesión)",
            "purpose": "SSO para los socios",
            "required_for_mvp": True,
            "failure_behavior": "Se muestra un aviso y el socio puede ingresar con correo y contraseña",
        }
    ],
    "security_requirements": [
        "Contraseñas guardadas con hash",
        "Solo el dueño de la reserva o un administrador puede cancelarla",
        "Los datos personales de los socios solo los ve el administrador",
    ],
    "non_functional_requirements": ["La disponibilidad responde en menos de 1 segundo", "Funciona en navegadores móviles actuales"],
    "edge_cases": [
        {"id": "CB-01", "category": "falta_informacion", "scenario": "El socio intenta confirmar sin elegir un bloque", "expected_behavior": "El botón Confirmar queda deshabilitado y se indica qué falta"},
        {"id": "CB-02", "category": "accion_fallida", "scenario": "El bloque fue tomado por otro socio antes de confirmar", "expected_behavior": "Se responde 409 y se muestra la grilla actualizada"},
        {"id": "CB-03", "category": "sin_permisos", "scenario": "Un socio intenta cancelar una reserva ajena", "expected_behavior": "Se responde 403 y se muestra 'No puedes cancelar esta reserva'"},
        {"id": "CB-04", "category": "recurso_inexistente", "scenario": "Se abre una reserva o cancha que no existe", "expected_behavior": "Se responde 404 y se muestra 'No encontrado'"},
        {"id": "CB-05", "category": "datos_invalidos", "scenario": "Se envía una fecha pasada o fuera del horario", "expected_behavior": "Se responde 422 indicando el campo inválido"},
        {"id": "CB-06", "category": "dependencia_caida", "scenario": "Google no responde durante el inicio de sesión", "expected_behavior": "Se muestra un aviso y la opción de ingresar con correo"},
        {"id": "CB-07", "category": "concurrencia", "scenario": "Dos socios confirman el mismo bloque al mismo tiempo", "expected_behavior": "Solo una reserva se crea; la otra recibe 409"},
    ],
    "assumptions": [
        {"id": "S-01", "description": "La interfaz está solo en español", "accepted": False},
        {"id": "S-02", "description": "Todas las horas se manejan en la zona horaria America/Santiago", "accepted": False},
    ],
    "decisions": [
        {"id": "D-01", "topic": "Tipos de usuario", "decision": "Socio (U1) y Administrador del club (U2)", "source": "usuario"},
        {"id": "D-02", "topic": "Pagos", "decision": "Sin pago en línea en el MVP", "source": "usuario"},
        {"id": "D-03", "topic": "Duración de bloques", "decision": "Bloques de 60 minutos", "source": "usuario"},
    ],
    "glossary": [
        {"term": "Bloque", "definition": "Intervalo reservable de 60 minutos de una cancha"},
        {"term": "Bloqueo", "definition": "Período en que el administrador inhabilita una cancha"},
    ],
}

DATA_MODEL = {
    "summary": "El modelo gira en torno a las reservas: cada reserva une a un usuario con una cancha en un bloque horario. Los usuarios tienen un rol (socio o administrador) y pueden tener identidades SSO. Los bloqueos inhabilitan una cancha en un rango de horas.",
    "enums": [
        {"name": "user_role", "values": ["member", "admin"]},
        {"name": "sport", "values": ["tennis", "padel"]},
        {"name": "reservation_status", "values": ["confirmed", "cancelled"]},
    ],
    "tables": [
        {
            "name": "users",
            "description": "Socios y administradores",
            "columns": [
                _id(),
                _col("email", "varchar(254)", unique=True, description="Correo de acceso, en minúsculas"),
                _col("full_name", "varchar(120)", description="Nombre completo"),
                _col("password_hash", "varchar(255)", nullable=True, description="Hash argon2; nulo si solo usa SSO"),
                _col("role", "user_role", default="'member'", description="Rol: member = U1, admin = U2"),
                _created(),
            ],
            "indexes": [],
            "unique_constraints": [],
            "checks": [],
        },
        {
            "name": "sso_identities",
            "description": "Identidades externas (Google) vinculadas a un usuario",
            "columns": [
                _id(),
                _col("user_id", "uuid", fk=_fk("users"), description="Usuario dueño"),
                _col("provider", "varchar(30)", description="Proveedor, ej. google"),
                _col("subject", "varchar(255)", description="Identificador del usuario en el proveedor (claim sub)"),
                _created(),
            ],
            "indexes": [{"name": "idx_sso_identities_user", "columns": ["user_id"], "unique": False}],
            "unique_constraints": [["provider", "subject"]],
            "checks": [],
        },
        {
            "name": "courts",
            "description": "Canchas del club",
            "columns": [
                _id(),
                _col("name", "varchar(60)", unique=True, description="Nombre visible, ej. Cancha 1"),
                _col("sport", "sport", description="Deporte"),
                _col("is_active", "boolean", default="true", description="Si aparece en la disponibilidad"),
                _created(),
                _col("updated_at", "timestamptz", default="now()", description="Última modificación"),
            ],
            "indexes": [],
            "unique_constraints": [],
            "checks": [],
        },
        {
            "name": "reservations",
            "description": "Reservas de un bloque de una cancha",
            "columns": [
                _id(),
                _col("court_id", "uuid", fk=_fk("courts", "RESTRICT"), description="Cancha reservada"),
                _col("user_id", "uuid", fk=_fk("users"), description="Socio que reserva"),
                _col("starts_at", "timestamptz", description="Inicio del bloque"),
                _col("ends_at", "timestamptz", description="Fin del bloque (inicio + 60 min)"),
                _col("status", "reservation_status", default="'confirmed'", description="Estado"),
                _col("cancelled_at", "timestamptz", nullable=True, description="Fecha de cancelación"),
                _created(),
            ],
            "indexes": [
                {"name": "idx_reservations_user", "columns": ["user_id", "starts_at"], "unique": False},
                {"name": "idx_reservations_court_start", "columns": ["court_id", "starts_at"], "unique": False},
            ],
            "unique_constraints": [],
            "checks": [{"name": "ck_reservations_range", "expression": "ends_at > starts_at"}],
        },
        {
            "name": "court_blocks",
            "description": "Bloqueos de horario de una cancha",
            "columns": [
                _id(),
                _col("court_id", "uuid", fk=_fk("courts"), description="Cancha bloqueada"),
                _col("starts_at", "timestamptz", description="Inicio del bloqueo"),
                _col("ends_at", "timestamptz", description="Fin del bloqueo"),
                _col("reason", "varchar(200)", description="Motivo"),
                _col("created_by", "uuid", nullable=True, fk=_fk("users", "SET NULL"), description="Administrador que lo creó"),
                _created(),
            ],
            "indexes": [{"name": "idx_court_blocks_court_start", "columns": ["court_id", "starts_at"], "unique": False}],
            "unique_constraints": [],
            "checks": [{"name": "ck_court_blocks_range", "expression": "ends_at > starts_at"}],
        },
    ],
    "notes": [
        "RN-04 se garantiza además con un índice único parcial: CREATE UNIQUE INDEX uq_reservations_slot ON reservations (court_id, starts_at) WHERE status = 'confirmed'.",
        "RN-02 y RN-05 se validan en el backend dentro de la misma transacción que crea la reserva.",
    ],
}

AUTH_ERR = '{"error": {"code": "slot_taken", "message": "El bloque ya fue reservado", "details": null}}'

API_SPEC = {
    "summary": "API REST JSON bajo /api/v1. La sesión es un JWT en cookie HttpOnly; cada endpoint valida permisos en el backend.",
    "conventions": {
        "base_path": "/api/v1",
        "auth_mechanism": "JWT firmado (HS256) en cookie HttpOnly 'session' (8 horas); también se acepta Authorization: Bearer",
        "error_format": AUTH_ERR,
        "pagination": "Parámetros page (desde 1) y page_size (máx. 50); respuesta {items, page, page_size, total}",
        "datetime_format": "ISO 8601 con zona horaria (ej. 2026-11-03T18:00:00-03:00)",
        "id_format": "UUID v4",
    },
    "endpoints": [
        {
            "id": "EP-01", "method": "POST", "path": "/api/v1/auth/register", "summary": "Registrar socio",
            "description": "Crea una cuenta con rol member e inicia sesión.", "auth": "public", "allowed_roles": [], "authorization_rule": "",
            "params": [],
            "request_body": [_f("full_name", "string", validation="1 a 120 caracteres"), _f("email", "string", validation="correo válido"), _f("password", "string", validation="mínimo 8 caracteres")],
            "responses": [_r(201, "Cuenta creada", "object", [_f("id", "uuid"), _f("email", "string"), _f("full_name", "string"), _f("role", "enum(member|admin)")]), _r(409, "El correo ya está registrado"), R422],
            "tables": ["users"], "requirements": ["RF-01"],
        },
        {
            "id": "EP-02", "method": "POST", "path": "/api/v1/auth/login", "summary": "Iniciar sesión",
            "description": "Valida correo y contraseña y entrega la cookie de sesión.", "auth": "public", "allowed_roles": [], "authorization_rule": "",
            "params": [],
            "request_body": [_f("email", "string", validation="correo válido"), _f("password", "string")],
            "responses": [_r(200, "Sesión iniciada", "object", [_f("id", "uuid"), _f("full_name", "string"), _f("role", "enum(member|admin)")]), _r(401, "Credenciales inválidas"), R422, _r(429, "Demasiados intentos fallidos")],
            "tables": ["users"], "requirements": ["RF-01"],
        },
        {
            "id": "EP-03", "method": "POST", "path": "/api/v1/auth/logout", "summary": "Cerrar sesión",
            "description": "Elimina la cookie de sesión.", "auth": "authenticated", "allowed_roles": ["*"], "authorization_rule": "",
            "params": [], "request_body": [], "responses": [_r(204, "Sesión cerrada", "none"), R401], "tables": ["users"], "requirements": ["RF-01"],
        },
        {
            "id": "EP-04", "method": "GET", "path": "/api/v1/auth/me", "summary": "Usuario actual",
            "description": "Devuelve el usuario de la sesión.", "auth": "authenticated", "allowed_roles": ["*"], "authorization_rule": "",
            "params": [], "request_body": [],
            "responses": [_r(200, "Usuario", "object", [_f("id", "uuid"), _f("email", "string"), _f("full_name", "string"), _f("role", "enum(member|admin)")]), R401],
            "tables": ["users"], "requirements": ["RF-01"],
        },
        {
            "id": "EP-05", "method": "GET", "path": "/api/v1/auth/sso/google/login", "summary": "Iniciar SSO con Google",
            "description": "Redirige a Google con state, nonce y PKCE.", "auth": "public", "allowed_roles": [], "authorization_rule": "",
            "params": [], "request_body": [], "responses": [_r(302, "Redirección a Google", "none"), _r(503, "SSO no disponible")],
            "tables": [], "requirements": ["RF-01"],
        },
        {
            "id": "EP-06", "method": "GET", "path": "/api/v1/auth/sso/google/callback", "summary": "Callback de Google",
            "description": "Valida el código, crea o vincula el usuario y redirige al frontend con la sesión iniciada.", "auth": "public", "allowed_roles": [], "authorization_rule": "",
            "params": [_p("code", "query", "string", description="Código de autorización"), _p("state", "query", "string", description="State enviado al iniciar")],
            "request_body": [],
            "responses": [_r(302, "Sesión iniciada; redirige a /disponibilidad", "none"), _r(400, "State inválido o código ausente"), _r(502, "Google no respondió")],
            "tables": ["users", "sso_identities"], "requirements": ["RF-01"],
        },
        {
            "id": "EP-07", "method": "GET", "path": "/api/v1/availability", "summary": "Disponibilidad",
            "description": "Bloques de 08:00 a 22:00 de cada cancha activa, con estado libre, reservado o bloqueado.", "auth": "authenticated", "allowed_roles": ["*"], "authorization_rule": "",
            "params": [_p("date", "query", "date", description="Fecha YYYY-MM-DD"), _p("sport", "query", "enum(tennis|padel)", required=False, description="Filtro por deporte")],
            "request_body": [],
            "responses": [_r(200, "Grilla", "array", [_f("court_id", "uuid"), _f("court_name", "string"), _f("sport", "enum(tennis|padel)"), _f("slots", "array<object>", description="{starts_at, ends_at, state: free|reserved|blocked, mine: boolean}")]), R401, _r(422, "Fecha inválida")],
            "tables": ["courts", "reservations", "court_blocks"], "requirements": ["RF-02"],
        },
        {
            "id": "EP-08", "method": "POST", "path": "/api/v1/reservations", "summary": "Crear reserva",
            "description": "Reserva un bloque libre para el socio de la sesión.", "auth": "authenticated", "allowed_roles": ["U1"], "authorization_rule": "La reserva siempre queda a nombre del usuario de la sesión",
            "params": [],
            "request_body": [_f("court_id", "uuid"), _f("starts_at", "datetime", validation="futuro, en punto, entre 08:00 y 21:00")],
            "responses": [
                _r(201, "Reserva creada", "object", [_f("id", "uuid"), _f("court_id", "uuid"), _f("starts_at", "datetime"), _f("ends_at", "datetime"), _f("status", "enum(confirmed|cancelled)")]),
                R401, _r(403, "El usuario no es socio"), _r(409, "Bloque tomado o bloqueado, o el socio ya tiene 2 reservas futuras"), _r(422, "Datos inválidos o cancha inactiva"),
            ],
            "tables": ["reservations", "courts", "court_blocks"], "requirements": ["RF-03"],
        },
        {
            "id": "EP-09", "method": "GET", "path": "/api/v1/reservations/me", "summary": "Mis reservas",
            "description": "Reservas del socio de la sesión, futuras primero.", "auth": "authenticated", "allowed_roles": ["U1"], "authorization_rule": "Solo las reservas propias",
            "params": [], "request_body": [],
            "responses": [_r(200, "Lista", "array", [_f("id", "uuid"), _f("court_name", "string"), _f("starts_at", "datetime"), _f("status", "enum(confirmed|cancelled)"), _f("can_cancel", "boolean")]), R401, R403],
            "tables": ["reservations", "courts"], "requirements": ["RF-04"],
        },
        {
            "id": "EP-10", "method": "POST", "path": "/api/v1/reservations/{reservation_id}/cancel", "summary": "Cancelar reserva",
            "description": "Cancela la reserva y libera el bloque.", "auth": "authenticated", "allowed_roles": ["U1", "U2"], "authorization_rule": "U1 solo sus reservas y hasta 2 horas antes; U2 cualquier reserva",
            "params": [_p("reservation_id", "path", "uuid", description="Id de la reserva")], "request_body": [],
            "responses": [_r(200, "Reserva cancelada", "object", [_f("id", "uuid"), _f("status", "enum(confirmed|cancelled)"), _f("cancelled_at", "datetime")]), R401, _r(403, "No es dueño de la reserva"), _r(404, "La reserva no existe"), _r(409, "Ya cancelada o fuera de plazo")],
            "tables": ["reservations"], "requirements": ["RF-04", "RF-07"],
        },
        {
            "id": "EP-11", "method": "GET", "path": "/api/v1/admin/reservations", "summary": "Reservas del día",
            "description": "Todas las reservas de una fecha.", "auth": "authenticated", "allowed_roles": ["U2"], "authorization_rule": "",
            "params": [_p("date", "query", "date", description="Fecha YYYY-MM-DD"), _p("page", "query", "integer", required=False, description="Página")],
            "request_body": [],
            "responses": [_r(200, "Lista paginada", "paginated", [_f("id", "uuid"), _f("court_name", "string"), _f("starts_at", "datetime"), _f("member_name", "string"), _f("status", "enum(confirmed|cancelled)")]), R401, R403, R422],
            "tables": ["reservations", "courts", "users"], "requirements": ["RF-07"],
        },
        {
            "id": "EP-12", "method": "GET", "path": "/api/v1/courts", "summary": "Listar canchas",
            "description": "Canchas del club (los socios solo ven las activas).", "auth": "authenticated", "allowed_roles": ["*"], "authorization_rule": "",
            "params": [], "request_body": [],
            "responses": [_r(200, "Lista", "array", [_f("id", "uuid"), _f("name", "string"), _f("sport", "enum(tennis|padel)"), _f("is_active", "boolean")]), R401],
            "tables": ["courts"], "requirements": ["RF-02", "RF-05"],
        },
        {
            "id": "EP-13", "method": "POST", "path": "/api/v1/courts", "summary": "Crear cancha",
            "description": "Crea una cancha activa.", "auth": "authenticated", "allowed_roles": ["U2"], "authorization_rule": "",
            "params": [], "request_body": [_f("name", "string", validation="1 a 60 caracteres, único"), _f("sport", "enum(tennis|padel)")],
            "responses": [_r(201, "Cancha creada", "object", [_f("id", "uuid"), _f("name", "string"), _f("sport", "enum(tennis|padel)"), _f("is_active", "boolean")]), R401, R403, _r(409, "Nombre repetido"), R422],
            "tables": ["courts"], "requirements": ["RF-05"],
        },
        {
            "id": "EP-14", "method": "PATCH", "path": "/api/v1/courts/{court_id}", "summary": "Editar cancha",
            "description": "Cambia nombre, deporte o estado activo.", "auth": "authenticated", "allowed_roles": ["U2"], "authorization_rule": "",
            "params": [_p("court_id", "path", "uuid", description="Id de la cancha")],
            "request_body": [_f("name", "string", required=False, validation="1 a 60 caracteres, único"), _f("sport", "enum(tennis|padel)", required=False), _f("is_active", "boolean", required=False)],
            "responses": [_r(200, "Cancha actualizada", "object", [_f("id", "uuid"), _f("name", "string"), _f("is_active", "boolean")]), R401, R403, _r(404, "La cancha no existe"), _r(409, "Nombre repetido"), R422],
            "tables": ["courts"], "requirements": ["RF-05"],
        },
        {
            "id": "EP-15", "method": "POST", "path": "/api/v1/courts/{court_id}/blocks", "summary": "Crear bloqueo",
            "description": "Bloquea la cancha en un rango de horas.", "auth": "authenticated", "allowed_roles": ["U2"], "authorization_rule": "",
            "params": [_p("court_id", "path", "uuid", description="Id de la cancha")],
            "request_body": [_f("starts_at", "datetime"), _f("ends_at", "datetime", validation="posterior a starts_at"), _f("reason", "string", validation="1 a 200 caracteres")],
            "responses": [_r(201, "Bloqueo creado", "object", [_f("id", "uuid"), _f("starts_at", "datetime"), _f("ends_at", "datetime")]), R401, R403, _r(404, "La cancha no existe"), _r(409, "Se cruza con otro bloqueo"), R422],
            "tables": ["court_blocks", "courts"], "requirements": ["RF-06"],
        },
        {
            "id": "EP-16", "method": "DELETE", "path": "/api/v1/courts/{court_id}/blocks/{block_id}", "summary": "Eliminar bloqueo",
            "description": "Elimina un bloqueo.", "auth": "authenticated", "allowed_roles": ["U2"], "authorization_rule": "",
            "params": [_p("court_id", "path", "uuid", description="Id de la cancha"), _p("block_id", "path", "uuid", description="Id del bloqueo")],
            "request_body": [], "responses": [_r(204, "Eliminado", "none"), R401, R403, _r(404, "No existe")],
            "tables": ["court_blocks"], "requirements": ["RF-06"],
        },
    ],
}


def _sec(title, kind, elements, actions=None):
    return {"title": title, "kind": kind, "elements": elements, "actions": actions or []}


def _act(label, kind, endpoint=None, target=None, roles=None):
    return {"label": label, "kind": kind, "endpoint_id": endpoint, "target_screen": target, "roles": roles or []}


FRONTEND_SPEC = {
    "summary": "Web responsive pensada para celular. Los socios ven disponibilidad y sus reservas; el administrador además gestiona canchas, bloqueos y reservas del día.",
    "layout": "Cabecera con el nombre del club y menú: Disponibilidad y Mis reservas (U1); Disponibilidad, Canchas y Reservas del día (U2); Cerrar sesión.",
    "design_guidelines": ["Bloques libres en verde, ocupados en gris, bloqueados con trama", "Botones grandes para uso táctil"],
    "start_screen": "PA-01",
    "screens": [
        {
            "id": "PA-01", "name": "Iniciar sesión", "route": "/login", "purpose": "Ingresar con correo o con Google", "roles": ["publico"], "data_endpoints": [],
            "sections": [_sec("Acceso", "form", ["Correo", "Contraseña"], [_act("Ingresar", "submit", "EP-02", "PA-03"), _act("Entrar con Google", "other", "EP-05"), _act("Crear cuenta", "navigate", None, "PA-02")])],
            "states": ["Error: 'Correo o contraseña incorrectos'", "Google no disponible: aviso y se mantiene el formulario"], "journey_steps": [1],
        },
        {
            "id": "PA-02", "name": "Crear cuenta", "route": "/registro", "purpose": "Registro de socios", "roles": ["publico"], "data_endpoints": [],
            "sections": [_sec("Registro", "form", ["Nombre completo", "Correo", "Contraseña"], [_act("Crear cuenta", "submit", "EP-01", "PA-03"), _act("Ya tengo cuenta", "navigate", None, "PA-01")])],
            "states": ["Correo ya registrado: mensaje junto al campo"], "journey_steps": [],
        },
        {
            "id": "PA-03", "name": "Disponibilidad", "route": "/disponibilidad", "purpose": "Ver bloques libres y elegir uno", "roles": ["U1", "U2"], "data_endpoints": ["EP-04", "EP-12", "EP-07"],
            "sections": [
                _sec("Filtros", "filters", ["Fecha", "Deporte"]),
                _sec("Grilla", "table", ["Cancha", "Bloques 08:00 a 22:00 con estado"], [_act("Reservar bloque", "navigate", None, "PA-04", ["U1"])]),
                _sec("Menú", "other", ["Opciones según rol"], [_act("Mis reservas", "navigate", None, "PA-05", ["U1"]), _act("Canchas", "navigate", None, "PA-06", ["U2"]), _act("Reservas del día", "navigate", None, "PA-08", ["U2"]), _act("Cerrar sesión", "submit", "EP-03", "PA-01")]),
            ],
            "states": ["Sin canchas activas: 'No hay canchas disponibles'", "Cargando: grilla en gris", "Error: reintentar"], "journey_steps": [2, 3],
        },
        {
            "id": "PA-04", "name": "Confirmar reserva", "route": "/reservas/nueva", "purpose": "Revisar y confirmar el bloque elegido", "roles": ["U1"], "data_endpoints": [],
            "sections": [_sec("Resumen", "detail", ["Cancha", "Fecha", "Hora", "Regla de cancelación"], [_act("Confirmar reserva", "submit", "EP-08", "PA-05"), _act("Volver", "navigate", None, "PA-03")])],
            "states": ["Bloque tomado (409): aviso y vuelta a la grilla actualizada", "Límite de 2 reservas: aviso"], "journey_steps": [4],
        },
        {
            "id": "PA-05", "name": "Mis reservas", "route": "/mis-reservas", "purpose": "Ver y cancelar reservas propias", "roles": ["U1"], "data_endpoints": ["EP-09"],
            "sections": [_sec("Reservas", "list", ["Cancha", "Fecha", "Hora", "Estado"], [_act("Cancelar", "submit", "EP-10"), _act("Volver a disponibilidad", "navigate", None, "PA-03")])],
            "states": ["Sin reservas: 'Aún no tienes reservas'", "Fuera de plazo: botón Cancelar deshabilitado"], "journey_steps": [5],
        },
        {
            "id": "PA-06", "name": "Canchas", "route": "/admin/canchas", "purpose": "Administrar canchas", "roles": ["U2"], "data_endpoints": ["EP-12"],
            "sections": [
                _sec("Listado", "table", ["Nombre", "Deporte", "Activa"], [_act("Editar", "submit", "EP-14"), _act("Bloquear horario", "navigate", None, "PA-07"), _act("Volver", "navigate", None, "PA-03")]),
                _sec("Nueva cancha", "form", ["Nombre", "Deporte"], [_act("Crear cancha", "submit", "EP-13")]),
            ],
            "states": ["Sin canchas: invitación a crear la primera", "Nombre repetido: mensaje en el formulario"], "journey_steps": [],
        },
        {
            "id": "PA-07", "name": "Bloqueos de cancha", "route": "/admin/canchas/:id/bloqueos", "purpose": "Crear y eliminar bloqueos", "roles": ["U2"], "data_endpoints": [],
            "sections": [_sec("Nuevo bloqueo", "form", ["Inicio", "Fin", "Motivo"], [_act("Crear bloqueo", "submit", "EP-15"), _act("Eliminar bloqueo", "delete", "EP-16"), _act("Volver", "navigate", None, "PA-06")])],
            "states": ["Cancha inexistente: 'No encontrado'"], "journey_steps": [],
        },
        {
            "id": "PA-08", "name": "Reservas del día", "route": "/admin/reservas", "purpose": "Ver y cancelar reservas de una fecha", "roles": ["U2"], "data_endpoints": ["EP-11"],
            "sections": [_sec("Filtro", "filters", ["Fecha"]), _sec("Reservas", "table", ["Cancha", "Hora", "Socio", "Estado"], [_act("Cancelar", "submit", "EP-10"), _act("Volver", "navigate", None, "PA-03")])],
            "states": ["Sin reservas para la fecha"], "journey_steps": [],
        },
    ],
    "navigation": [
        {"from_screen": "PA-01", "to_screen": "PA-03", "trigger": "Ingresar"},
        {"from_screen": "PA-01", "to_screen": "PA-02", "trigger": "Crear cuenta"},
        {"from_screen": "PA-02", "to_screen": "PA-03", "trigger": "Cuenta creada"},
        {"from_screen": "PA-03", "to_screen": "PA-04", "trigger": "Reservar bloque"},
        {"from_screen": "PA-04", "to_screen": "PA-05", "trigger": "Reserva confirmada"},
        {"from_screen": "PA-03", "to_screen": "PA-06", "trigger": "Menú Canchas"},
        {"from_screen": "PA-06", "to_screen": "PA-07", "trigger": "Bloquear horario"},
        {"from_screen": "PA-03", "to_screen": "PA-08", "trigger": "Menú Reservas del día"},
    ],
}

ARCH_EVALUATION = {
    "scores": [
        {"scenario_id": "A1", "fit": 5, "strengths": ["CRUD relacional con reglas transaccionales simples", "Equipo pequeño, un solo despliegue"], "risks": ["Escala vertical limitada (suficiente para 400 socios)"]},
        {"scenario_id": "A2", "fit": 4, "strengths": ["Un solo lenguaje"], "risks": ["El equipo trabaja en Python"]},
        {"scenario_id": "A3", "fit": 3, "strengths": ["Rápido de montar"], "risks": ["Reglas RN-02/RN-05 quedan repartidas en políticas RLS"]},
        {"scenario_id": "A4", "fit": 2, "strengths": ["Escalable"], "risks": ["Complejidad innecesaria para un club"]},
        {"scenario_id": "A5", "fit": 1, "strengths": [], "risks": ["El producto no usa IA"]},
    ],
    "recommended": "A1",
    "justification": "ReservaCancha es un CRUD relacional con reglas transaccionales (choques de horario, máximo de reservas) y poca carga; un monolito FastAPI + PostgreSQL las resuelve en una transacción y se despliega con un solo docker compose.",
}


def arch_spec(scenario_id: str) -> dict:
    return {
        "scenario_id": scenario_id,
        "summary": "Monolito modular: API FastAPI, PostgreSQL y SPA React servida por Nginx, desplegados con Docker Compose.",
        "rationale": "Las reglas de reserva necesitan transacciones sobre datos relacionales y la carga es baja. Un monolito evita la complejidad de servicios separados (A4), no depende de políticas RLS dispersas (A3) y el producto no usa IA (A5).",
        "stack": [
            {"layer": "Base de datos", "technology": "PostgreSQL", "version": "16", "justification": "Transacciones e índices parciales"},
            {"layer": "Backend", "technology": "Python + FastAPI + SQLAlchemy", "version": "3.12 / 0.115 / 2.0", "justification": "Validación con Pydantic y OpenAPI automático"},
            {"layer": "Frontend", "technology": "React + TypeScript + Vite", "version": "18 / 5 / 5", "justification": "SPA liviana y responsive"},
            {"layer": "Autenticación", "technology": "Authlib (OIDC Google) + PyJWT + argon2", "version": "1.3 / 2.8 / 23", "justification": "Estándares OIDC y hash seguro"},
            {"layer": "Infraestructura", "technology": "Docker Compose + Nginx", "version": "2 / 1.27", "justification": "Un comando para levantar todo"},
            {"layer": "Observabilidad", "technology": "Logs JSON + prometheus-client", "version": "0.20", "justification": "Métricas y health checks simples"},
            {"layer": "Pruebas", "technology": "pytest + Playwright", "version": "8 / 1.45", "justification": "Unitarias, API y end-to-end"},
        ],
        "components": [
            {"name": "web", "responsibility": "Sirve la SPA y hace de proxy a /api", "technology": "Nginx + React", "communicates_with": ["api"]},
            {"name": "api", "responsibility": "Lógica de negocio, autenticación y autorización", "technology": "FastAPI", "communicates_with": ["db", "Google OIDC"]},
            {"name": "db", "responsibility": "Persistencia", "technology": "PostgreSQL 16", "communicates_with": []},
            {"name": "Google OIDC", "responsibility": "Proveedor de identidad", "technology": "Google Identity", "communicates_with": []},
        ],
        "repository_structure": "reservacancha/\n├── docker-compose.yml\n├── .env.example\n├── backend/\n│   ├── Dockerfile\n│   ├── app/{main.py, config.py, db.py, models.py, auth/, routers/, services/}\n│   ├── migrations/ (Alembic)\n│   └── tests/{unit,functional}/\n└── frontend/\n    ├── Dockerfile\n    ├── nginx.conf\n    └── src/{pages,components,api}/",
        "persistence": "PostgreSQL 16 con migraciones Alembic. Zona horaria UTC en la base; conversión a America/Santiago en el backend. Respaldo diario con pg_dump.",
        "backend": "Capas routers → services → repositorios SQLAlchemy. Validación con Pydantic; errores con el formato único. La creación de reservas usa una transacción con SELECT ... FOR UPDATE sobre la cancha.",
        "frontend": "React Router con rutas por pantalla, cliente fetch con credenciales incluidas, estado local por pantalla y guardas de ruta por rol.",
        "communication": "REST/JSON sobre HTTPS; mismo origen a través de Nginx (sin CORS en producción).",
        "authentication": "Registro y login con correo y contraseña (argon2). El backend emite un JWT HS256 de 8 horas en una cookie HttpOnly, Secure y SameSite=Lax. Logout borra la cookie.",
        "sso": "OIDC con Google, flujo authorization code con PKCE. Callback /api/v1/auth/sso/google/callback. Se valida firma, iss, aud, exp y nonce del id_token; se vincula por (provider, sub) en sso_identities y, si no existe, se crea el usuario con rol member.",
        "authorization": "Rol en users.role (member=U1, admin=U2). Una dependencia de FastAPI exige sesión (401 si falta o es inválida) y el rol del endpoint (403). Para reservas se verifica que user_id sea el de la sesión salvo admin (403). Recurso inexistente: 404.",
        "configuration": [
            {"name": "DATABASE_URL", "description": "Conexión a PostgreSQL", "example": "postgresql+psycopg://app:app@db:5432/reservas", "secret": True, "required": True},
            {"name": "SECRET_KEY", "description": "Firma de los JWT", "example": "(32+ caracteres)", "secret": True, "required": True},
            {"name": "GOOGLE_CLIENT_ID", "description": "Cliente OIDC de Google", "example": "123.apps.googleusercontent.com", "secret": False, "required": True},
            {"name": "GOOGLE_CLIENT_SECRET", "description": "Secreto del cliente OIDC", "example": "(secreto)", "secret": True, "required": True},
            {"name": "FRONTEND_URL", "description": "URL pública del frontend", "example": "https://reservas.club.cl", "secret": False, "required": True},
        ],
        "environments": ["Desarrollo: docker compose local con datos de prueba", "Pruebas: base efímera en CI", "Producción: VM con HTTPS y secretos en Key Vault"],
        "deployment": "Dockerfile para api (python:3.12-slim) y web (build de Vite + nginx). docker-compose con db, api y web y healthchecks. CI en GitHub Actions: pruebas y build de imágenes en cada PR.",
        "observability": "Logs JSON con request_id; métricas Prometheus en /metrics (latencia y errores por ruta); health check /api/health y readiness /api/ready (verifica la base).",
        "testing": "pytest para reglas de negocio (choques, límite de reservas, plazos) y pruebas de API con base de datos de prueba; Playwright para el recorrido principal y los casos 401/403.",
        "security": ["Rate limiting en login", "Cookies HttpOnly + SameSite", "Validación de entrada con Pydantic", "Secretos fuera del repositorio"],
        "risks": ["Doble reserva por concurrencia: índice único parcial + transacción", "Caída de Google: login con contraseña como alternativa"],
    }


REVIEW = {
    "findings": [
        {
            "severity": "importante",
            "area": "api",
            "description": "EP-08 responde 409 en tres situaciones distintas (bloque tomado, bloqueo y límite de 2 reservas) sin códigos de error diferenciados.",
            "suggestion": "En la etapa de API, documentar error.code distintos (slot_taken, court_blocked, max_reservations) para que la pantalla PA-04 muestre el mensaje correcto.",
        }
    ],
    "summary": "La definición es consistente; solo falta diferenciar los conflictos de EP-08.",
}


class FakeLLM(LLMClient):
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, *, task: str, system: str, user: str, schema: type[T], effort: str | None = None) -> T:
        self.calls.append(task)
        if task == "product_turn":
            if "RESPUESTAS NUEVAS DEL EQUIPO" in user or "MENSAJES RECIENTES" in user:
                refs = re.findall(r"^(Q\d+) \[", user, flags=re.MULTILINE)
                data = {
                    "brief": BRIEF_COMPLETE,
                    "resolved_question_refs": refs,
                    "new_questions": [],
                    "contradictions": [],
                    "assistant_message": "Con tus respuestas la definición quedó completa. Revisa los supuestos y aprueba la etapa.",
                }
            else:
                data = {
                    "brief": BRIEF_ROUND_1,
                    "resolved_question_refs": [],
                    "new_questions": QUESTIONS_ROUND_1,
                    "contradictions": [],
                    "assistant_message": "Entendí la idea general. Necesito definir los tipos de usuario y si habrá pagos antes de seguir.",
                }
        elif task == "data_model":
            data = DATA_MODEL
        elif task == "api_spec":
            data = API_SPEC
        elif task == "frontend_spec":
            data = FRONTEND_SPEC
        elif task == "architecture_eval":
            data = ARCH_EVALUATION
        elif task == "architecture_spec":
            match = re.search(r"ESCENARIO_SELECCIONADO: (A\d)", user)
            data = arch_spec(match.group(1) if match else "A1")
        elif task == "consistency_review":
            data = REVIEW
        else:  # pragma: no cover
            raise ValueError(f"Tarea desconocida: {task}")
        return schema.model_validate(data)
