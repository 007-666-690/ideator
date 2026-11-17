import { Fragment, useState } from "react";
import { api } from "../../api";
import { Tabs } from "../../components/ui";
import type { ApiField, ApiSpec, Endpoint } from "../../types";
import type { StageCtx } from "../Project";
import { ChangeRequest, GenerateFirst, JsonEditor, StageIntro } from "./common";

function statusClass(s: number) {
  return `status s${String(s)[0]}`;
}

function Fields({ fields }: { fields: ApiField[] }) {
  if (!fields.length) return null;
  return (
    <table className="data" style={{ marginTop: 6 }}>
      <thead>
        <tr>
          <th>Campo</th>
          <th>Tipo</th>
          <th>Obligatorio</th>
          <th>Validación</th>
          <th>Descripción</th>
        </tr>
      </thead>
      <tbody>
        {fields.map((f) => (
          <tr key={f.name}>
            <td className="mono">{f.name}</td>
            <td className="mono">{f.type}</td>
            <td>{f.required ? "Sí" : "No"}</td>
            <td>{f.validation}</td>
            <td>{f.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EndpointDetail({ ep }: { ep: Endpoint }) {
  return (
    <div style={{ padding: "6px 4px 14px" }}>
      <p style={{ marginBottom: 6 }}>{ep.description}</p>
      <p className="small muted">
        {ep.auth === "public" ? "Público, sin sesión." : `Requiere sesión. Roles: ${ep.allowed_roles.join(", ") === "*" ? "cualquier usuario autenticado" : ep.allowed_roles.join(", ")}.`}
        {ep.authorization_rule && ` Regla: ${ep.authorization_rule}.`} Tablas: {ep.tables.join(", ") || "ninguna"}. Requisitos: {ep.requirements.join(", ") || "ninguno"}.
      </p>
      {ep.params.length > 0 && (
        <>
          <h4>Parámetros</h4>
          <table className="data">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Ubicación</th>
                <th>Tipo</th>
                <th>Obligatorio</th>
                <th>Descripción</th>
              </tr>
            </thead>
            <tbody>
              {ep.params.map((p) => (
                <tr key={`${p.location}-${p.name}`}>
                  <td className="mono">{p.name}</td>
                  <td>{p.location}</td>
                  <td className="mono">{p.type}</td>
                  <td>{p.required ? "Sí" : "No"}</td>
                  <td>{p.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {ep.request_body.length > 0 && (
        <>
          <h4>Cuerpo de la solicitud</h4>
          <Fields fields={ep.request_body} />
        </>
      )}
      <h4>Respuestas</h4>
      {ep.responses.map((r) => (
        <div key={r.status} style={{ marginBottom: 8 }}>
          <span className={statusClass(r.status)}>{r.status}</span> {r.description}
          {r.body_kind === "error" && <span className="muted small"> (formato de error estándar)</span>}
          {(r.body_kind === "array" || r.body_kind === "paginated") && <span className="muted small"> ({r.body_kind === "array" ? "lista" : "lista paginada"})</span>}
          <Fields fields={r.body_kind === "error" ? [] : r.fields} />
        </div>
      ))}
    </div>
  );
}

export default function ApiStage({ ctx }: { ctx: StageCtx }) {
  const { project, view, run } = ctx;
  const spec: ApiSpec | null = view.content.data;
  const [tab, setTab] = useState<"endpoints" | "json">("endpoints");
  const [open, setOpen] = useState<string | null>(null);

  if (!spec) {
    return (
      <>
        <StageIntro title="Backend y API">Plano define cada endpoint: método, ruta, qué recibe, qué devuelve y los errores posibles, consistente con el modelo de datos aprobado.</StageIntro>
        <GenerateFirst ctx={ctx} what="una especificación de la API" button="Proponer API" />
      </>
    );
  }

  const groups = new Map<string, Endpoint[]>();
  const base = spec.conventions.base_path.replace(/\/$/, "");
  for (const ep of spec.endpoints) {
    const rest = ep.path.startsWith(base) ? ep.path.slice(base.length) : ep.path;
    const key = rest.split("/").filter(Boolean)[0] ?? "/";
    groups.set(key, [...(groups.get(key) ?? []), ep]);
  }

  return (
    <>
      <StageIntro title="Backend y API">
        {spec.summary} Sin sesión válida se responde 401; con sesión pero sin permiso sobre el recurso, 403.
      </StageIntro>
      <Tabs
        tabs={[
          ["endpoints", `Endpoints (${spec.endpoints.length})`],
          ["json", "JSON"],
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "endpoints" ? (
        <>
          <dl className="kv section">
            <dt>Prefijo</dt>
            <dd className="mono">{spec.conventions.base_path}</dd>
            <dt>Autenticación</dt>
            <dd>{spec.conventions.auth_mechanism}</dd>
            <dt>Paginación</dt>
            <dd>{spec.conventions.pagination}</dd>
            <dt>Fechas e ids</dt>
            <dd>
              {spec.conventions.datetime_format}. {spec.conventions.id_format}.
            </dd>
            <dt>Formato de error</dt>
            <dd>
              <pre style={{ margin: 0 }}>{spec.conventions.error_format}</pre>
            </dd>
          </dl>
          {[...groups.entries()].map(([group, eps]) => (
            <div className="section" key={group}>
              <h4 className="mono">/{group}</h4>
              <div className="table-scroll">
                <table className="data">
                  <thead>
                    <tr>
                      <th style={{ width: 64 }}>Id</th>
                      <th style={{ width: 80 }}>Método</th>
                      <th>Ruta</th>
                      <th>Qué hace</th>
                      <th>Acceso</th>
                      <th>Códigos</th>
                    </tr>
                  </thead>
                  <tbody>
                    {eps.map((ep) => (
                      <Fragment key={ep.id}>
                        <tr className={`endpoint-row ${open === ep.id ? "open" : ""}`} onClick={() => setOpen(open === ep.id ? null : ep.id)}>
                          <td className="mono">
                            <button className="btn ghost small" aria-expanded={open === ep.id} style={{ padding: 0 }}>
                              {ep.id}
                            </button>
                          </td>
                          <td>
                            <span className={`method ${ep.method}`}>{ep.method}</span>
                          </td>
                          <td className="mono">{ep.path}</td>
                          <td>{ep.summary}</td>
                          <td className="small">{ep.auth === "public" ? "Público" : ep.allowed_roles.join(", ")}</td>
                          <td className="small">
                            {ep.responses.map((r) => (
                              <span key={r.status} className={statusClass(r.status)} style={{ marginRight: 6 }}>
                                {r.status}
                              </span>
                            ))}
                          </td>
                        </tr>
                        {open === ep.id && (
                          <tr>
                            <td colSpan={6}>
                              <EndpointDetail ep={ep} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </>
      ) : (
        <div className="section">
          <JsonEditor ctx={ctx} value={spec} onSave={(d) => run(() => api.saveStage(project.id, "api", view.version, d, "Edición de la API"), "API guardada.")} />
        </div>
      )}
      <ChangeRequest ctx={ctx} placeholder="Ej.: agrega un endpoint para exportar las reservas del día en CSV, solo para U2" />
    </>
  );
}
