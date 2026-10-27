"""Representaciones derivadas: diagramas Mermaid y DDL SQL.

Todo se genera de forma determinista desde la estructura aprobada, para que el
diagrama, el DDL y el documento final digan exactamente lo mismo.
"""

from __future__ import annotations

import re

from .schemas import ArchitectureSpec, DataModel, FrontendSpec
from .validation import derive_relationships, normalize_type

_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _mid(text: str) -> str:
    """Id seguro para Mermaid."""
    return _SAFE.sub("_", text) or "x"


def _mlabel(text: str) -> str:
    return text.replace('"', "'").replace("\n", " ").strip()


def mermaid_er(model: DataModel) -> str:
    lines = ["erDiagram"]
    for t in model.tables:
        lines.append(f"    {_mid(t.name)} {{")
        for c in t.columns:
            ctype = re.sub(r"[\s,]+", "_", normalize_type(c.type)).replace("[]", "_array")
            ctype = re.sub(r"[^A-Za-z0-9_()\-]", "", ctype) or "text"
            keys = []
            if c.primary_key:
                keys.append("PK")
            if c.foreign_key:
                keys.append("FK")
            if c.unique and not c.primary_key:
                keys.append("UK")
            key_txt = f" {', '.join(keys)}" if keys else ""
            comment = "" if not c.nullable or c.primary_key else ' "opcional"'
            lines.append(f"        {ctype} {_mid(c.name)}{key_txt}{comment}")
        lines.append("    }")
    for r in derive_relationships(model):
        if not r["parent_exists"]:
            continue
        left = "|o" if r["optional"] else "||"
        right = "o|" if r["cardinality"] == "1:1" else "o{"
        lines.append(f'    {_mid(r["parent"])} {left}--{right} {_mid(r["child"])} : "{_mlabel(r["column"])}"')
    return "\n".join(lines)


def _sql_default(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip().rstrip(";")
    if not v or ";" in v or "--" in v:
        return None
    return v


def _sql_type(t: str, enum_names: set[str]) -> str:
    n = normalize_type(t)
    return n if n in enum_names else n


def ddl(model: DataModel) -> str:
    enum_names = {e.name for e in model.enums}
    out: list[str] = ["-- DDL generado por Ideator (PostgreSQL 15+)", "CREATE EXTENSION IF NOT EXISTS pgcrypto;", ""]
    for e in model.enums:
        values = ", ".join("'" + v.replace("'", "''") + "'" for v in e.values)
        out.append(f"CREATE TYPE {e.name} AS ENUM ({values});")
    if model.enums:
        out.append("")

    fks: list[str] = []
    indexes: list[str] = []
    for t in model.tables:
        defs: list[str] = []
        pk_cols = [c.name for c in t.columns if c.primary_key]
        for c in t.columns:
            parts = [f"    {c.name} {_sql_type(c.type, enum_names)}"]
            default = _sql_default(c.default)
            if default is None and c.primary_key and normalize_type(c.type) == "uuid" and len(pk_cols) == 1:
                default = "gen_random_uuid()"
            if default:
                parts.append(f"DEFAULT {default}")
            if not c.nullable or c.primary_key:
                parts.append("NOT NULL")
            if c.unique and not c.primary_key:
                parts.append("UNIQUE")
            defs.append(" ".join(parts))
            if c.foreign_key:
                fk = c.foreign_key
                fks.append(
                    f"ALTER TABLE {t.name} ADD CONSTRAINT fk_{t.name}_{c.name} FOREIGN KEY ({c.name}) "
                    f"REFERENCES {fk.table} ({fk.column}) ON DELETE {fk.on_delete};"
                )
        if pk_cols:
            defs.append(f"    CONSTRAINT pk_{t.name} PRIMARY KEY ({', '.join(pk_cols)})")
        for uc in t.unique_constraints:
            if uc:
                defs.append(f"    CONSTRAINT uq_{t.name}_{'_'.join(uc)} UNIQUE ({', '.join(uc)})")
        for ck in t.checks:
            expr = ck.expression.strip().rstrip(";")
            if expr and ";" not in expr:
                defs.append(f"    CONSTRAINT {ck.name} CHECK ({expr})")
        out.append(f"-- {t.description}".rstrip())
        out.append(f"CREATE TABLE {t.name} (")
        out.append(",\n".join(defs))
        out.append(");")
        out.append("")
        for idx in t.indexes:
            unique = "UNIQUE " if idx.unique else ""
            indexes.append(f"CREATE {unique}INDEX {idx.name} ON {t.name} ({', '.join(idx.columns)});")
    if fks:
        out.append("-- Claves foráneas")
        out.extend(fks)
        out.append("")
    if indexes:
        out.append("-- Índices")
        out.extend(indexes)
    return "\n".join(out).rstrip() + "\n"


def navigation_map(spec: FrontendSpec) -> str:
    lines = ["flowchart LR"]
    for s in spec.screens:
        shape = f'(["{_mlabel(s.name)}"])' if s.id == spec.start_screen else f'["{_mlabel(s.id + " · " + s.name)}"]'
        lines.append(f"    {_mid(s.id)}{shape}")
    seen: set[tuple[str, str]] = set()
    for link in spec.navigation:
        key = (link.from_screen, link.to_screen)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f'    {_mid(link.from_screen)} -->|"{_mlabel(link.trigger)[:40]}"| {_mid(link.to_screen)}')
    for s in spec.screens:
        for sec in s.sections:
            for a in sec.actions:
                if a.target_screen and (s.id, a.target_screen) not in seen:
                    seen.add((s.id, a.target_screen))
                    lines.append(f'    {_mid(s.id)} -->|"{_mlabel(a.label)[:40]}"| {_mid(a.target_screen)}')
    return "\n".join(lines)


def components_diagram(spec: ArchitectureSpec) -> str:
    lines = ["flowchart LR"]
    ids = {}
    for i, c in enumerate(spec.components):
        cid = f"C{i + 1}"
        ids[c.name.lower()] = cid
        lines.append(f'    {cid}["{_mlabel(c.name)}<br/><small>{_mlabel(c.technology)}</small>"]')
    for i, c in enumerate(spec.components):
        for target in c.communicates_with:
            tid = ids.get(target.lower())
            if tid:
                lines.append(f"    C{i + 1} --> {tid}")
    return "\n".join(lines)


SSO_SEQUENCE = """sequenceDiagram
    actor U as Usuario
    participant F as Frontend
    participant B as Backend
    participant I as Proveedor de identidad (OIDC)
    U->>F: Clic en Entrar con SSO
    F->>B: GET /auth/sso/proveedor/login
    B-->>U: 302 a /authorize con state, nonce y PKCE
    U->>I: Inicia sesión en el proveedor
    I-->>B: GET /auth/sso/proveedor/callback con code y state
    B->>I: Intercambia el code por tokens (code_verifier)
    I-->>B: id_token firmado
    B->>B: Valida firma, iss, aud, exp y nonce y busca o crea el usuario
    B-->>F: Cookie de sesión HttpOnly y redirección
    F->>B: Solicitudes con cookie (sin sesión 401, sin permiso 403)"""
