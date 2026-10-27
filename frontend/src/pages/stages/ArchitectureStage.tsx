import { useState } from "react";
import { api } from "../../api";
import { Tabs } from "../../components/ui";
import type { ArchitectureEvaluation, ArchitectureSpec, Scenario } from "../../types";
import type { StageCtx } from "../Project";
import { ChangeRequest, JsonEditor, List, StageIntro } from "./common";

function Fit({ value }: { value: number }) {
  return (
    <span className="fit" aria-label={`Ajuste ${value} de 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <i key={n} className={n <= value ? "on" : ""} />
      ))}
    </span>
  );
}

export default function ArchitectureStage({ ctx }: { ctx: StageCtx }) {
  const { project, view, run, editable, working } = ctx;
  const scenarios: Scenario[] = view.scenarios ?? [];
  const evaluation: ArchitectureEvaluation | null = view.content.evaluation;
  const selected: string | null = view.content.selected;
  const spec: ArchitectureSpec | null = view.content.data;
  const [tab, setTab] = useState<"spec" | "json">("spec");
  const canWork = editable && view.status !== "approved" && view.status !== "locked";
  const score = (id: string) => evaluation?.scores.find((s) => s.scenario_id === id);

  return (
    <>
      <StageIntro title="Arquitectura">
        Ideator compara cinco arquitecturas base con lo que el producto necesita. El equipo elige una y la IA la detalla: tecnologías, autenticación y SSO, despliegue y observabilidad.
      </StageIntro>

      <section className="section">
        <div className="row between">
          <h3 style={{ border: 0, margin: 0 }}>1. Elegir la arquitectura base</h3>
          {canWork && (
            <button className={`btn ${evaluation ? "secondary" : ""}`} disabled={working} onClick={() => run(() => api.evaluateArchitecture(project.id, view.version), "Arquitecturas evaluadas.")}>
              {evaluation ? "Volver a evaluar" : "Evaluar las cinco con IA"}
            </button>
          )}
        </div>
        <hr style={{ margin: "10px 0 16px" }} />
        {evaluation && <p className="prose">{evaluation.justification}</p>}
        <div role="radiogroup" aria-label="Arquitecturas base">
          {scenarios.map((s) => {
            const sc = score(s.id);
            const isSel = selected === s.id;
            return (
              <label key={s.id} className={`scenario ${isSel ? "selected" : ""}`}>
                <input
                  type="radio"
                  name="scenario"
                  checked={isSel}
                  disabled={!canWork || working}
                  onChange={() => run(() => api.selectArchitecture(project.id, view.version, s.id), `Elegiste ${s.id}.`)}
                />
                <div>
                  <h4>
                    {s.id} {s.name}
                  </h4>
                  <p className="small muted" style={{ margin: "2px 0 0" }}>
                    {s.summary}
                  </p>
                </div>
                <div style={{ textAlign: "right" }}>
                  {sc && <Fit value={sc.fit} />}
                  {evaluation?.recommended === s.id && <div className="recommended">Recomendada</div>}
                </div>
                {sc && (
                  <div className="pros-cons">
                    <div>
                      <strong>A favor</strong>
                      <List items={sc.strengths} empty="—" />
                    </div>
                    <div>
                      <strong>En contra</strong>
                      <List items={sc.risks} empty="—" />
                    </div>
                  </div>
                )}
              </label>
            );
          })}
        </div>
      </section>

      <section className="section">
        <div className="row between">
          <h3 style={{ border: 0, margin: 0 }}>2. Arquitectura detallada</h3>
          {canWork && selected && (
            <button className={`btn ${spec ? "secondary" : ""}`} disabled={working} onClick={() => run(() => api.generate(project.id, "architecture", view.version, null), "Arquitectura detallada.")}>
              {spec ? "Volver a detallar" : `Detallar ${selected}`}
            </button>
          )}
        </div>
        <hr style={{ margin: "10px 0 16px" }} />
        {!selected && <p className="muted">Primero elige una arquitectura base.</p>}
        {selected && !spec && <p className="muted">Todavía no se detalla la arquitectura elegida.</p>}
        {spec && (
          <>
            <Tabs
              tabs={[
                ["spec", "Detalle"],
                ["json", "JSON"],
              ]}
              value={tab}
              onChange={setTab}
            />
            {tab === "spec" ? (
              <div className="prose" style={{ maxWidth: "none" }}>
                <p>{spec.summary}</p>
                <p>
                  <strong>Por qué esta arquitectura:</strong> {spec.rationale}
                </p>
                <h4>Stack</h4>
                <div className="table-scroll">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Capa</th>
                        <th>Tecnología</th>
                        <th>Versión</th>
                        <th>Por qué</th>
                      </tr>
                    </thead>
                    <tbody>
                      {spec.stack.map((t) => (
                        <tr key={t.layer}>
                          <td>{t.layer}</td>
                          <td>{t.technology}</td>
                          <td className="mono">{t.version}</td>
                          <td>{t.justification}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <h4 style={{ marginTop: 18 }}>Componentes</h4>
                <List items={spec.components.map((c) => `${c.name} (${c.technology}): ${c.responsibility}${c.communicates_with.length ? `. Habla con ${c.communicates_with.join(", ")}` : ""}`)} />
                <h4 style={{ marginTop: 18 }}>Estructura del repositorio</h4>
                <pre>{spec.repository_structure}</pre>
                <dl className="kv" style={{ marginTop: 18 }}>
                  <dt>Persistencia</dt>
                  <dd>{spec.persistence}</dd>
                  <dt>Backend</dt>
                  <dd>{spec.backend}</dd>
                  <dt>Frontend</dt>
                  <dd>{spec.frontend}</dd>
                  <dt>Comunicación</dt>
                  <dd>{spec.communication}</dd>
                  <dt>Autenticación</dt>
                  <dd>{spec.authentication}</dd>
                  <dt>Single Sign-On</dt>
                  <dd>{spec.sso}</dd>
                  <dt>Autorización</dt>
                  <dd>{spec.authorization}</dd>
                  <dt>Despliegue</dt>
                  <dd>{spec.deployment}</dd>
                  <dt>Observabilidad</dt>
                  <dd>{spec.observability}</dd>
                  <dt>Pruebas</dt>
                  <dd>{spec.testing}</dd>
                </dl>
                <h4 style={{ marginTop: 18 }}>Variables de entorno</h4>
                <div className="table-scroll">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Variable</th>
                        <th>Descripción</th>
                        <th>Ejemplo</th>
                        <th>Secreta</th>
                      </tr>
                    </thead>
                    <tbody>
                      {spec.configuration.map((v) => (
                        <tr key={v.name}>
                          <td className="mono">{v.name}</td>
                          <td>{v.description}</td>
                          <td className="mono">{v.secret ? "—" : v.example}</td>
                          <td>{v.secret ? "Sí" : "No"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="split" style={{ gap: 24, marginTop: 18 }}>
                  <div>
                    <h4>Ambientes</h4>
                    <List items={spec.environments} />
                    <h4 style={{ marginTop: 14 }}>Seguridad</h4>
                    <List items={spec.security} />
                  </div>
                  <div>
                    <h4>Riesgos</h4>
                    <List items={spec.risks} />
                  </div>
                </div>
              </div>
            ) : (
              <JsonEditor ctx={ctx} value={spec} onSave={(d) => run(() => api.saveStage(project.id, "architecture", view.version, d, "Edición de la arquitectura"), "Arquitectura guardada.")} />
            )}
          </>
        )}
      </section>
      {spec && <ChangeRequest ctx={ctx} kind="architecture" placeholder="Ej.: despliega en Azure Container Apps en vez de una VM" />}
    </>
  );
}
