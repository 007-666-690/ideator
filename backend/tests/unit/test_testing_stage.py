"""Plan de pruebas funcionales y datos sintéticos (etapa «Pruebas y datos»)."""

from app.ideator.testing import build_seed, build_testing, coverage, seed_sql, validate_testing



def _artifacts():
    from tests.unit.test_render_documents import API, BRIEF as B, FE, MODEL

    return B, MODEL, API, FE


def test_every_requirement_has_cases_and_there_are_negative_and_security_cases():
    brief, model, api, fe = _artifacts()
    spec = build_testing(brief, model, api, fe)
    cov = coverage(brief, spec.cases)
    assert all(cov[r.id] for r in brief.functional_requirements)
    kinds = {c.kind for c in spec.cases}
    assert "seguridad" in kinds and "persistencia" in kinds and ({"negativo", "limite"} & kinds)
    assert len({c.id for c in spec.cases}) == len(spec.cases)
    assert not [i for i in validate_testing(spec, brief, model) if i["severity"] == "error"]


def test_uncovered_must_requirement_is_an_error():
    brief, model, api, fe = _artifacts()
    spec = build_testing(brief, model, api, fe)
    rid = brief.functional_requirements[0].id
    spec.cases = [c for c in spec.cases if rid not in c.requirement_ids]
    issues = validate_testing(spec, brief, model)
    assert any(i["code"] == "test.uncovered" and i["path"] == rid for i in issues)


def test_seed_respects_foreign_keys_uniqueness_and_is_fictitious():
    _, model, _, _ = _artifacts()
    seed = build_seed(model)
    tables = {t.table: t.rows for t in seed.tables}
    order = [t.table for t in seed.tables]
    for t in model.tables:
        pk = next(c.name for c in t.columns if c.primary_key)
        ids = [r[pk] for r in tables[t.name]]
        assert len(ids) == len(set(ids))
        for c in t.columns:
            if c.foreign_key and c.foreign_key.table != t.name:
                parent_pk = next(x.name for x in next(m for m in model.tables if m.name == c.foreign_key.table).columns if x.primary_key)
                parent_ids = {r[parent_pk] for r in tables[c.foreign_key.table]}
                assert order.index(c.foreign_key.table) < order.index(t.name)  # padres antes que hijos
                assert all(r[c.name] in parent_ids for r in tables[t.name] if r.get(c.name) is not None)
            if c.unique and not c.primary_key:
                vals = [r[c.name] for r in tables[t.name] if r.get(c.name) is not None]
                assert len(vals) == len(set(vals)), (t.name, c.name)
    sql = seed_sql(seed)
    assert sql.startswith("-- DATOS FICTICIOS") and "BEGIN;" in sql and "COMMIT;" in sql
    assert "@ejemplo.test" in sql
