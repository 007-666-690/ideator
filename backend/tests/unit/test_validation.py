import copy

import pytest

from app.ideator import fake
from app.ideator.schemas import ApiSpec, DataModel, FrontendSpec, ProductBrief, empty_brief
from app.ideator.validation import (
    derive_relationships,
    junction_tables,
    product_checklist,
    validate_api,
    validate_data_model,
    validate_frontend,
    validate_product,
)


@pytest.fixture
def brief():
    return ProductBrief.model_validate(copy.deepcopy(fake.BRIEF_COMPLETE))


@pytest.fixture
def model_data():
    return copy.deepcopy(fake.DATA_MODEL)


@pytest.fixture
def api_data():
    return copy.deepcopy(fake.API_SPEC)


@pytest.fixture
def fe_data():
    return copy.deepcopy(fake.FRONTEND_SPEC)


def codes(issues, severity="error"):
    return {i["code"] for i in issues if i["severity"] == severity}


# --- Producto -----------------------------------------------------------------


def test_empty_brief_fails_every_check():
    checklist = product_checklist(empty_brief("X"), open_blocking=1)
    assert not any(c["ok"] for c in checklist)
    assert "product.blocking" in codes(validate_product(empty_brief("X"), 1))


def test_complete_brief_passes(brief):
    assert all(c["ok"] for c in product_checklist(brief, 0))
    assert codes(validate_product(brief, 0)) == set()
    assert "product.pending_assumptions" in codes(validate_product(brief, 0), "warning")


def test_missing_edge_category_is_reported(brief):
    brief.edge_cases = [e for e in brief.edge_cases if e.category != "dependencia_caida"]
    item = next(c for c in product_checklist(brief, 0) if c["key"] == "edge_cases")
    assert not item["ok"]
    assert "Dependencia externa" in item["detail"]


def test_requirement_without_criteria(brief):
    brief.functional_requirements[0].acceptance_criteria = []
    assert "product.requirements" in codes(validate_product(brief, 0))


# --- Modelo de datos ------------------------------------------------------------


def test_valid_model_has_no_errors(model_data, brief):
    assert codes(validate_data_model(DataModel.model_validate(model_data), brief)) == set()


def test_fk_to_missing_table(model_data):
    model_data["tables"][3]["columns"][1]["foreign_key"]["table"] = "canchas"
    assert "dm.fk_table" in codes(validate_data_model(DataModel.model_validate(model_data)))


def test_fk_type_mismatch(model_data):
    model_data["tables"][3]["columns"][1]["type"] = "integer"
    assert "dm.fk_type" in codes(validate_data_model(DataModel.model_validate(model_data)))


def test_missing_pk_bad_type_and_names(model_data):
    model_data["tables"][2]["columns"][0]["primary_key"] = False
    model_data["tables"][2]["columns"][1]["type"] = "string"
    model_data["tables"][2]["columns"][2]["name"] = "Sport"
    found = codes(validate_data_model(DataModel.model_validate(model_data)))
    assert {"dm.no_pk", "dm.bad_type", "dm.column_name"} <= found


def test_set_null_requires_nullable(model_data):
    col = model_data["tables"][4]["columns"][5]
    assert col["name"] == "created_by"
    col["nullable"] = False
    assert "dm.fk_set_null" in codes(validate_data_model(DataModel.model_validate(model_data)))


def test_relationships_are_derived_from_fks(model_data):
    rels = derive_relationships(DataModel.model_validate(model_data))
    res = next(r for r in rels if r["child"] == "reservations" and r["parent"] == "courts")
    assert res["cardinality"] == "1:N"
    assert res["optional"] is False
    blocks = next(r for r in rels if r["column"] == "created_by")
    assert blocks["optional"] is True


def test_junction_table_detection():
    model = DataModel.model_validate(
        {
            "summary": "",
            "enums": [],
            "notes": [],
            "tables": [
                {"name": "a", "description": "", "indexes": [], "unique_constraints": [], "checks": [], "columns": [
                    {"name": "id", "type": "uuid", "nullable": False, "primary_key": True, "unique": False, "default": None, "foreign_key": None, "description": ""}]},
                {"name": "b", "description": "", "indexes": [], "unique_constraints": [], "checks": [], "columns": [
                    {"name": "id", "type": "uuid", "nullable": False, "primary_key": True, "unique": False, "default": None, "foreign_key": None, "description": ""}]},
                {"name": "a_b", "description": "", "indexes": [], "unique_constraints": [["a_id", "b_id"]], "checks": [], "columns": [
                    {"name": "id", "type": "uuid", "nullable": False, "primary_key": True, "unique": False, "default": None, "foreign_key": None, "description": ""},
                    {"name": "a_id", "type": "uuid", "nullable": False, "primary_key": False, "unique": False, "default": None, "foreign_key": {"table": "a", "column": "id", "on_delete": "CASCADE"}, "description": ""},
                    {"name": "b_id", "type": "uuid", "nullable": False, "primary_key": False, "unique": False, "default": None, "foreign_key": {"table": "b", "column": "id", "on_delete": "CASCADE"}, "description": ""}]},
            ],
        }
    )
    assert junction_tables(model) == [{"table": "a_b", "left": "a", "right": "b"}]


# --- API ---------------------------------------------------------------------------


def test_valid_api(api_data, model_data, brief):
    issues = validate_api(ApiSpec.model_validate(api_data), DataModel.model_validate(model_data), brief)
    assert codes(issues) == set()


def test_api_status_rules(api_data, model_data, brief):
    ep = api_data["endpoints"][9]  # cancelar reserva: auth, roles, id en ruta
    ep["responses"] = [r for r in ep["responses"] if r["status"] not in (401, 403, 404)]
    found = codes(validate_api(ApiSpec.model_validate(api_data), DataModel.model_validate(model_data), brief))
    assert {"api.missing_401", "api.missing_403", "api.missing_404"} <= found


def test_api_body_requires_400_or_422(api_data, model_data, brief):
    ep = api_data["endpoints"][7]  # crear reserva
    ep["responses"] = [r for r in ep["responses"] if r["status"] != 422]
    assert "api.missing_400" in codes(validate_api(ApiSpec.model_validate(api_data), DataModel.model_validate(model_data), brief))


def test_api_path_params_and_unknown_refs(api_data, model_data, brief):
    ep = api_data["endpoints"][13]
    ep["params"] = []
    ep["tables"] = ["canchas"]
    ep["requirements"] = ["RF-99"]
    ep["allowed_roles"] = ["Admin"]
    found = codes(validate_api(ApiSpec.model_validate(api_data), DataModel.model_validate(model_data), brief))
    assert {"api.path_params", "api.unknown_table", "api.unknown_req", "api.unknown_role"} <= found


def test_uncovered_must_requirement(api_data, model_data, brief):
    for ep in api_data["endpoints"]:
        ep["requirements"] = [r for r in ep["requirements"] if r != "RF-03"]
    found = codes(validate_api(ApiSpec.model_validate(api_data), DataModel.model_validate(model_data), brief))
    assert "api.uncovered_req" in found


def test_duplicate_route(api_data, model_data, brief):
    api_data["endpoints"].append(copy.deepcopy(api_data["endpoints"][0]) | {"id": "EP-99"})
    assert "api.duplicate_route" in codes(validate_api(ApiSpec.model_validate(api_data), DataModel.model_validate(model_data), brief))


# --- Frontend -------------------------------------------------------------------


def test_valid_frontend(fe_data, api_data, brief):
    assert codes(validate_frontend(FrontendSpec.model_validate(fe_data), ApiSpec.model_validate(api_data), brief)) == set()


def test_frontend_unknown_endpoint_and_target(fe_data, api_data, brief):
    fe_data["screens"][3]["sections"][0]["actions"][0]["endpoint_id"] = "EP-77"
    fe_data["screens"][3]["sections"][0]["actions"][1]["target_screen"] = "PA-99"
    found = codes(validate_frontend(FrontendSpec.model_validate(fe_data), ApiSpec.model_validate(api_data), brief))
    assert {"fe.unknown_endpoint", "fe.unknown_screen"} <= found


def test_frontend_journey_coverage(fe_data, api_data, brief):
    for s in fe_data["screens"]:
        s["journey_steps"] = [n for n in s["journey_steps"] if n != 4]
    assert "fe.journey_uncovered" in codes(validate_frontend(FrontendSpec.model_validate(fe_data), ApiSpec.model_validate(api_data), brief))


def test_submit_needs_endpoint(fe_data, api_data, brief):
    fe_data["screens"][4]["sections"][0]["actions"][0]["endpoint_id"] = None
    assert "fe.action_endpoint" in codes(validate_frontend(FrontendSpec.model_validate(fe_data), ApiSpec.model_validate(api_data), brief))
