"""Etapa «Pruebas y datos»: plan de pruebas funcionales y datos sintéticos.

Lo pidió el profe en clases: antes de que exista código no hay tests unitarios que ejecutar, así que
el editor debe entregar una ESPECIFICACIÓN de pruebas (qué comprobar, cómo, con qué datos y qué se
espera) ligada a cada requisito, más datos ficticios para que la app nueva no se vea vacía.

Se arma sin IA, a partir de lo ya aprobado, por tres razones:
- Trazabilidad exacta: cada caso sale de un criterio de aceptación, un caso borde o una respuesta
  de error documentada en la API, con sus ids.
- Velocidad: es instantáneo (la demo tiene que caber en 10 a 12 minutos).
- Honestidad: son casos verificables, no "tests ejecutados".
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel

from .schemas import ApiSpec, DataModel, FrontendSpec, ProductBrief

# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------


class TestCase(BaseModel):
    id: str
    title: str
    kind: Literal["positivo", "negativo", "limite", "seguridad", "persistencia"]
    requirement_ids: list[str] = []
    source: str  # de dónde sale: "RF-03 criterio 2", "CB-04", "EP-07 409"
    role: str
    preconditions: list[str] = []
    data: str = ""
    steps: list[str]
    expected: str
    endpoints: list[str] = []
    screens: list[str] = []
    priority: Literal["alta", "media", "baja"] = "media"


class SeedTable(BaseModel):
    table: str
    rows: list[dict[str, Any]]


class SeedData(BaseModel):
    purpose: str
    tables: list[SeedTable]
    load: str
    cleanup: str


class TestingSpec(BaseModel):
    summary: str
    cases: list[TestCase]
    seed: SeedData


# ---------------------------------------------------------------------------
# Plan de pruebas
# ---------------------------------------------------------------------------

_NEG = re.compile(r"rechaz|inv[aá]lid|error|no (se )?(permite|puede|guarda|crea|muestra)|impid|deneg|sin permiso|\b4\d\d\b|falla|no exist|duplicad", re.I)
_LIM = re.compile(r"m[aá]xim|m[ií]nim|l[ií]mite|m[aá]s de|menos de|hasta \d|al menos \d|exactamente", re.I)
_GWT = re.compile(r"^\s*dad[oa]s?\s+(?P<given>.+?)[,;]\s*cuando\s+(?P<when>.+?)[,;]\s*entonces\s+(?P<then>.+?)\s*\.?\s*$", re.I | re.S)


def _kind_of(text: str) -> str:
    if _NEG.search(text):
        return "negativo"
    if _LIM.search(text):
        return "limite"
    return "positivo"


def _req_links(api: ApiSpec, fe: FrontendSpec | None) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    req_eps: dict[str, list[str]] = {}
    for ep in api.endpoints:
        for r in ep.requirements:
            req_eps.setdefault(r, []).append(ep.id)
    ep_screens: dict[str, list[str]] = {}
    for s in fe.screens if fe else []:
        eps = set(s.data_endpoints) | {a.endpoint_id for sec in s.sections for a in sec.actions if a.endpoint_id}
        for e in eps:
            ep_screens.setdefault(e, []).append(s.id)
    req_screens = {r: sorted({sid for e in eps for sid in ep_screens.get(e, [])}) for r, eps in req_eps.items()}
    return req_eps, req_screens


def build_test_plan(brief: ProductBrief, api: ApiSpec, fe: FrontendSpec | None) -> list[TestCase]:
    names = {u.id: u.name for u in brief.user_types}
    req_eps, req_screens = _req_links(api, fe)
    eps = {e.id: e for e in api.endpoints}
    cases: list[TestCase] = []

    def add(**kw: Any) -> None:
        cases.append(TestCase(id=f"PF-{len(cases) + 1:02d}", **kw))

    # 1) Un caso por criterio de aceptación de cada requisito
    for r in brief.functional_requirements:
        role = ", ".join(names.get(u, u) for u in r.user_types) or "Cualquier usuario"
        endpoints = req_eps.get(r.id, [])
        screens = req_screens.get(r.id, [])
        criteria = r.acceptance_criteria or [f"Dado un {role}, cuando usa «{r.title}», entonces {r.description}"]
        for i, criterion in enumerate(criteria, start=1):
            m = _GWT.match(criterion)
            given, when, then = (m.group("given"), m.group("when"), m.group("then")) if m else ("", criterion, criterion)
            steps = []
            if screens:
                steps.append(f"Abrir {', '.join(screens)} con una cuenta de {role}.")
            steps.append(when[0].upper() + when[1:] if when else criterion)
            if endpoints:
                steps.append(f"Verificar en Network la llamada a {', '.join(endpoints)} y su código de respuesta.")
            add(
                title=f"{r.title} ({i})",
                kind=_kind_of(criterion),
                requirement_ids=[r.id],
                source=f"{r.id} criterio {i}",
                role=role,
                preconditions=[given] if given else [],
                data="Datos sintéticos de esta etapa.",
                steps=steps,
                expected=then,
                endpoints=endpoints,
                screens=screens,
                priority="alta" if r.priority == "must" else "media" if r.priority == "should" else "baja",
            )

    # 2) Persistencia: lo creado sigue ahí al recargar
    creator = next(
        (e for e in api.endpoints if e.method == "POST" and e.auth == "authenticated" and e.requirements and any(r.status == 201 for r in e.responses)),
        None,
    )
    if creator:
        add(
            title=f"Lo creado persiste al recargar ({creator.summary})",
            kind="persistencia",
            requirement_ids=creator.requirements,
            source=f"{creator.id} 201",
            role=", ".join(names.get(u, u) for u in creator.allowed_roles if u != "*") or "Usuario con sesión",
            steps=[f"Ejecutar {creator.method} {creator.path} desde la pantalla correspondiente.", "Recargar la página (F5) y volver a entrar."],
            expected="El registro sigue apareciendo igual: quedó guardado en la base de datos, no solo en el navegador.",
            endpoints=[creator.id],
            priority="alta",
        )

    # 3) Casos borde de la definición
    for cb in brief.edge_cases:
        add(
            title=cb.scenario[:90],
            kind="limite" if cb.category in ("concurrencia", "datos_invalidos") and _LIM.search(cb.scenario) else "negativo",
            source=cb.id,
            role="Según el escenario",
            steps=[cb.scenario],
            expected=cb.expected_behavior,
            priority="alta" if cb.category in ("sin_permisos", "concurrencia", "accion_fallida") else "media",
        )

    # 4) Seguridad y errores de la API: 401 una vez, 403 y 409 donde se documentan
    protected = next((e for e in api.endpoints if e.auth == "authenticated"), None)
    if protected:
        add(
            title="Sin sesión no se accede a datos protegidos",
            kind="seguridad",
            source=f"{protected.id} 401",
            role="Visitante sin sesión",
            steps=[f"Sin iniciar sesión (o con el token borrado), llamar a {protected.method} {protected.path}."],
            expected="Responde 401 y no entrega datos; la app pide iniciar sesión.",
            endpoints=[protected.id],
            priority="alta",
        )
    for code, kind, label in ((403, "seguridad", "sin permiso"), (409, "negativo", "en conflicto")):
        for e in [x for x in api.endpoints if any(r.status == code for r in x.responses)][:6]:
            resp = next(r for r in e.responses if r.status == code)
            add(
                title=f"{e.summary}: operación {label}",
                kind=kind,
                requirement_ids=e.requirements,
                source=f"{e.id} {code}",
                role=", ".join(names.get(u, u) for u in e.allowed_roles if u != "*") or "Usuario con sesión",
                steps=[f"Provocar el caso: {resp.description}", f"Llamar a {e.method} {e.path}."],
                expected=f"Responde {code} con el formato de error de la API y no modifica datos ni revela información de otro usuario.",
                endpoints=[e.id],
                priority="alta" if code == 403 else "media",
            )
    return cases


def coverage(brief: ProductBrief, cases: list[TestCase]) -> dict[str, list[str]]:
    covered: dict[str, list[str]] = {r.id: [] for r in brief.functional_requirements}
    for c in cases:
        for r in c.requirement_ids:
            covered.setdefault(r, []).append(c.id)
    return covered


# ---------------------------------------------------------------------------
# Datos sintéticos
# ---------------------------------------------------------------------------

_FIRST = ["Camila", "Diego", "Sofía", "Matías", "Valentina", "Benjamín", "Antonia", "Tomás", "Isidora", "Joaquín"]
_LAST = ["Rojas", "Muñoz", "Pérez", "Soto", "Contreras", "Silva", "Morales", "Fuentes", "Araya", "Reyes"]
_PLACES = ["Peñalolén", "Ñuñoa", "La Reina", "Macul", "Las Condes"]
# 15:00 UTC = mediodía en Chile: cae dentro de cualquier horario hábil razonable.
_BASE = datetime(2026, 12, 1, 15, 0, tzinfo=timezone.utc)
_NS = uuid.UUID("6f1c3b8e-2a4d-4f6b-9c1e-5d7a8b9c0d1e")


def _norm(s: str) -> str:
    return s.lower()


def _singular(table: str) -> str:
    t = table.replace("_", " ")
    return t[:-1] if t.endswith("s") else t


def _ordered_tables(model: DataModel):
    """Padres antes que hijos (orden topológico por claves foráneas)."""
    pending = {t.name: t for t in model.tables}
    done: list = []
    while pending:
        ready = [t for t in pending.values() if all(not c.foreign_key or c.foreign_key.table not in pending or c.foreign_key.table == t.name for c in t.columns)]
        if not ready:  # ciclo: se rompe en orden alfabético
            ready = [sorted(pending.values(), key=lambda t: t.name)[0]]
        for t in sorted(ready, key=lambda t: t.name):
            done.append(t)
            pending.pop(t.name)
    return done


def _maxlen(t: str) -> int | None:
    m = re.match(r"varchar\((\d+)\)", t.replace(" ", "").lower())
    return int(m.group(1)) if m else None


def _value(table: str, col, i: int, enums: dict[str, list[str]], ids: dict[str, list[str]]) -> Any:
    n, t = _norm(col.name), _norm(col.type)
    if col.foreign_key:
        parents = ids.get(col.foreign_key.table) or []
        return parents[i % len(parents)] if parents else None
    if col.primary_key and t == "uuid":
        return str(uuid.uuid5(_NS, f"{table}-{i}"))
    if t in enums:
        values = enums[t]
        return values[i % len(values)]
    if t == "uuid":
        return str(uuid.uuid5(_NS, f"{table}-{col.name}-{i}"))
    if t == "boolean":
        return i % 4 != 3  # la mayoría true, alguno false para ver ambos estados
    if t in ("integer", "bigint", "smallint") or t.startswith("numeric") or t in ("real", "double precision"):
        if "version" in n:
            return 1
        if re.search(r"price|precio|amount|monto|total|cost|fee|salary", n):
            return 4990 + i * 1500
        if re.search(r"capacity|capacidad|stock|quantity|cantidad|seats|cupos", n):
            return 10 + (i * 7) % 40
        if re.search(r"minutes|duration|duracion", n):
            return [30, 60, 90][i % 3]
        return 1 + i
    if t == "date":
        return (_BASE + timedelta(days=i)).date().isoformat()  # mismo día que los timestamps de la fila
    if t.startswith("time") and "stamp" not in t:
        return f"{9 + i % 10:02d}:00"
    if "timestamp" in t:
        if re.search(r"created|updated|registered|creado", n):
            return (_BASE - timedelta(days=20 - i)).isoformat()
        moment = _BASE + timedelta(days=i, hours=i % 5)
        if re.search(r"end|ends|fin|until|hasta|expires|vence|closed", n):
            moment += timedelta(minutes=_DURATION.get(table, 120))
        return moment.isoformat()
    if t == "jsonb" or t == "json":
        return {}
    # Texto
    first, last = _FIRST[i % len(_FIRST)], _LAST[(i * 3) % len(_LAST)]
    if "email" in n or "correo" in n:
        value = f"{first.lower()}.{last.lower()}{i}@ejemplo.test".replace("í", "i").replace("ó", "o").replace("á", "a").replace("é", "e").replace("ñ", "n").replace("ú", "u")
    elif "password" in n:
        value = f"$argon2id$v=19$m=65536,t=3,p=4$FICTICIO{i}$FICTICIO"
    elif "token" in n or "secret" in n or "hash" in n:
        value = f"ficticio-{table}-{i:04d}"
    elif "phone" in n or "telefono" in n:
        value = f"+56 9 5555 {1000 + i}"
    elif "url" in n or "link" in n:
        value = f"https://ejemplo.test/{table}/{i}"
    elif re.search(r"first_name|nombre$", n):
        value = first
    elif "last_name" in n or "apellido" in n:
        value = last
    elif n in ("name", "full_name", "display_name") or n.endswith("_name") and "user" in table:
        value = f"{first} {last}" if re.search(r"user|account|member|client|customer|person|socio", table) else f"{_singular(table).title()} {i + 1}"
    elif re.search(r"locality|commune|comuna|city|ciudad|address|direccion", n):
        value = _PLACES[i % len(_PLACES)]
    elif re.search(r"title|titulo|name|nombre", n):
        value = f"{_singular(table).title()} de prueba {i + 1}"
    elif re.search(r"description|descripcion|notes|notas|comment|comentario|reason|motivo|body|content", n):
        value = f"Texto ficticio de ejemplo para {_singular(table)} {i + 1}."
    elif re.search(r"status|estado", n):
        value = ["activo", "pendiente", "cerrado"][i % 3]
    elif re.search(r"code|codigo|sku|slug", n):
        value = f"{table[:3].upper()}-{i + 1:03d}"
    else:
        value = f"{col.name} ficticio {i + 1}"
    limit = _maxlen(t)
    return value[:limit] if limit else value


_DURATION: dict[str, int] = {}
_INTERVAL = re.compile(r"=\s*\w+\s*\+\s*interval\s*'(\d+)\s*(minute|minutes|hour|hours)'", re.I)


_PAIR = re.compile(r"\(?\s*(\w+)\s*=\s*(true|false)\s+and\s+(\w+)\s*=\s*'([^']+)'\s*\)?", re.I)


def _fix_pairs(table, row: dict[str, Any]) -> None:
    """CHECK del tipo (activo = true AND estado = 'x') OR (activo = false AND estado = 'y'): se respeta la pareja."""
    for chk in table.checks:
        pairs = _PAIR.findall(chk.expression)
        if len(pairs) < 2:
            continue
        for flag, val, col, text in pairs:
            if flag in row and col in row and isinstance(row[flag], bool) and row[flag] == (val.lower() == "true"):
                row[col] = text


def build_seed(model: DataModel) -> SeedData:
    enums = {_norm(e.name): e.values for e in model.enums}
    # Duración fija pedida por un CHECK (ej. ends_at = starts_at + interval '60 minutes')
    _DURATION.clear()
    for t in model.tables:
        for chk in t.checks:
            m = _INTERVAL.search(chk.expression)
            if m:
                _DURATION[t.name] = int(m.group(1)) * (60 if m.group(2).lower().startswith("hour") else 1)
    ids: dict[str, list[str]] = {}
    tables: list[SeedTable] = []
    for table in _ordered_tables(model):
        has_fk = any(c.foreign_key for c in table.columns)
        count = 8 if has_fk else 5
        # Una FK única (relación 1:1) no puede repetir el padre: como máximo una fila por padre.
        for c in table.columns:
            if c.foreign_key and (c.unique or c.primary_key or [c.name] in table.unique_constraints):
                count = min(count, len(ids.get(c.foreign_key.table) or [None]))
        rows = []
        for i in range(count):
            row = {}
            for col in table.columns:
                if col.default and not col.primary_key and not col.foreign_key and "now()" in col.default.lower():
                    continue  # lo pone la base de datos
                value = _value(table.name, col, i, enums, ids)
                if value is None and not col.nullable:
                    value = _value(table.name, col.model_copy(update={"foreign_key": None}), i, enums, ids)
                row[col.name] = value
            _fix_pairs(table, row)
            rows.append(row)
        pk = next((c.name for c in table.columns if c.primary_key), None)
        if pk:
            ids[table.name] = [r[pk] for r in rows if r.get(pk) is not None]
        tables.append(SeedTable(table=table.name, rows=rows))
    return SeedData(
        purpose="Datos FICTICIOS para que la app recién construida muestre tablas, tarjetas y gráficos con contenido, "
        "y para ejecutar el plan de pruebas. Ningún dato es real: correos @ejemplo.test, teléfonos +56 9 5555 y "
        "hashes marcados FICTICIO (esas cuentas no pueden iniciar sesión).",
        tables=tables,
        load="Cargar solo en desarrollo o pruebas, después de las migraciones: ejecutar `seed.sql` (o el script de seed "
        "equivalente del stack). Las tablas van en orden de dependencias, así las claves foráneas existen al insertar. "
        "Los valores respetan tipos, enums, claves foráneas, unicidad y duraciones fijas; si una restricción CHECK de negocio "
        "más compleja rechaza una fila, ajusta solo ese valor manteniendo el carácter ficticio.",
        cleanup="Borrar en orden inverso las filas cuyos ids aparecen en el seed (o recrear la base de pruebas). Nunca cargar en producción.",
    )


def _sql_literal(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    return "'" + str(v).replace("'", "''") + "'"


def seed_sql(seed: SeedData) -> str:
    lines = ["-- DATOS FICTICIOS generados por Plano (Ideator). Solo para desarrollo y pruebas.", "BEGIN;"]
    for t in seed.tables:
        if not t.rows:
            continue
        cols = list(t.rows[0].keys())
        lines.append(f"\n-- {t.table} ({len(t.rows)} filas)")
        lines.append(f"INSERT INTO {t.table} ({', '.join(cols)}) VALUES")
        values = [f"  ({', '.join(_sql_literal(r.get(c)) for c in cols)})" for r in t.rows]
        lines.append(",\n".join(values) + ";")
    lines.append("\nCOMMIT;")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Construcción y validación
# ---------------------------------------------------------------------------


def build_testing(brief: ProductBrief, model: DataModel, api: ApiSpec, fe: FrontendSpec | None) -> TestingSpec:
    cases = build_test_plan(brief, api, fe)
    by_kind: dict[str, int] = {}
    for c in cases:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
    detail = ", ".join(f"{n} {k}" for k, n in sorted(by_kind.items(), key=lambda x: -x[1]))
    seed = build_seed(model)
    rows = sum(len(t.rows) for t in seed.tables)
    return TestingSpec(
        summary=f"{len(cases)} casos de prueba funcionales ({detail}) trazados a {len(brief.functional_requirements)} requisitos, "
        f"y {rows} filas de datos ficticios en {len(seed.tables)} tablas.",
        cases=cases,
        seed=seed,
    )


def validate_testing(spec: TestingSpec, brief: ProductBrief, model: DataModel | None) -> list[dict[str, str]]:
    from .validation import issue

    issues = []
    cov = coverage(brief, spec.cases)
    for r in brief.functional_requirements:
        if not cov.get(r.id):
            sev = "error" if r.priority == "must" else "warning"
            issues.append(issue(sev, "test.uncovered", f"{r.id} «{r.title}» no tiene ningún caso de prueba", r.id))
    ids = [c.id for c in spec.cases]
    if len(ids) != len(set(ids)):
        issues.append(issue("error", "test.duplicate_id", "Hay ids de caso repetidos"))
    if not any(c.kind in ("negativo", "seguridad") for c in spec.cases):
        issues.append(issue("error", "test.only_happy", "El plan solo tiene casos positivos: faltan errores y permisos"))
    if model:
        seeded = {t.table for t in spec.seed.tables if t.rows}
        missing = [t.name for t in model.tables if t.name not in seeded]
        if missing:
            issues.append(issue("warning", "test.seed_missing", f"Tablas sin datos de ejemplo: {', '.join(missing)}"))
    return issues


def testing_markdown(spec: TestingSpec, brief: ProductBrief) -> list[str]:
    """Secciones para especificacion-producto.md."""
    from .documents import _cell, _table

    out: list[str] = []
    w = out.append
    w("## 17. Plan de pruebas funcionales")
    w("")
    w(
        "> Especificación verificable, NO tests ejecutados: describe qué comprobar, cómo, con qué datos y qué se espera. "
        "Al implementar, conviértela en pruebas automáticas (unitarias, de integración y E2E) que cumplan cada caso."
    )
    w("")
    w(spec.summary)
    w("")
    cov = coverage(brief, spec.cases)
    w(_table(["Requisito", "Casos"], [[f"{r.id} {r.title}", ", ".join(cov.get(r.id, [])) or "**sin casos**"] for r in brief.functional_requirements]))
    w("")
    for c in spec.cases:
        w(f"### {c.id} · {c.title}")
        w("")
        meta = [f"**Tipo:** {c.kind}", f"**Prioridad:** {c.priority}", f"**Origen:** {c.source}", f"**Rol:** {c.role}"]
        if c.requirement_ids:
            meta.append(f"**Requisitos:** {', '.join(c.requirement_ids)}")
        if c.endpoints:
            meta.append(f"**Endpoints:** {', '.join(c.endpoints)}")
        if c.screens:
            meta.append(f"**Pantallas:** {', '.join(c.screens)}")
        w(" · ".join(meta))
        w("")
        if c.preconditions:
            w("**Precondiciones:** " + "; ".join(_cell(p) for p in c.preconditions))
            w("")
        w("**Pasos:**")
        w("")
        w("\n".join(f"{i}. {s}" for i, s in enumerate(c.steps, start=1)))
        w("")
        w(f"**Resultado esperado:** {c.expected}")
        w("")
    w("## 18. Datos sintéticos (ficticios)")
    w("")
    w(spec.seed.purpose)
    w("")
    w(f"**Carga:** {spec.seed.load}")
    w("")
    w(f"**Limpieza:** {spec.seed.cleanup}")
    w("")
    w(_table(["Tabla", "Filas"], [[f"`{t.table}`", len(t.rows)] for t in spec.seed.tables]))
    w("")
    w("```sql")
    w(seed_sql(spec.seed))
    w("```")
    w("")
    return out
