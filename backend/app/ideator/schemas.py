"""Estructuras de cada etapa de Ideator.

Estos modelos se usan para dos cosas:
1. Como esquema de salida estructurada (JSON Schema estricto) del modelo de IA.
2. Para validar las ediciones que hacen los usuarios.

Por compatibilidad con el modo estricto de salidas estructuradas, ningún campo
tiene valor por defecto: todos son obligatorios (las listas pueden ir vacías).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Etapa 1: definición del producto
# ---------------------------------------------------------------------------

EdgeCategory = Literal[
    "falta_informacion",
    "accion_fallida",
    "sin_permisos",
    "recurso_inexistente",
    "datos_invalidos",
    "dependencia_caida",
    "concurrencia",
    "otro",
]
REQUIRED_EDGE_CATEGORIES: tuple[str, ...] = (
    "falta_informacion",
    "accion_fallida",
    "sin_permisos",
    "recurso_inexistente",
    "datos_invalidos",
    "dependencia_caida",
)
EDGE_CATEGORY_LABELS = {
    "falta_informacion": "Falta información",
    "accion_fallida": "Acción que no se puede completar",
    "sin_permisos": "Usuario sin permisos",
    "recurso_inexistente": "Recurso inexistente",
    "datos_invalidos": "Datos inválidos",
    "dependencia_caida": "Dependencia externa no disponible",
    "concurrencia": "Modificaciones concurrentes",
    "otro": "Otro",
}


class UserType(Strict):
    id: str = Field(description="Identificador corto y estable: U1, U2...")
    name: str = Field(description="Nombre del tipo de usuario o rol, ej. 'Administrador del recinto'")
    description: str
    goals: list[str] = Field(description="Qué quiere conseguir con el producto")
    permissions: list[str] = Field(description="Qué puede hacer en el producto")
    restrictions: list[str] = Field(description="Qué NO puede hacer o ver")


class Outcome(Strict):
    id: str = Field(description="R1, R2...")
    description: str
    metric: str = Field(description="Cómo se mide")
    target: str = Field(description="Valor objetivo o criterio de éxito")


class ScopeItem(Strict):
    id: str = Field(description="A1, A2... para dentro del MVP; X1, X2... para fuera")
    description: str
    reason: str = Field(description="Por qué está dentro o por qué queda fuera")


class JourneyStep(Strict):
    number: int
    actor: str = Field(description="Id del tipo de usuario (U1) o 'Sistema'")
    action: str
    system_response: str


class Journey(Strict):
    name: str
    actor: str
    goal: str
    preconditions: list[str]
    steps: list[JourneyStep]
    success_result: str


class Requirement(Strict):
    id: str = Field(description="RF-01, RF-02...")
    title: str
    description: str
    user_types: list[str] = Field(description="Ids de tipos de usuario que lo usan")
    priority: Literal["must", "should", "could"]
    acceptance_criteria: list[str] = Field(description="Criterios verificables (Dado/Cuando/Entonces)")


class BusinessRule(Strict):
    id: str = Field(description="RN-01, RN-02...")
    description: str


class Integration(Strict):
    name: str
    purpose: str
    required_for_mvp: bool
    failure_behavior: str = Field(description="Qué hace el producto si la integración no responde")


class EdgeCase(Strict):
    id: str = Field(description="CB-01, CB-02...")
    category: EdgeCategory
    scenario: str
    expected_behavior: str


class Assumption(Strict):
    id: str = Field(description="S-01, S-02...")
    description: str
    accepted: bool = Field(description="true solo si el equipo lo aceptó; los supuestos nuevos van en false")


class Decision(Strict):
    id: str = Field(description="D-01, D-02...")
    topic: str
    decision: str
    source: Literal["usuario", "delegada_a_ia"]


class GlossaryTerm(Strict):
    term: str
    definition: str


class ProductBrief(Strict):
    product_name: str
    one_liner: str = Field(description="Una frase: qué es y para quién")
    problem: str
    context: str
    current_situation: str = Field(description="Cómo se resuelve hoy y qué duele")
    desired_improvement: str
    user_types: list[UserType]
    expected_outcomes: list[Outcome]
    mvp_in_scope: list[ScopeItem]
    mvp_out_of_scope: list[ScopeItem]
    main_journey: Journey
    functional_requirements: list[Requirement]
    business_rules: list[BusinessRule]
    technical_constraints: list[str]
    integrations: list[Integration]
    security_requirements: list[str]
    non_functional_requirements: list[str]
    edge_cases: list[EdgeCase]
    assumptions: list[Assumption]
    decisions: list[Decision]
    glossary: list[GlossaryTerm]


def empty_brief(name: str = "") -> ProductBrief:
    return ProductBrief(
        product_name=name,
        one_liner="",
        problem="",
        context="",
        current_situation="",
        desired_improvement="",
        user_types=[],
        expected_outcomes=[],
        mvp_in_scope=[],
        mvp_out_of_scope=[],
        main_journey=Journey(name="", actor="", goal="", preconditions=[], steps=[], success_result=""),
        functional_requirements=[],
        business_rules=[],
        technical_constraints=[],
        integrations=[],
        security_requirements=[],
        non_functional_requirements=[],
        edge_cases=[],
        assumptions=[],
        decisions=[],
        glossary=[],
    )


Affects = Literal["datos", "backend", "interfaz", "arquitectura", "alcance", "negocio", "seguridad"]


class LLMQuestion(Strict):
    text: str = Field(description="La pregunta, concreta y con una sola decisión")
    rationale: str = Field(description="Por qué importa y qué cambia según la respuesta")
    blocking: bool
    affects: list[Affects]
    options: list[str] = Field(description="2 a 4 opciones concretas; vacío si es abierta")
    section: str = Field(description="Sección de la definición que completa, ej. 'user_types'")


class ProductTurn(Strict):
    brief: ProductBrief
    resolved_question_refs: list[str] = Field(description="Refs (Q1, Q2...) de preguntas abiertas ya resueltas")
    new_questions: list[LLMQuestion]
    contradictions: list[str]
    assistant_message: str


# ---------------------------------------------------------------------------
# Etapa 2: modelo de datos (físico, PostgreSQL)
# ---------------------------------------------------------------------------


class ForeignKey(Strict):
    table: str
    column: str
    on_delete: Literal["CASCADE", "RESTRICT", "SET NULL", "NO ACTION"]


class Column(Strict):
    name: str
    type: str = Field(description="Tipo PostgreSQL: uuid, text, varchar(n), integer, numeric(p,s), boolean, date, timestamptz, jsonb o el nombre de un enum")
    nullable: bool
    primary_key: bool
    unique: bool
    default: str | None = Field(description="Expresión SQL por defecto o null")
    foreign_key: ForeignKey | None
    description: str


class TableIndex(Strict):
    name: str
    columns: list[str]
    unique: bool


class CheckConstraint(Strict):
    name: str
    expression: str = Field(description="Expresión SQL del CHECK, ej. 'price >= 0'")


class Table(Strict):
    name: str = Field(description="snake_case, plural, en inglés")
    description: str
    columns: list[Column]
    indexes: list[TableIndex]
    unique_constraints: list[list[str]] = Field(description="Restricciones UNIQUE compuestas (lista de columnas)")
    checks: list[CheckConstraint]


class EnumType(Strict):
    name: str
    values: list[str]


class DataModel(Strict):
    summary: str = Field(description="Explicación general del modelo en 3 a 6 frases")
    enums: list[EnumType]
    tables: list[Table]
    notes: list[str] = Field(description="Reglas que se validan en el backend y no en la base de datos")


# ---------------------------------------------------------------------------
# Etapa 3: backend y API
# ---------------------------------------------------------------------------

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
ALLOWED_STATUS = (200, 201, 202, 204, 302, 400, 401, 403, 404, 409, 422, 429, 500, 502, 503)


class ApiParam(Strict):
    name: str
    location: Literal["path", "query", "header"]
    type: str
    required: bool
    description: str


class ApiField(Strict):
    name: str
    type: str = Field(description="string, integer, number, boolean, uuid, date, datetime, enum(a|b), object, array<tipo>")
    required: bool
    description: str
    validation: str = Field(description="Reglas de validación; vacío si no aplica")


class ApiResponse(Strict):
    status: int
    description: str = Field(description="Cuándo ocurre")
    body_kind: Literal["none", "object", "array", "paginated", "error"]
    fields: list[ApiField] = Field(description="Campos del cuerpo (o de cada ítem); vacío para none/error")


class Endpoint(Strict):
    id: str = Field(description="EP-01, EP-02...")
    method: HttpMethod
    path: str
    summary: str
    description: str
    auth: Literal["public", "authenticated"]
    allowed_roles: list[str] = Field(description="Ids de tipos de usuario permitidos (U1...) o ['*'] para cualquier usuario autenticado")
    authorization_rule: str = Field(description="Regla sobre el recurso, ej. 'solo el creador de la reserva'; vacío si no aplica")
    params: list[ApiParam]
    request_body: list[ApiField]
    responses: list[ApiResponse]
    tables: list[str]
    requirements: list[str] = Field(description="Ids RF-xx que implementa")


class ApiConventions(Strict):
    base_path: str
    auth_mechanism: str
    error_format: str
    pagination: str
    datetime_format: str
    id_format: str


class ApiSpec(Strict):
    summary: str
    conventions: ApiConventions
    endpoints: list[Endpoint]


# ---------------------------------------------------------------------------
# Etapa 4: frontend
# ---------------------------------------------------------------------------


class UIAction(Strict):
    label: str
    kind: Literal["navigate", "submit", "delete", "download", "open_modal", "other"]
    endpoint_id: str | None
    target_screen: str | None
    roles: list[str] = Field(description="Ids de tipos de usuario que ven esta acción; vacío = todos los del screen")


class UISection(Strict):
    title: str
    kind: Literal[
        "form", "table", "list", "detail", "cards", "chart", "text", "calendar", "map", "chat", "filters", "tabs", "other"
    ]
    elements: list[str] = Field(description="Campos, columnas o contenidos visibles")
    actions: list[UIAction]


class Screen(Strict):
    id: str = Field(description="PA-01, PA-02...")
    name: str
    route: str
    purpose: str
    roles: list[str] = Field(description="Ids de tipos de usuario con acceso, o ['publico'] si no requiere sesión")
    data_endpoints: list[str] = Field(description="Endpoints (EP-xx) que carga al abrir")
    sections: list[UISection]
    states: list[str] = Field(description="Estados vacío/cargando/error y qué muestra cada uno")
    journey_steps: list[int] = Field(description="Pasos del recorrido principal que cubre")


class NavLink(Strict):
    from_screen: str
    to_screen: str
    trigger: str


class FrontendSpec(Strict):
    summary: str
    layout: str = Field(description="Estructura global: navegación, cabecera, menú según rol")
    design_guidelines: list[str]
    start_screen: str
    screens: list[Screen]
    navigation: list[NavLink]


# ---------------------------------------------------------------------------
# Etapa 5: arquitectura
# ---------------------------------------------------------------------------


class ScenarioScore(Strict):
    scenario_id: str
    fit: int = Field(description="1 (no calza) a 5 (calza perfecto)")
    strengths: list[str]
    risks: list[str]


class ArchitectureEvaluation(Strict):
    scores: list[ScenarioScore]
    recommended: str
    justification: str


class TechChoice(Strict):
    layer: str
    technology: str
    version: str
    justification: str


class Component(Strict):
    name: str
    responsibility: str
    technology: str
    communicates_with: list[str]


class EnvVar(Strict):
    name: str
    description: str
    example: str
    secret: bool
    required: bool


class ArchitectureSpec(Strict):
    scenario_id: str
    summary: str
    rationale: str = Field(description="Por qué esta arquitectura calza con el producto y por qué no las otras")
    stack: list[TechChoice]
    components: list[Component]
    repository_structure: str = Field(description="Árbol de carpetas del repositorio")
    persistence: str
    backend: str
    frontend: str
    communication: str
    authentication: str
    sso: str
    authorization: str
    configuration: list[EnvVar]
    environments: list[str]
    deployment: str
    observability: str
    testing: str
    security: list[str]
    risks: list[str]


# ---------------------------------------------------------------------------
# Etapa 6: revisión de consistencia
# ---------------------------------------------------------------------------


class ReviewFinding(Strict):
    severity: Literal["critica", "importante", "menor"]
    area: Literal["producto", "datos", "api", "pantallas", "arquitectura", "transversal"]
    description: str
    suggestion: str


class ConsistencyReview(Strict):
    findings: list[ReviewFinding]
    summary: str


# ---------------------------------------------------------------------------
# Esquemas por etapa (para validar ediciones manuales)
# ---------------------------------------------------------------------------

STAGE_SCHEMAS: dict[str, type[BaseModel]] = {
    "product": ProductBrief,
    "data_model": DataModel,
    "api": ApiSpec,
    "frontend": FrontendSpec,
    "architecture": ArchitectureSpec,
}
