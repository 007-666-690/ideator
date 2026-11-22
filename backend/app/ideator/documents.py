"""Generación de los documentos finales en Markdown.

Los documentos se arman de forma determinista a partir de las etapas aprobadas.
Así cada nombre de tabla, ruta, código HTTP o rol aparece exactamente igual en
todas las secciones, y el documento no depende de la conversación previa.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .architectures import BASE_ARCHITECTURES, get_architecture
from .render import SSO_SEQUENCE, components_diagram, ddl, mermaid_er, navigation_map
from .schemas import (
    EDGE_CATEGORY_LABELS,
    ApiSpec,
    ArchitectureEvaluation,
    ArchitectureSpec,
    DataModel,
    FrontendSpec,
    ProductBrief,
)
from .validation import derive_relationships, junction_tables

PRIORITY = {"must": "Obligatorio", "should": "Deseable", "could": "Opcional"}
PRODUCT_FILENAME = "especificacion-producto.md"
ARCHITECTURE_FILENAME = "arquitectura.md"


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>").strip() or "—"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_(sin elementos)_"
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _bullets(items: list[str], empty: str = "_(ninguno)_") -> str:
    return "\n".join(f"- {i}" for i in items) if items else empty


def _user_names(brief: ProductBrief) -> dict[str, str]:
    return {u.id: u.name for u in brief.user_types}


def _roles_text(roles: list[str], names: dict[str, str]) -> str:
    if not roles or roles == ["*"]:
        return "cualquier usuario autenticado"
    out = []
    for r in roles:
        if r == "*":
            out.append("cualquier usuario autenticado")
        elif r == "publico":
            out.append("público (sin sesión)")
        else:
            out.append(f"{r} ({names[r]})" if r in names else r)
    return ", ".join(out)


def uses_sso(api: ApiSpec) -> bool:
    """El producto usa SSO solo si la API aprobada tiene endpoints de SSO."""
    return any("/sso" in ep.path.lower() for ep in api.endpoints)


def _req_links(api: ApiSpec, fe: FrontendSpec) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Mapea cada requisito a sus endpoints y pantallas."""
    req_eps: dict[str, list[str]] = {}
    for ep in api.endpoints:
        for r in ep.requirements:
            req_eps.setdefault(r, []).append(ep.id)
    ep_screens: dict[str, list[str]] = {}
    for s in fe.screens:
        eps = set(s.data_endpoints) | {a.endpoint_id for sec in s.sections for a in sec.actions if a.endpoint_id}
        for e in eps:
            ep_screens.setdefault(e, []).append(s.id)
    req_screens = {
        r: sorted({sid for e in eps for sid in ep_screens.get(e, [])}) for r, eps in req_eps.items()
    }
    return req_eps, req_screens


# ---------------------------------------------------------------------------
# Documento 1: especificación del producto
# ---------------------------------------------------------------------------


def product_spec_markdown(
    *,
    project_name: str,
    brief: ProductBrief,
    model: DataModel | None,
    api: ApiSpec | None,
    fe: FrontendSpec | None,
    version: int,
    generated_at: datetime,
    stage_only: bool = False,
    testing: Any = None,
) -> str:
    """Especificación del producto. Con stage_only=True genera solo lo de la etapa 1 (sin §9–11).

    testing (TestingSpec) agrega §17 Plan de pruebas funcionales y §18 Datos sintéticos.
    """
    names = _user_names(brief)
    req_eps, req_screens = _req_links(api, fe) if api is not None and fe is not None else ({}, {})
    step_screens: dict[int, list[str]] = {}
    for s in fe.screens if fe is not None else []:
        for n in s.journey_steps:
            step_screens.setdefault(n, []).append(s.id)

    out: list[str] = []
    w = out.append
    if stage_only:
        w(f"# {brief.product_name or project_name} — Definición del producto")
        w("")
        w(
            f"> Exportado desde Ideator el {generated_at:%Y-%m-%d %H:%M} UTC · Proyecto «{project_name}» · Etapa 1, versión {version}.  \n"
            "> Es la definición aprobada del producto. El modelo de datos, la API y las pantallas se definen en las etapas siguientes."
        )
    else:
        w(f"# {brief.product_name or project_name} — Especificación de producto (MVP)")
        w("")
        w(
            f"> Generado por Ideator el {generated_at:%Y-%m-%d %H:%M} UTC · Proyecto «{project_name}» · Versión {version}.  \n"
            "> Este documento y `arquitectura.md` son la única fuente de verdad del producto. "
            "Lo que no aparece aquí no forma parte del MVP."
        )
    w("")
    w("## 0. Instrucciones para la IA que implementa")
    w("")
    w(
        _bullets(
            [
                "Implementa solo el alcance del MVP (§4). Lo listado como «Fuera del MVP» no se construye.",
                "Usa exactamente los nombres de tablas, columnas, rutas, campos, roles y códigos HTTP de este documento. No los renombres ni los traduzcas.",
                "Las decisiones (§14) y los supuestos aceptados (§15) ya están tomados: aplícalos sin volver a preguntar.",
                "La autorización se valida siempre en el backend (§3 y §10). La interfaz solo oculta acciones; nunca es la protección.",
                "El stack, la estructura del repositorio, la autenticación/SSO, las variables de entorno y el despliegue están en `arquitectura.md`.",
                "El MVP está terminado cuando se cumplen todos los criterios de aceptación (§5) y los comportamientos de los casos borde (§8).",
                "Orden sugerido: base de datos y migraciones (§9) → autenticación → endpoints en el orden del recorrido principal (§6) → pantallas (§11) → casos borde → pruebas.",
                *(
                    [
                        "Las pruebas automáticas deben cubrir cada caso de §17 (mismo id PF-xx en el nombre del test). Carga los datos ficticios de §18 solo en desarrollo y pruebas."
                    ]
                    if testing is not None
                    else []
                ),
            ]
        )
    )
    w("")
    w("## 1. Resumen")
    w("")
    if brief.one_liner:
        w(f"**{brief.one_liner}**")
        w("")
    w(f"- **Problema:** {brief.problem}")
    w(f"- **Contexto:** {brief.context}")
    w(f"- **Situación actual:** {brief.current_situation or '—'}")
    w(f"- **Mejora esperada:** {brief.desired_improvement or '—'}")
    w("")
    w("## 2. Resultados esperados")
    w("")
    w(_table(["Id", "Resultado", "Cómo se mide", "Meta"], [[o.id, o.description, o.metric, o.target] for o in brief.expected_outcomes]))
    w("")
    w("## 3. Usuarios, roles y permisos")
    w("")
    w(_table(["Id", "Tipo de usuario", "Descripción", "Objetivos"], [[u.id, u.name, u.description, "; ".join(u.goals)] for u in brief.user_types]))
    w("")
    w("### Permisos")
    w("")
    w(_table(["Id", "Puede", "No puede"], [[u.id, "<br>".join(u.permissions) or "—", "<br>".join(u.restrictions) or "—"] for u in brief.user_types]))
    w("")
    w("En la API, los roles se identifican por estos ids (`U1`, `U2`…); `*` significa cualquier usuario autenticado.")
    w("")
    w("## 4. Alcance del MVP")
    w("")
    w("### Incluido")
    w("")
    w(_bullets([f"**{i.id}** {i.description}" + (f" — {i.reason}" if i.reason else "") for i in brief.mvp_in_scope]))
    w("")
    w("### Fuera del MVP (no implementar)")
    w("")
    w(_bullets([f"**{i.id}** {i.description}" + (f" — {i.reason}" if i.reason else "") for i in brief.mvp_out_of_scope]))
    w("")
    w("## 5. Requisitos funcionales")
    w("")
    for r in brief.functional_requirements:
        w(f"### {r.id} · {r.title}")
        w("")
        w(r.description)
        w("")
        w(f"- **Prioridad:** {PRIORITY.get(r.priority, r.priority)}")
        w(f"- **Usuarios:** {_roles_text(r.user_types, names)}")
        if not stage_only:
            w(f"- **Endpoints:** {', '.join(req_eps.get(r.id, [])) or '—'}")
            w(f"- **Pantallas:** {', '.join(req_screens.get(r.id, [])) or '—'}")
        w("")
        w("**Criterios de aceptación**")
        w("")
        w("\n".join(f"- [ ] {c}" for c in r.acceptance_criteria) or "_(sin criterios)_")
        w("")
    j = brief.main_journey
    w(f"## 6. Recorrido principal: {j.name}")
    w("")
    w(f"- **Actor:** {_roles_text([j.actor], names) if j.actor else '—'}")
    w(f"- **Objetivo:** {j.goal}")
    w(f"- **Precondiciones:** {'; '.join(j.preconditions) or 'ninguna'}")
    w("")
    w(
        _table(
            ["Paso", "Actor", "Acción", "Respuesta del sistema", "Pantalla"],
            [[s.number, s.actor, s.action, s.system_response, ", ".join(step_screens.get(s.number, []))] for s in j.steps],
        )
    )
    w("")
    w(f"**Resultado:** {j.success_result}")
    w("")
    w("## 7. Reglas de negocio")
    w("")
    w(_bullets([f"**{r.id}** {r.description}" for r in brief.business_rules]))
    w("")
    w("## 8. Casos borde y manejo de errores")
    w("")
    w(
        _table(
            ["Id", "Categoría", "Escenario", "Comportamiento esperado"],
            [[e.id, EDGE_CATEGORY_LABELS.get(e.category, e.category), e.scenario, e.expected_behavior] for e in brief.edge_cases],
        )
    )
    w("")
    if model is not None:
        out.extend(_data_model_section(model))
    if api is not None:
        out.extend(_api_section(api, names))
    if fe is not None:
        out.extend(_frontend_section(fe, names))
    w("## 12. Requisitos no funcionales y seguridad")
    w("")
    w("### Seguridad")
    w("")
    w(_bullets(brief.security_requirements))
    w("")
    w("### No funcionales")
    w("")
    w(_bullets(brief.non_functional_requirements))
    w("")
    w("### Restricciones técnicas")
    w("")
    w(_bullets(brief.technical_constraints))
    w("")
    w("## 13. Integraciones externas")
    w("")
    w(
        _table(
            ["Integración", "Propósito", "Obligatoria en el MVP", "Si no responde"],
            [[i.name, i.purpose, "Sí" if i.required_for_mvp else "No", i.failure_behavior] for i in brief.integrations],
        )
        if brief.integrations
        else "No hay integraciones externas en el MVP."
    )
    w("")
    w("## 14. Decisiones tomadas")
    w("")
    w(
        _table(
            ["Id", "Tema", "Decisión", "Origen"],
            [[d.id, d.topic, d.decision, "Equipo" if d.source == "usuario" else "Delegada a la IA por el equipo"] for d in brief.decisions],
        )
    )
    w("")
    w("## 15. Supuestos aceptados")
    w("")
    w(_bullets([f"**{a.id}** {a.description}" for a in brief.assumptions if a.accepted], "_(no hay supuestos)_"))
    w("")
    w("## 16. Glosario")
    w("")
    w(_table(["Término", "Definición"], [[g.term, g.definition] for g in brief.glossary]))
    w("")
    if testing is not None and not stage_only:
        from .testing import testing_markdown

        out.extend(testing_markdown(testing, brief))
    return "\n".join(out)


def _data_model_section(model: DataModel) -> list[str]:
    out: list[str] = []
    w = out.append
    w("## 9. Modelo de datos")
    w("")
    w(model.summary)
    w("")
    w("```mermaid")
    w(mermaid_er(model))
    w("```")
    w("")
    if model.enums:
        w("### Tipos enumerados")
        w("")
        w(_table(["Enum", "Valores"], [[f"`{e.name}`", ", ".join(f"`{v}`" for v in e.values)] for e in model.enums]))
        w("")
    w("### Tablas")
    w("")
    for t in model.tables:
        w(f"#### `{t.name}`")
        w("")
        w(t.description)
        w("")
        rows = []
        for c in t.columns:
            keys = []
            if c.primary_key:
                keys.append("PK")
            if c.foreign_key:
                keys.append(f"FK → `{c.foreign_key.table}.{c.foreign_key.column}`")
            if c.unique and not c.primary_key:
                keys.append("UNIQUE")
            rows.append([f"`{c.name}`", f"`{c.type}`", "Sí" if c.nullable else "No", " ".join(keys), c.default or "", c.description])
        w(_table(["Columna", "Tipo", "Nulo", "Clave", "Por defecto", "Descripción"], rows))
        extras = []
        if t.unique_constraints:
            extras.append("Únicos compuestos: " + "; ".join(f"({', '.join(u)})" for u in t.unique_constraints))
        if t.checks:
            extras.append("Checks: " + "; ".join(f"`{c.expression}`" for c in t.checks))
        if t.indexes:
            extras.append("Índices: " + "; ".join(f"`{i.name}` ({', '.join(i.columns)}){' único' if i.unique else ''}" for i in t.indexes))
        if extras:
            w("")
            w(_bullets(extras))
        w("")
    rels = [r for r in derive_relationships(model) if r["parent_exists"]]
    w("### Relaciones")
    w("")
    w(
        _table(
            ["Tabla padre", "Tabla hija", "Columna FK", "Cardinalidad", "Obligatoria", "ON DELETE"],
            [[r["parent"], r["child"], r["column"], r["cardinality"], "No" if r["optional"] else "Sí", r["on_delete"]] for r in rels],
        )
    )
    jt = junction_tables(model)
    if jt:
        w("")
        w(_bullets([f"`{j['table']}` implementa la relación N:M entre `{j['left']}` y `{j['right']}`." for j in jt]))
    w("")
    if model.notes:
        w("### Reglas que se validan en el backend")
        w("")
        w(_bullets(model.notes))
        w("")
    w("### DDL (PostgreSQL)")
    w("")
    w("```sql")
    w(ddl(model).rstrip())
    w("```")
    w("")
    return out


def _fields_table(fields: list[Any]) -> str:
    return _table(
        ["Campo", "Tipo", "Obligatorio", "Validación", "Descripción"],
        [[f"`{f.name}`", f.type, "Sí" if f.required else "No", f.validation, f.description] for f in fields],
    )


def _api_section(api: ApiSpec, names: dict[str, str]) -> list[str]:
    out: list[str] = []
    w = out.append
    c = api.conventions
    w("## 10. API del backend")
    w("")
    w(api.summary)
    w("")
    w("### Convenciones")
    w("")
    w(f"- **Prefijo:** `{c.base_path}`")
    w(f"- **Autenticación:** {c.auth_mechanism}")
    w(f"- **Paginación:** {c.pagination}")
    w(f"- **Fechas:** {c.datetime_format}")
    w(f"- **Identificadores:** {c.id_format}")
    w("- **Autorización:** sin sesión válida → `401`; con sesión pero sin permiso sobre el recurso → `403`; recurso inexistente → `404`.")
    w("- **Formato de error** (todas las respuestas 4xx/5xx):")
    w("")
    w("```json")
    w(c.error_format.strip())
    w("```")
    w("")
    w("### Resumen de endpoints")
    w("")
    w(
        _table(
            ["Id", "Método", "Ruta", "Descripción", "Acceso"],
            [
                [ep.id, ep.method, f"`{ep.path}`", ep.summary, "Público" if ep.auth == "public" else _roles_text(ep.allowed_roles, names)]
                for ep in api.endpoints
            ],
        )
    )
    w("")
    w("### Detalle de endpoints")
    w("")
    for ep in api.endpoints:
        w(f"#### {ep.id} · `{ep.method} {ep.path}`")
        w("")
        w(f"**{ep.summary}.** {ep.description}")
        w("")
        access = "Público (sin sesión)" if ep.auth == "public" else f"Requiere sesión · Roles: {_roles_text(ep.allowed_roles, names)}"
        w(f"- **Acceso:** {access}")
        if ep.authorization_rule:
            w(f"- **Regla de autorización:** {ep.authorization_rule}")
        w(f"- **Tablas:** {', '.join(f'`{t}`' for t in ep.tables) or '—'} · **Requisitos:** {', '.join(ep.requirements) or '—'}")
        w("")
        if ep.params:
            w("**Parámetros**")
            w("")
            w(
                _table(
                    ["Nombre", "Ubicación", "Tipo", "Obligatorio", "Descripción"],
                    [[f"`{p.name}`", p.location, p.type, "Sí" if p.required else "No", p.description] for p in ep.params],
                )
            )
            w("")
        if ep.request_body:
            w("**Cuerpo (JSON)**")
            w("")
            w(_fields_table(ep.request_body))
            w("")
        w("**Respuestas**")
        w("")
        for r in ep.responses:
            kind = {
                "none": "sin cuerpo",
                "object": "objeto",
                "array": "lista de objetos",
                "paginated": "lista paginada",
                "error": "formato de error estándar",
            }[r.body_kind]
            w(f"- `{r.status}` — {r.description} ({kind})")
            if r.fields and r.body_kind not in ("none", "error"):
                w("")
                w("  " + _fields_table(r.fields).replace("\n", "\n  "))
                w("")
        w("")
    return out


def _frontend_section(fe: FrontendSpec, names: dict[str, str]) -> list[str]:
    out: list[str] = []
    w = out.append
    screens = {s.id: s.name for s in fe.screens}
    w("## 11. Interfaz")
    w("")
    w(fe.summary)
    w("")
    w(f"- **Estructura general:** {fe.layout}")
    w(f"- **Pantalla inicial:** {fe.start_screen} ({screens.get(fe.start_screen, '?')})")
    if fe.design_guidelines:
        w("- **Lineamientos:** " + "; ".join(fe.design_guidelines))
    w(
        "- **Guía de diseño base:** [Material Design 3](https://m3.material.io/) de Google: "
        "[iconos Material Symbols](https://fonts.google.com/icons), objetivos táctiles de 48 dp, espaciado en múltiplos de 4/8 dp, "
        "componentes estándar y [accesibilidad](https://m3.material.io/foundations/designing/overview) (contraste WCAG AA, foco visible, etiquetas)."
    )
    w("")
    w("### Mapa de navegación")
    w("")
    w("```mermaid")
    w(navigation_map(fe))
    w("```")
    w("")
    w("### Pantallas")
    w("")
    for s in fe.screens:
        w(f"#### {s.id} · {s.name} — `{s.route}`")
        w("")
        w(s.purpose)
        w("")
        w(f"- **Acceso:** {_roles_text(s.roles, names)}")
        if s.data_endpoints:
            w(f"- **Datos al abrir:** {', '.join(s.data_endpoints)}")
        if s.journey_steps:
            w(f"- **Pasos del recorrido principal:** {', '.join(str(n) for n in s.journey_steps)}")
        w("")
        for sec in s.sections:
            w(f"- **{sec.title}** ({sec.kind}): {', '.join(sec.elements) or '—'}")
            for a in sec.actions:
                target = []
                if a.endpoint_id:
                    target.append(f"llama a {a.endpoint_id}")
                if a.target_screen:
                    target.append(f"va a {a.target_screen} ({screens.get(a.target_screen, '?')})")
                who = f" · visible para {_roles_text(a.roles, names)}" if a.roles else ""
                w(f"  - Acción «{a.label}» → {'; '.join(target) or a.kind}{who}")
        if s.states:
            w(f"- **Estados:** {'; '.join(s.states)}")
        w("")
    return out


# ---------------------------------------------------------------------------
# Documento 2: arquitectura
# ---------------------------------------------------------------------------


def architecture_markdown(
    *,
    project_name: str,
    brief: ProductBrief,
    api: ApiSpec,
    spec: ArchitectureSpec,
    evaluation: ArchitectureEvaluation | None,
    version: int,
    generated_at: datetime,
) -> str:
    names = _user_names(brief)
    scenario = get_architecture(spec.scenario_id) or {"name": spec.scenario_id}
    sso = uses_sso(api)
    out: list[str] = []
    w = out.append
    w(f"# {brief.product_name or project_name} — Arquitectura")
    w("")
    w(
        f"> Generado por Ideator el {generated_at:%Y-%m-%d %H:%M} UTC · Versión {version}.  \n"
        "> Complementa a `especificacion-producto.md`, que define qué construir. Este documento define con qué y cómo."
    )
    w("")
    w("## 0. Instrucciones para la IA que implementa")
    w("")
    w(
        _bullets(
            [
                "Usa exactamente el stack y las versiones de §2. No sustituyas tecnologías ni agregues servicios no listados.",
                "Respeta la estructura del repositorio de §4 y las variables de entorno de §10 (mismos nombres).",
                (
                    "Implementa autenticación, SSO y autorización como indica §9: la autorización se valida en el backend en cada endpoint."
                    if sso
                    else "Implementa autenticación y autorización como indica §9 (este producto no usa SSO): la autorización se valida en el backend en cada endpoint."
                ),
                "Los códigos de respuesta de cada endpoint son los de `especificacion-producto.md` §10; si algo de este documento parece contradecirlos, manda §10.",
                "Los secretos nunca van en el código ni en el repositorio: se leen de variables de entorno o del gestor de secretos.",
                "Incluye health checks, logs estructurados y las pruebas de §12 y §13 como parte de la entrega.",
                "Antes de terminar, recorre la checklist de §16.",
            ]
        )
    )
    w("")
    w(f"## 1. Arquitectura seleccionada: {spec.scenario_id} · {scenario['name']}")
    w("")
    w(spec.summary)
    w("")
    w(f"**Por qué esta arquitectura:** {spec.rationale}")
    w("")
    if evaluation:
        w("### Alternativas evaluadas")
        w("")
        by_id = {s.scenario_id: s for s in evaluation.scores}
        rows = []
        for a in BASE_ARCHITECTURES:
            sc = by_id.get(a["id"])
            rows.append(
                [
                    f"{a['id']} · {a['name']}" + (" ✅" if a["id"] == spec.scenario_id else ""),
                    f"{sc.fit}/5" if sc else "—",
                    "; ".join(sc.strengths[:2]) if sc else "",
                    "; ".join(sc.risks[:2]) if sc else "",
                ]
            )
        w(_table(["Escenario", "Ajuste", "A favor", "En contra"], rows))
        w("")
    w("## 2. Stack tecnológico")
    w("")
    w(_table(["Capa", "Tecnología", "Versión", "Justificación"], [[t.layer, t.technology, t.version, t.justification] for t in spec.stack]))
    w("")
    w("## 3. Componentes")
    w("")
    if spec.components:
        w("```mermaid")
        w(components_diagram(spec))
        w("```")
        w("")
    w(
        _table(
            ["Componente", "Responsabilidad", "Tecnología", "Se comunica con"],
            [[c.name, c.responsibility, c.technology, ", ".join(c.communicates_with)] for c in spec.components],
        )
    )
    w("")
    w("## 4. Estructura del repositorio")
    w("")
    w("```text")
    w(spec.repository_structure.strip())
    w("```")
    w("")
    w("## 5. Persistencia")
    w("")
    w(spec.persistence)
    w("")
    w("El esquema exacto (tablas, columnas, relaciones y DDL) está en `especificacion-producto.md` §9 y debe implementarse con migraciones.")
    w("")
    w("## 6. Backend")
    w("")
    w(spec.backend)
    w("")
    w("## 7. Frontend")
    w("")
    w(spec.frontend)
    w("")
    w("## 8. Comunicación entre componentes")
    w("")
    w(spec.communication)
    w("")
    w("## 9. Autenticación, SSO y autorización" if sso else "## 9. Autenticación y autorización")
    w("")
    w("### Autenticación")
    w("")
    w(spec.authentication)
    w("")
    if sso:
        w("### Single Sign-On")
        w("")
        w(spec.sso)
        w("")
        w("```mermaid")
        w(SSO_SEQUENCE)
        w("```")
        w("")
    w("### Autorización")
    w("")
    w(spec.authorization)
    w("")
    w(
        _table(
            ["Rol", "Nombre", "Puede", "No puede"],
            [[u.id, u.name, "<br>".join(u.permissions), "<br>".join(u.restrictions)] for u in brief.user_types],
        )
    )
    w("")
    protected = [ep for ep in api.endpoints if ep.auth == "authenticated" and (ep.allowed_roles != ["*"] or ep.authorization_rule)]
    if protected:
        w("Endpoints con reglas de acceso específicas:")
        w("")
        w(
            _table(
                ["Endpoint", "Roles", "Regla sobre el recurso"],
                [[f"{ep.id} `{ep.method} {ep.path}`", _roles_text(ep.allowed_roles, names), ep.authorization_rule] for ep in protected],
            )
        )
        w("")
    w("## 10. Configuración y variables de entorno")
    w("")
    w(
        _table(
            ["Variable", "Descripción", "Ejemplo", "Secreta", "Obligatoria"],
            [
                [f"`{v.name}`", v.description, "(definir en el gestor de secretos)" if v.secret else f"`{v.example}`", "Sí" if v.secret else "No", "Sí" if v.required else "No"]
                for v in spec.configuration
            ],
        )
    )
    w("")
    w("## 11. Ambientes y despliegue")
    w("")
    w(_bullets(spec.environments))
    w("")
    w(spec.deployment)
    w("")
    w("## 12. Observabilidad")
    w("")
    w(spec.observability)
    w("")
    w("## 13. Pruebas")
    w("")
    w(spec.testing)
    w("")
    w("## 14. Seguridad")
    w("")
    w(_bullets(spec.security))
    w("")
    w("## 15. Riesgos y mitigaciones")
    w("")
    w(_bullets(spec.risks))
    w("")
    w("## 16. Checklist de verificación")
    w("")
    w(
        "\n".join(
            f"- [ ] {item}"
            for item in [
                "La aplicación levanta en local siguiendo §11 y todas las variables de §10 están documentadas en un `.env.example`.",
                "Las migraciones crean exactamente el esquema de `especificacion-producto.md` §9.",
                "Cada endpoint de `especificacion-producto.md` §10 existe con su método, ruta, validaciones y códigos de respuesta.",
                "Cada endpoint responde exactamente los códigos documentados en `especificacion-producto.md` §10 (401 sin sesión, 403 sin permiso, 404 inexistente, según corresponda).",
                *(["El inicio de sesión con SSO funciona con el proveedor configurado."] if sso else []),
                "Los health checks responden y los logs son estructurados.",
                "Todas las pruebas automatizadas pasan.",
            ]
        )
    )
    w("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Exportar una etapa («Copiar para la IA»)
# ---------------------------------------------------------------------------

STAGE_EXPORT_TITLES = {"data_model": "Modelo de datos", "api": "Backend y API", "frontend": "Pantallas y navegación"}


def stage_markdown(
    *,
    kind: str,
    project_name: str,
    brief: ProductBrief,
    model: DataModel | None = None,
    api: ApiSpec | None = None,
    fe: FrontendSpec | None = None,
    spec: ArchitectureSpec | None = None,
    evaluation: ArchitectureEvaluation | None = None,
    version: int,
    generated_at: datetime,
) -> str:
    """Markdown de una sola etapa, para copiarlo a otra IA o compartirlo con el equipo."""
    if kind == "product":
        return product_spec_markdown(
            project_name=project_name, brief=brief, model=None, api=None, fe=None, version=version, generated_at=generated_at, stage_only=True
        )
    if kind == "architecture":
        if spec is None or api is None:
            raise ValueError("La arquitectura todavía no está detallada.")
        return architecture_markdown(
            project_name=project_name, brief=brief, api=api, spec=spec, evaluation=evaluation, version=version, generated_at=generated_at
        )
    names = _user_names(brief)
    body: list[str]
    if kind == "data_model" and model is not None:
        body = _data_model_section(model)
    elif kind == "api" and api is not None:
        body = _api_section(api, names)
    elif kind == "frontend" and fe is not None:
        body = _frontend_section(fe, names)
    else:
        raise ValueError("La etapa todavía no tiene contenido para exportar.")
    head = [
        f"# {brief.product_name or project_name} — {STAGE_EXPORT_TITLES[kind]}",
        "",
        f"> Exportado desde Ideator el {generated_at:%Y-%m-%d %H:%M} UTC · Proyecto «{project_name}» · Versión {version} de la etapa.",
        "",
    ]
    return "\n".join(head + body)
