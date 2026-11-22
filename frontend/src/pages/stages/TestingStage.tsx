import { useMemo, useState } from "react";
import { api } from "../../api";
import { Tabs } from "../../components/ui";
import type { StageCtx } from "../Project";
import { JsonEditor, StageIntro } from "./common";

interface TestCase {
  id: string;
  title: string;
  kind: "positivo" | "negativo" | "limite" | "seguridad" | "persistencia";
  requirement_ids: string[];
  source: string;
  role: string;
  preconditions: string[];
  data: string;
  steps: string[];
  expected: string;
  endpoints: string[];
  screens: string[];
  priority: "alta" | "media" | "baja";
}
interface TestingSpec {
  summary: string;
  cases: TestCase[];
  seed: { purpose: string; tables: { table: string; rows: Record<string, unknown>[] }[]; load: string; cleanup: string };
}

const KINDS: Record<TestCase["kind"], string> = {
  positivo: "Positivo",
  negativo: "Negativo",
  limite: "Límite",
  seguridad: "Seguridad",
  persistencia: "Persistencia",
};

type TabKey = "cases" | "coverage" | "seed" | "json";

export default function TestingStage({ ctx }: { ctx: StageCtx }) {
  const { project, view, run, editable, working } = ctx;
  const spec: TestingSpec | null = view.content.data;
  const coverage: Record<string, string[]> = view.coverage ?? {};
  const [tab, setTab] = useState<TabKey>("cases");
  const [filter, setFilter] = useState<TestCase["kind"] | "todos">("todos");
  const [table, setTable] = useState(0);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const t of spec?.cases ?? []) c[t.kind] = (c[t.kind] ?? 0) + 1;
    return c;
  }, [spec]);

  const intro = (
    <StageIntro title="Pruebas y datos">
      Antes de que exista código no hay tests que ejecutar: aquí queda la <strong>especificación de las pruebas funcionales</strong> (qué comprobar, cómo y qué se espera), cada una ligada a su requisito, y los <strong>datos ficticios</strong> para que la app nueva no se vea vacía. Se arma al instante desde lo aprobado, sin IA.
    </StageIntro>
  );

  if (!spec) {
    if (view.status === "locked") return (<>{intro}<p className="muted">Se habilita cuando se aprueba la arquitectura.</p></>);
    return (
      <>
        {intro}
        <div className="box">
          <h3>Aún no hay plan de pruebas</h3>
          <p className="muted">Normalmente se arma solo al aprobar la arquitectura.</p>
          {editable && (
            <button className="btn" disabled={working} onClick={() => run(() => api.generateTesting(project.id, view.version), "Plan de pruebas y datos listos.")}>
              Armar plan de pruebas y datos
            </button>
          )}
        </div>
      </>
    );
  }

  const shown = filter === "todos" ? spec.cases : spec.cases.filter((c) => c.kind === filter);
  const uncovered = Object.entries(coverage).filter(([, ids]) => ids.length === 0);
  const t = spec.seed.tables[table];
  const cols = t?.rows[0] ? Object.keys(t.rows[0]) : [];

  return (
    <>
      {intro}
      <p className="prose">{spec.summary}</p>
      <Tabs<TabKey>
        tabs={[
          ["cases", `Casos de prueba (${spec.cases.length})`],
          ["coverage", `Cobertura${uncovered.length ? ` (${uncovered.length} sin casos)` : ""}`],
          ["seed", "Datos ficticios"],
          ["json", "JSON"],
        ]}
        value={tab}
        onChange={setTab}
      />

      {tab === "cases" && (
        <div className="section">
          <div className="options" role="group" aria-label="Filtrar por tipo">
            <button className="option" aria-pressed={filter === "todos"} onClick={() => setFilter("todos")}>
              Todos ({spec.cases.length})
            </button>
            {(Object.keys(KINDS) as TestCase["kind"][])
              .filter((k) => counts[k])
              .map((k) => (
                <button key={k} className="option" aria-pressed={filter === k} onClick={() => setFilter(k)}>
                  {KINDS[k]} ({counts[k]})
                </button>
              ))}
          </div>
          {shown.map((c) => (
            <details key={c.id} className={`test-case k-${c.kind}`}>
              <summary>
                <span className="mono small">{c.id}</span>
                <span className={`tkind k-${c.kind}`}>{KINDS[c.kind]}</span>
                <strong>{c.title}</strong>
                <span className="small muted">{c.requirement_ids.join(", ") || c.source}</span>
              </summary>
              <dl className="kv">
                <dt>Origen</dt>
                <dd>{c.source}</dd>
                <dt>Rol</dt>
                <dd>{c.role}</dd>
                {c.preconditions.length > 0 && (
                  <>
                    <dt>Precondiciones</dt>
                    <dd>{c.preconditions.join("; ")}</dd>
                  </>
                )}
                <dt>Pasos</dt>
                <dd>
                  <ol style={{ margin: 0, paddingLeft: 18 }}>
                    {c.steps.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ol>
                </dd>
                <dt>Resultado esperado</dt>
                <dd>
                  <strong>{c.expected}</strong>
                </dd>
                {(c.endpoints.length > 0 || c.screens.length > 0) && (
                  <>
                    <dt>Dónde se ve</dt>
                    <dd className="mono small">{[...c.endpoints, ...c.screens].join(", ")}</dd>
                  </>
                )}
                <dt>Prioridad</dt>
                <dd>{c.priority}</dd>
              </dl>
            </details>
          ))}
        </div>
      )}

      {tab === "coverage" && (
        <div className="section table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Requisito</th>
                <th>Casos que lo prueban</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(coverage).map(([rid, ids]) => (
                <tr key={rid}>
                  <td className="mono">{rid}</td>
                  <td>{ids.length ? ids.join(", ") : <strong style={{ color: "var(--danger)" }}>Sin casos: revisar</strong>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "seed" && (
        <div className="section">
          <div className="banner info">{spec.seed.purpose}</div>
          <p className="small">
            <strong>Carga:</strong> {spec.seed.load}
          </p>
          <p className="small">
            <strong>Limpieza:</strong> {spec.seed.cleanup}
          </p>
          <div className="options" role="group" aria-label="Tabla">
            {spec.seed.tables.map((s, i) => (
              <button key={s.table} className="option" aria-pressed={table === i} onClick={() => setTable(i)}>
                {s.table} ({s.rows.length})
              </button>
            ))}
          </div>
          {t && (
            <div className="table-scroll">
              <table className="data seed">
                <thead>
                  <tr>
                    {cols.map((c) => (
                      <th key={c} className="mono">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {t.rows.map((r, i) => (
                    <tr key={i}>
                      {cols.map((c) => (
                        <td key={c} className="mono small">
                          {r[c] === null || r[c] === undefined ? "—" : typeof r[c] === "object" ? JSON.stringify(r[c]) : String(r[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {view.seed_sql && (
            <details style={{ marginTop: 14 }}>
              <summary>
                <strong>Ver seed.sql</strong>
              </summary>
              <div className="row" style={{ margin: "8px 0" }}>
                <button className="btn secondary small" onClick={() => navigator.clipboard?.writeText(view.seed_sql ?? "")}>
                  Copiar SQL
                </button>
              </div>
              <pre className="code">{view.seed_sql}</pre>
            </details>
          )}
        </div>
      )}

      {tab === "json" && (
        <div className="section">
          <JsonEditor ctx={ctx} value={spec} onSave={(d) => run(() => api.saveStage(project.id, "testing", view.version, d, "Edición del plan de pruebas"), "Plan guardado.")} />
        </div>
      )}

      {editable && view.status !== "approved" && view.status !== "locked" && (
        <div className="section">
          <button className="btn secondary" disabled={working} onClick={() => run(() => api.generateTesting(project.id, view.version), "Plan rearmado desde lo aprobado.")}>
            Rearmar desde lo aprobado
          </button>
        </div>
      )}
    </>
  );
}
