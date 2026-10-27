"""Validaciones deterministas de cada etapa y de la consistencia entre etapas.

Cada validación devuelve una lista de issues:
{"severity": "error" | "warning", "code": str, "message": str, "path": str}
Un "error" impide aprobar la etapa; un "warning" solo se informa.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any

from .schemas import (
    ALLOWED_STATUS,
    EDGE_CATEGORY_LABELS,
    REQUIRED_EDGE_CATEGORIES,
    ApiSpec,
    ArchitectureSpec,
    DataModel,
    FrontendSpec,
    ProductBrief,
)

SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
BASE_TYPE = re.compile(
    r"^(uuid|text|citext|varchar\(\d+\)|char\(\d+\)|smallint|integer|int|bigint|serial|bigserial|"
    r"numeric(\(\d+\s*,\s*\d+\))?|decimal(\(\d+\s*,\s*\d+\))?|real|double precision|boolean|date|time|"
    r"timestamptz|timestamp|interval|jsonb|json|bytea|inet)(\[\])?$",
    re.IGNORECASE,
)
PATH_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

Issue = dict[str, str]


def issue(severity: str, code: str, message: str, path: str = "") -> Issue:
    return {"severity": severity, "code": code, "message": message, "path": path}


def has_errors(issues: list[Issue]) -> bool:
    return any(i["severity"] == "error" for i in issues)


def _filled(text: str | None, min_len: int = 1) -> bool:
    return bool(text and len(text.strip()) >= min_len)


def user_type_ids(brief: ProductBrief | None) -> set[str]:
    if brief is None:
        return set()
    return {u.id for u in brief.user_types}


def _role_ok(role: str, ids: set[str], extra: set[str]) -> bool:
    return role in ids or role in extra


# ---------------------------------------------------------------------------
# Producto
# ---------------------------------------------------------------------------


def product_checklist(brief: ProductBrief, open_blocking: int) -> list[dict[str, Any]]:
    """Checklist de completitud que se muestra al equipo y bloquea la aprobación."""
    present = {e.category for e in brief.edge_cases}
    missing_edges = [EDGE_CATEGORY_LABELS[c] for c in REQUIRED_EDGE_CATEGORIES if c not in present]
    reqs_without_criteria = [r.id for r in brief.functional_requirements if not r.acceptance_criteria]
    items = [
        ("problem", "Problema y contexto definidos", _filled(brief.problem, 20) and _filled(brief.context, 20), ""),
        ("users", "Al menos un tipo de usuario con objetivos", any(u.goals for u in brief.user_types), ""),
        (
            "outcomes",
            "Resultados esperados con forma de medirlos",
            any(_filled(o.metric) for o in brief.expected_outcomes),
            "",
        ),
        (
            "scope",
            "Alcance del MVP: qué entra y qué queda fuera",
            len(brief.mvp_in_scope) >= 2 and len(brief.mvp_out_of_scope) >= 1,
            "",
        ),
        ("journey", "Recorrido principal con al menos 3 pasos", len(brief.main_journey.steps) >= 3, ""),
        (
            "requirements",
            "Requisitos funcionales con criterios de aceptación",
            len(brief.functional_requirements) >= 3 and not reqs_without_criteria,
            ("Sin criterios: " + ", ".join(reqs_without_criteria)) if reqs_without_criteria else "",
        ),
        ("rules", "Reglas de negocio", len(brief.business_rules) >= 1, ""),
        ("security", "Condiciones de seguridad", len(brief.security_requirements) >= 1, ""),
        (
            "edge_cases",
            "Casos borde (falta de información, fallas, permisos, inexistentes, datos inválidos, dependencias)",
            not missing_edges,
            ("Faltan: " + ", ".join(missing_edges)) if missing_edges else "",
        ),
        (
            "blocking",
            "Sin preguntas bloqueantes pendientes",
            open_blocking == 0,
            f"{open_blocking} pendiente(s)" if open_blocking else "",
        ),
    ]
    return [{"key": k, "label": label, "ok": bool(ok), "detail": detail} for k, label, ok, detail in items]


def validate_product(brief: ProductBrief, open_blocking: int) -> list[Issue]:
    issues: list[Issue] = []
    for item in product_checklist(brief, open_blocking):
        if not item["ok"]:
            msg = item["label"] + (f" ({item['detail']})" if item["detail"] else "")
            issues.append(issue("error", f"product.{item['key']}", f"Incompleto: {msg}", item["key"]))

    ids = [u.id for u in brief.user_types]
    if len(ids) != len(set(ids)):
        issues.append(issue("error", "product.duplicate_user_ids", "Hay tipos de usuario con el mismo id", "user_types"))
    req_ids = [r.id for r in brief.functional_requirements]
    if len(req_ids) != len(set(req_ids)):
        issues.append(issue("error", "product.duplicate_req_ids", "Hay requisitos con el mismo id", "functional_requirements"))
    valid_users = set(ids)
    for r in brief.functional_requirements:
        unknown = [u for u in r.user_types if u not in valid_users]
        if unknown:
            issues.append(
                issue("warning", "product.req_unknown_user", f"{r.id} usa tipos de usuario inexistentes: {', '.join(unknown)}", r.id)
            )
    for step in brief.main_journey.steps:
        if step.actor not in valid_users and step.actor.lower() != "sistema":
            issues.append(
                issue("warning", "product.journey_actor", f"Paso {step.number}: actor '{step.actor}' no es un tipo de usuario", "main_journey")
            )
    pending = [a.id for a in brief.assumptions if not a.accepted]
    if pending:
        issues.append(
            issue(
                "warning",
                "product.pending_assumptions",
                f"Supuestos sin aceptar: {', '.join(pending)}. Debes aceptarlos o corregirlos antes de generar los documentos.",
                "assumptions",
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------


def normalize_type(t: str) -> str:
    t = t.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return {"int": "integer", "decimal": "numeric", "timestamp with time zone": "timestamptz"}.get(t, t)


def _type_family(t: str) -> str:
    t = normalize_type(t)
    t = re.sub(r"\(.*\)", "", t)
    return {"serial": "integer", "bigserial": "bigint", "citext": "text", "varchar": "text", "char": "text"}.get(t, t)


def derive_relationships(model: DataModel) -> list[dict[str, Any]]:
    """Relaciones derivadas de las claves foráneas (fuente única de verdad)."""
    tables = {t.name: t for t in model.tables}
    rels = []
    for t in model.tables:
        unique_cols = {c.name for c in t.columns if c.unique or c.primary_key}
        for uc in t.unique_constraints:
            if len(uc) == 1:
                unique_cols.add(uc[0])
        for c in t.columns:
            if not c.foreign_key:
                continue
            parent = c.foreign_key.table
            rels.append(
                {
                    "parent": parent,
                    "child": t.name,
                    "column": c.name,
                    "references": f"{parent}.{c.foreign_key.column}",
                    "cardinality": "1:1" if c.name in unique_cols else "1:N",
                    "optional": c.nullable,
                    "on_delete": c.foreign_key.on_delete,
                    "parent_exists": parent in tables,
                }
            )
    return rels


def junction_tables(model: DataModel) -> list[dict[str, str]]:
    """Tablas puente (N:M): dos FKs a tablas distintas y casi sin columnas propias."""
    result = []
    for t in model.tables:
        fks = [c for c in t.columns if c.foreign_key]
        own = [c for c in t.columns if not c.foreign_key and not c.primary_key and c.name not in ("created_at", "updated_at")]
        if len(fks) == 2 and fks[0].foreign_key.table != fks[1].foreign_key.table and len(own) <= 2:
            result.append({"table": t.name, "left": fks[0].foreign_key.table, "right": fks[1].foreign_key.table})
    return result


def validate_data_model(model: DataModel, brief: ProductBrief | None = None) -> list[Issue]:
    issues: list[Issue] = []
    if not model.tables:
        return [issue("error", "dm.empty", "El modelo no tiene tablas")]

    enum_names = {e.name for e in model.enums}
    for e in model.enums:
        if not e.values:
            issues.append(issue("error", "dm.enum_empty", f"El enum {e.name} no tiene valores", e.name))
        if not SNAKE.match(e.name):
            issues.append(issue("error", "dm.enum_name", f"El enum '{e.name}' debe estar en snake_case", e.name))

    names = [t.name for t in model.tables]
    seen: set[str] = set()
    for n in names:
        if n in seen:
            issues.append(issue("error", "dm.duplicate_table", f"La tabla {n} está repetida", n))
        seen.add(n)
    tables = {t.name: t for t in model.tables}
    used_enums: set[str] = set()

    for t in model.tables:
        if not SNAKE.match(t.name):
            issues.append(issue("error", "dm.table_name", f"La tabla '{t.name}' debe estar en snake_case", t.name))
        cols = [c.name for c in t.columns]
        if len(cols) != len(set(cols)):
            issues.append(issue("error", "dm.duplicate_column", f"{t.name} tiene columnas repetidas", t.name))
        pks = [c for c in t.columns if c.primary_key]
        if not pks:
            issues.append(issue("error", "dm.no_pk", f"{t.name} no tiene clave primaria", t.name))
        for c in t.columns:
            path = f"{t.name}.{c.name}"
            if not SNAKE.match(c.name):
                issues.append(issue("error", "dm.column_name", f"La columna '{path}' debe estar en snake_case", path))
            ctype = normalize_type(c.type)
            if ctype in enum_names:
                used_enums.add(ctype)
            elif not BASE_TYPE.match(ctype):
                issues.append(issue("error", "dm.bad_type", f"{path}: tipo '{c.type}' no reconocido (usa un tipo PostgreSQL o un enum definido)", path))
            if c.primary_key and c.nullable:
                issues.append(issue("error", "dm.pk_nullable", f"{path}: una clave primaria no puede ser nula", path))
            if c.foreign_key:
                fk = c.foreign_key
                parent = tables.get(fk.table)
                if parent is None:
                    issues.append(issue("error", "dm.fk_table", f"{path} referencia a la tabla inexistente '{fk.table}'", path))
                    continue
                target = next((pc for pc in parent.columns if pc.name == fk.column), None)
                if target is None:
                    issues.append(issue("error", "dm.fk_column", f"{path} referencia a la columna inexistente '{fk.table}.{fk.column}'", path))
                    continue
                single_uniques = {u[0] for u in parent.unique_constraints if len(u) == 1}
                if not (target.primary_key or target.unique or target.name in single_uniques):
                    issues.append(issue("error", "dm.fk_not_unique", f"{path} debe referenciar una clave primaria o única", path))
                if _type_family(target.type) != _type_family(c.type):
                    issues.append(issue("error", "dm.fk_type", f"{path} ({c.type}) no coincide con {fk.table}.{fk.column} ({target.type})", path))
                if fk.on_delete == "SET NULL" and not c.nullable:
                    issues.append(issue("error", "dm.fk_set_null", f"{path} usa ON DELETE SET NULL pero no admite nulos", path))
        colset = set(cols)
        for idx in t.indexes:
            missing = [c for c in idx.columns if c not in colset]
            if missing or not idx.columns:
                issues.append(issue("error", "dm.index_columns", f"Índice {idx.name} en {t.name} usa columnas inexistentes: {', '.join(missing) or '(vacío)'}", t.name))
        for uc in t.unique_constraints:
            missing = [c for c in uc if c not in colset]
            if missing or not uc:
                issues.append(issue("error", "dm.unique_columns", f"Restricción única en {t.name} usa columnas inexistentes: {', '.join(missing) or '(vacío)'}", t.name))

    for e in model.enums:
        if e.name not in used_enums:
            issues.append(issue("warning", "dm.enum_unused", f"El enum {e.name} no se usa en ninguna columna", e.name))

    rels = derive_relationships(model)
    related = {r["parent"] for r in rels} | {r["child"] for r in rels}
    if len(model.tables) > 1:
        for t in model.tables:
            if t.name not in related:
                issues.append(issue("warning", "dm.isolated_table", f"La tabla {t.name} no se relaciona con ninguna otra", t.name))

    if brief is not None and len(brief.user_types) >= 2:
        has_roles = any(
            "role" in c.name or "rol" == c.name or "type" in c.name
            for t in model.tables
            for c in t.columns
        ) or any("member" in t.name or "role" in t.name for t in model.tables)
        if not has_roles:
            issues.append(
                issue("warning", "dm.roles", "Hay varios tipos de usuario pero el modelo no tiene una columna o tabla de roles", "")
            )
    return issues


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def validate_api(spec: ApiSpec, model: DataModel | None, brief: ProductBrief | None) -> list[Issue]:
    issues: list[Issue] = []
    if not spec.endpoints:
        return [issue("error", "api.empty", "No hay endpoints definidos")]

    table_names = {t.name for t in model.tables} if model else set()
    req_ids = {r.id for r in brief.functional_requirements} if brief else set()
    roles = user_type_ids(brief)
    seen_ids: set[str] = set()
    seen_routes: set[tuple[str, str]] = set()
    base = spec.conventions.base_path.rstrip("/")

    for ep in spec.endpoints:
        where = f"{ep.id} {ep.method} {ep.path}"
        if ep.id in seen_ids:
            issues.append(issue("error", "api.duplicate_id", f"Id repetido: {ep.id}", ep.id))
        seen_ids.add(ep.id)
        route_key = (ep.method, PATH_PARAM.sub("{}", ep.path))
        if route_key in seen_routes:
            issues.append(issue("error", "api.duplicate_route", f"Ruta repetida: {ep.method} {ep.path}", ep.id))
        seen_routes.add(route_key)
        if base and not ep.path.startswith(base):
            issues.append(issue("warning", "api.base_path", f"{where}: no parte con el prefijo {base}", ep.id))

        in_path = set(PATH_PARAM.findall(ep.path))
        declared = {p.name for p in ep.params if p.location == "path"}
        if in_path != declared:
            issues.append(
                issue(
                    "error",
                    "api.path_params",
                    f"{where}: parámetros de ruta {sorted(in_path)} no coinciden con los declarados {sorted(declared)}",
                    ep.id,
                )
            )

        statuses = [r.status for r in ep.responses]
        status_set = set(statuses)
        if not any(200 <= s < 400 for s in statuses):
            issues.append(issue("error", "api.no_success", f"{where}: no define una respuesta exitosa (2xx o redirección)", ep.id))
        bad = [s for s in statuses if s not in ALLOWED_STATUS]
        if bad:
            issues.append(issue("error", "api.bad_status", f"{where}: códigos no válidos {bad}", ep.id))
        if len(statuses) != len(status_set):
            issues.append(issue("warning", "api.duplicate_status", f"{where}: hay códigos de respuesta repetidos", ep.id))
        if ep.auth == "authenticated" and 401 not in status_set:
            issues.append(issue("error", "api.missing_401", f"{where}: requiere sesión pero no documenta 401", ep.id))
        restricted = ep.auth == "authenticated" and (ep.allowed_roles != ["*"] or _filled(ep.authorization_rule))
        if restricted and 403 not in status_set:
            issues.append(issue("error", "api.missing_403", f"{where}: tiene restricción de permisos pero no documenta 403", ep.id))
        if in_path and 404 not in status_set:
            issues.append(issue("error", "api.missing_404", f"{where}: recibe un id en la ruta pero no documenta 404", ep.id))
        has_input = bool(ep.request_body) or any(p.required and p.location == "query" for p in ep.params)
        if has_input and not ({400, 422} & status_set):
            issues.append(issue("error", "api.missing_400", f"{where}: recibe datos pero no documenta 400/422", ep.id))
        if ep.method == "POST" and not ({200, 201, 202, 204} & status_set):
            issues.append(issue("warning", "api.post_status", f"{where}: un POST debería responder 201 (creación) o 200", ep.id))
        if ep.method == "DELETE" and not ({200, 204} & status_set):
            issues.append(issue("warning", "api.delete_status", f"{where}: un DELETE debería responder 204", ep.id))
        for r in ep.responses:
            if r.status == 204 and r.fields:
                issues.append(issue("error", "api.204_body", f"{where}: una respuesta 204 no puede tener cuerpo", ep.id))
        if ep.method == "GET" and ep.request_body:
            issues.append(issue("error", "api.get_body", f"{where}: un GET no debe recibir cuerpo", ep.id))

        if model is not None:
            unknown_tables = [t for t in ep.tables if t not in table_names]
            if unknown_tables:
                issues.append(
                    issue("error", "api.unknown_table", f"{where}: usa tablas que no existen en el modelo: {', '.join(unknown_tables)}", ep.id)
                )
        if brief is not None:
            unknown_reqs = [r for r in ep.requirements if r not in req_ids]
            if unknown_reqs:
                issues.append(issue("error", "api.unknown_req", f"{where}: referencia requisitos inexistentes: {', '.join(unknown_reqs)}", ep.id))
            unknown_roles = [r for r in ep.allowed_roles if not _role_ok(r, roles, {"*"})]
            if unknown_roles:
                issues.append(issue("error", "api.unknown_role", f"{where}: roles inexistentes {unknown_roles} (usa ids U1.. o '*')", ep.id))

    if brief is not None:
        covered = {r for ep in spec.endpoints for r in ep.requirements}
        for req in brief.functional_requirements:
            if req.id not in covered:
                sev = "error" if req.priority == "must" else "warning"
                issues.append(issue(sev, "api.uncovered_req", f"{req.id} ({req.title}) no tiene ningún endpoint asociado", req.id))
    if model is not None:
        used = {t for ep in spec.endpoints for t in ep.tables}
        for t in model.tables:
            if t.name not in used:
                issues.append(issue("warning", "api.unused_table", f"La tabla {t.name} no la usa ningún endpoint", t.name))
    return issues


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------


def validate_frontend(spec: FrontendSpec, api: ApiSpec | None, brief: ProductBrief | None) -> list[Issue]:
    issues: list[Issue] = []
    if not spec.screens:
        return [issue("error", "fe.empty", "No hay pantallas definidas")]

    screen_ids = [s.id for s in spec.screens]
    screen_set = set(screen_ids)
    if len(screen_ids) != len(screen_set):
        issues.append(issue("error", "fe.duplicate_id", "Hay pantallas con el mismo id"))
    routes = [s.route for s in spec.screens]
    if len(routes) != len(set(routes)):
        issues.append(issue("error", "fe.duplicate_route", "Hay pantallas con la misma ruta"))
    if spec.start_screen not in screen_set:
        issues.append(issue("error", "fe.start", f"La pantalla inicial {spec.start_screen} no existe"))

    endpoint_ids = {e.id for e in api.endpoints} if api else set()
    roles = user_type_ids(brief)
    used_endpoints: set[str] = set()

    for s in spec.screens:
        if api is not None:
            for ep in s.data_endpoints:
                used_endpoints.add(ep)
                if ep not in endpoint_ids:
                    issues.append(issue("error", "fe.unknown_endpoint", f"{s.id}: carga el endpoint inexistente {ep}", s.id))
        if brief is not None:
            bad_roles = [r for r in s.roles if not _role_ok(r, roles, {"publico", "*"})]
            if bad_roles:
                issues.append(issue("error", "fe.unknown_role", f"{s.id}: roles inexistentes {bad_roles}", s.id))
        for sec in s.sections:
            for a in sec.actions:
                where = f"{s.id} › {sec.title} › '{a.label}'"
                if a.endpoint_id:
                    used_endpoints.add(a.endpoint_id)
                    if api is not None and a.endpoint_id not in endpoint_ids:
                        issues.append(issue("error", "fe.unknown_endpoint", f"{where}: usa el endpoint inexistente {a.endpoint_id}", s.id))
                if a.kind in ("submit", "delete") and not a.endpoint_id:
                    issues.append(issue("error", "fe.action_endpoint", f"{where}: una acción de tipo {a.kind} debe indicar su endpoint", s.id))
                if a.kind == "navigate" and not a.target_screen:
                    issues.append(issue("error", "fe.action_target", f"{where}: una navegación debe indicar la pantalla destino", s.id))
                if a.target_screen and a.target_screen not in screen_set:
                    issues.append(issue("error", "fe.unknown_screen", f"{where}: navega a la pantalla inexistente {a.target_screen}", s.id))
                if brief is not None:
                    bad = [r for r in a.roles if not _role_ok(r, roles, {"publico", "*"})]
                    if bad:
                        issues.append(issue("error", "fe.unknown_role", f"{where}: roles inexistentes {bad}", s.id))

    for link in spec.navigation:
        for sid in (link.from_screen, link.to_screen):
            if sid not in screen_set:
                issues.append(issue("error", "fe.nav_unknown", f"La navegación usa la pantalla inexistente {sid}"))

    if brief is not None:
        covered_steps = {n for s in spec.screens for n in s.journey_steps}
        for step in brief.main_journey.steps:
            if step.number not in covered_steps:
                issues.append(issue("error", "fe.journey_uncovered", f"El paso {step.number} del recorrido principal no tiene pantalla", f"step-{step.number}"))

    # Alcanzabilidad desde la pantalla inicial
    graph: dict[str, set[str]] = defaultdict(set)
    for link in spec.navigation:
        graph[link.from_screen].add(link.to_screen)
    for s in spec.screens:
        for sec in s.sections:
            for a in sec.actions:
                if a.target_screen:
                    graph[s.id].add(a.target_screen)
    if spec.start_screen in screen_set:
        reach = {spec.start_screen}
        queue = deque([spec.start_screen])
        while queue:
            for nxt in graph[queue.popleft()]:
                if nxt not in reach:
                    reach.add(nxt)
                    queue.append(nxt)
        for s in spec.screens:
            if s.id not in reach:
                issues.append(issue("warning", "fe.unreachable", f"No hay forma de llegar a {s.id} ({s.name}) desde la pantalla inicial", s.id))

    if api is not None:
        for ep in api.endpoints:
            redirect_flow = any(r.status == 302 for r in ep.responses)
            if ep.id not in used_endpoints and not redirect_flow:
                issues.append(issue("warning", "fe.unused_endpoint", f"{ep.id} ({ep.method} {ep.path}) no se usa en ninguna pantalla", ep.id))
    return issues


# ---------------------------------------------------------------------------
# Arquitectura
# ---------------------------------------------------------------------------


def validate_architecture(spec: ArchitectureSpec, scenario_ids: set[str], relational_model: bool = True) -> list[Issue]:
    issues: list[Issue] = []
    if spec.scenario_id not in scenario_ids:
        issues.append(issue("error", "arch.scenario", f"Escenario desconocido: {spec.scenario_id}"))
    layers = " ".join(f"{t.layer} {t.technology}".lower() for t in spec.stack)
    for needle, label in (
        (("base de datos", "database", "persistencia", "postgres", "mysql", "mongo", "firestore", "supabase"), "base de datos"),
        (("backend", "api", "servidor"), "backend"),
        (("frontend", "interfaz", "cliente web", "react", "vue", "angular", "next"), "frontend"),
    ):
        if not any(n in layers for n in needle):
            issues.append(issue("error", "arch.stack_layer", f"El stack no define la capa de {label}"))
    if not spec.configuration:
        issues.append(issue("error", "arch.config", "No hay variables de entorno definidas"))
    elif not any(v.secret for v in spec.configuration):
        issues.append(issue("warning", "arch.secrets", "Ninguna variable está marcada como secreta"))
    if not _filled(spec.sso, 20):
        issues.append(issue("error", "arch.sso", "Falta definir el Single Sign-On"))
    if not _filled(spec.authentication, 20):
        issues.append(issue("error", "arch.auth", "Falta definir la autenticación"))
    if not _filled(spec.authorization, 20):
        issues.append(issue("error", "arch.authz", "Falta definir la autorización"))
    elif not ("401" in spec.authorization and "403" in spec.authorization):
        issues.append(issue("warning", "arch.authz_codes", "La autorización debería explicar cuándo se responde 401 y cuándo 403"))
    obs = spec.observability.lower()
    if not any(k in obs for k in ("health", "salud", "estado")):
        issues.append(issue("warning", "arch.health", "La observabilidad no define verificación de estado (health check)"))
    if not any(k in obs for k in ("log",)):
        issues.append(issue("warning", "arch.logging", "La observabilidad no define logging"))
    if relational_model:
        nosql = any(k in layers for k in ("mongo", "firestore", "dynamo", "cosmos"))
        if nosql and not any(k in layers for k in ("postgres", "mysql", "sql server", "sqlite", "supabase")):
            issues.append(issue("error", "arch.db_mismatch", "El modelo de datos aprobado es relacional pero el stack usa una base no relacional"))
    if not spec.environments:
        issues.append(issue("warning", "arch.environments", "No se definen ambientes de ejecución"))
    return issues
