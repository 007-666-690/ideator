from datetime import datetime, timezone

from app.ideator import fake
from app.ideator.documents import architecture_markdown, product_spec_markdown
from app.ideator.render import components_diagram, ddl, mermaid_er, navigation_map
from app.ideator.schemas import ApiSpec, ArchitectureEvaluation, ArchitectureSpec, DataModel, FrontendSpec, ProductBrief

BRIEF = ProductBrief.model_validate(fake.BRIEF_COMPLETE)
MODEL = DataModel.model_validate(fake.DATA_MODEL)
API = ApiSpec.model_validate(fake.API_SPEC)
FE = FrontendSpec.model_validate(fake.FRONTEND_SPEC)
ARCH = ArchitectureSpec.model_validate(fake.arch_spec("A1"))
EVAL = ArchitectureEvaluation.model_validate(fake.ARCH_EVALUATION)
NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)


def test_mermaid_er():
    er = mermaid_er(MODEL)
    assert er.startswith("erDiagram")
    assert "courts ||--o{ reservations" in er
    assert "users |o--o{ court_blocks" in er  # created_by opcional
    assert "uuid id PK" in er
    assert "varchar(254) email UK" in er


def test_ddl_is_complete():
    sql = ddl(MODEL)
    assert "CREATE TYPE reservation_status AS ENUM ('confirmed', 'cancelled');" in sql
    assert "CREATE TABLE reservations (" in sql
    assert "id uuid DEFAULT gen_random_uuid() NOT NULL" in sql
    assert "CONSTRAINT ck_reservations_range CHECK (ends_at > starts_at)" in sql
    assert "CONSTRAINT uq_sso_identities_provider_subject UNIQUE (provider, subject)" in sql
    assert "FOREIGN KEY (court_id) REFERENCES courts (id) ON DELETE RESTRICT" in sql
    assert "CREATE INDEX idx_reservations_court_start ON reservations (court_id, starts_at);" in sql
    assert "role user_role DEFAULT 'member' NOT NULL" in sql


def test_ddl_ignores_injected_defaults():
    data = fake.DATA_MODEL | {}
    model = DataModel.model_validate(data)
    model.tables[0].columns[1].default = "'x'; DROP TABLE users"
    assert "DROP TABLE" not in ddl(model)


def test_navigation_and_components():
    nav = navigation_map(FE)
    assert nav.startswith("flowchart LR")
    assert 'PA_01 -->|"Ingresar"| PA_03' in nav
    comp = components_diagram(ARCH)
    assert "C1 --> C2" in comp


def test_product_spec_document():
    md = product_spec_markdown(project_name="Club", brief=BRIEF, model=MODEL, api=API, fe=FE, version=3, generated_at=NOW)
    assert md.startswith("# ReservaCancha — Especificación de producto (MVP)")
    assert "Versión 3" in md
    # Trazabilidad requisito → endpoints → pantallas
    assert "- **Endpoints:** EP-08" in md
    assert "- **Pantallas:** PA-04" in md
    # Recorrido con pantalla por paso
    assert "| 4 | U1 | Confirma la reserva |" in md
    # Fuera de alcance explícito
    assert "Fuera del MVP (no implementar)" in md and "**X1** Pago en línea" in md
    # Cada endpoint con respuestas
    assert "#### EP-10 · `POST /api/v1/reservations/{reservation_id}/cancel`" in md
    assert "- `404` — La reserva no existe" in md
    # Pantallas con acciones ligadas a endpoints
    assert "Acción «Confirmar reserva» → llama a EP-08; va a PA-05" in md
    # Supuestos no aceptados no aparecen como aceptados
    assert "_(no hay supuestos)_" in md


def test_architecture_document():
    md = architecture_markdown(project_name="Club", brief=BRIEF, api=API, spec=ARCH, evaluation=EVAL, version=1, generated_at=NOW)
    assert "## 1. Arquitectura seleccionada: A1 · Monolito modular en Python" in md
    assert "A1 · Monolito modular en Python ✅" in md
    assert "| `SECRET_KEY` | Firma de los JWT | (definir en el gestor de secretos) | Sí | Sí |" in md
    assert "sequenceDiagram" in md
    assert "EP-10 `POST /api/v1/reservations/{reservation_id}/cancel`" in md
    assert "- [ ] Cada endpoint responde exactamente los códigos documentados" in md
    # La API de ejemplo tiene SSO con Google: la sección y la checklist lo incluyen
    assert "## 9. Autenticación, SSO y autorización" in md and "El inicio de sesión con SSO funciona" in md


def test_architecture_without_sso_omits_sso_sections():
    api = API.model_copy(deep=True)
    api.endpoints = [ep for ep in api.endpoints if "/sso" not in ep.path]
    md = architecture_markdown(project_name="Club", brief=BRIEF, api=api, spec=ARCH, evaluation=EVAL, version=1, generated_at=NOW)
    assert "## 9. Autenticación y autorización" in md
    assert "sequenceDiagram" not in md and "Single Sign-On" not in md
    assert "SSO funciona" not in md
    assert "este producto no usa SSO" in md


def test_review_flags_stages_that_reject_assumptions():
    from app.ideator.engine import rejects_assumptions

    assert rejects_assumptions({"notes": ["No se adopta el mínimo de 12 caracteres porque figura como supuesto no aceptado."]})
    assert rejects_assumptions({"notes": ["la paginación de 20 y el orden alfabético aparecen como supuestos no aceptados"]})
    assert not rejects_assumptions({"notes": ["Se aplica el supuesto S-04: 20 por página."]})


def test_markdown_tables_escape_pipes():
    brief = BRIEF.model_copy(deep=True)
    brief.expected_outcomes[0].description = "Uno | dos"
    md = product_spec_markdown(project_name="Club", brief=brief, model=MODEL, api=API, fe=FE, version=1, generated_at=NOW)
    assert "Uno \\| dos" in md
