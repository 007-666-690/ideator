import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { ConfirmButton, Mermaid, Tabs, useToast } from "../../components/ui";
import type { Column, DataModel, FK, Table } from "../../types";
import { clone } from "../../util";
import type { StageCtx } from "../Project";
import { ChangeRequest, GenerateFirst, JsonEditor, StageIntro } from "./common";

const TYPES = ["uuid", "text", "varchar(120)", "varchar(254)", "integer", "bigint", "numeric(12,2)", "boolean", "date", "time", "timestamptz", "jsonb"];
const ON_DELETE: FK["on_delete"][] = ["CASCADE", "RESTRICT", "SET NULL", "NO ACTION"];
const ON_DELETE_LABEL: Record<FK["on_delete"], string> = {
  CASCADE: "Borrar también este (CASCADE)",
  RESTRICT: "Impedir el borrado (RESTRICT)",
  "SET NULL": "Dejar vacío (SET NULL)",
  "NO ACTION": "No hacer nada (NO ACTION)",
};

const newColumn = (): Column => ({
  name: "nueva_columna",
  type: "text",
  nullable: true,
  primary_key: false,
  unique: false,
  default: null,
  foreign_key: null,
  description: "",
});

const newTable = (n: number): Table => ({
  name: `nueva_tabla_${n}`,
  description: "",
  columns: [{ name: "id", type: "uuid", nullable: false, primary_key: true, unique: false, default: null, foreign_key: null, description: "Identificador" }],
  indexes: [],
  unique_constraints: [],
  checks: [],
});

type TabKey = "diagram" | "tables" | "relations" | "sql" | "json";

export default function DataModelStage({ ctx }: { ctx: StageCtx }) {
  const { project, view, run, editable, working, setDirty } = ctx;
  const data: DataModel | null = view.content.data;
  const [tab, setTab] = useState<TabKey>("diagram");
  const [draft, setDraft] = useState<DataModel | null>(data ? clone(data) : null);
  const [selected, setSelected] = useState(0);
  const [openCol, setOpenCol] = useState<number | null>(null);
  const [summary, setSummary] = useState("");
  const toast = useToast();

  useEffect(() => {
    setDraft(data ? clone(data) : null);
    setSummary("");
  }, [view.version]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(data), [draft, data]);
  useEffect(() => {
    setDirty(dirty);
  }, [dirty, setDirty]);

  if (!data || !draft) {
    return (
      <>
        <StageIntro title="Modelo de datos">El modelo físico (PostgreSQL) se propone a partir de la definición aprobada: tablas, columnas, tipos, claves y restricciones.</StageIntro>
        <GenerateFirst ctx={ctx} what="un modelo de datos" button="Proponer modelo de datos" />
      </>
    );
  }

  const readOnly = !editable || view.status === "approved" || view.status === "locked";
  const table = draft.tables[Math.min(selected, draft.tables.length - 1)];
  const enumNames = draft.enums.map((e) => e.name);

  const update = (fn: (m: DataModel) => void) =>
    setDraft((m) => {
      const next = clone(m!);
      fn(next);
      return next;
    });
  const updateTable = (fn: (t: Table, m: DataModel) => void) => update((m) => fn(m.tables[selected], m));
  const updateColumn = (ci: number, patch: Partial<Column>) =>
    updateTable((t, m) => {
      const old = t.columns[ci];
      if (patch.name && patch.name !== old.name) {
        // Mantiene las FKs que apuntaban a esta columna
        m.tables.forEach((other) => other.columns.forEach((c) => c.foreign_key && c.foreign_key.table === t.name && c.foreign_key.column === old.name && (c.foreign_key.column = patch.name!)));
      }
      t.columns[ci] = { ...old, ...patch };
    });

  const renameTable = (name: string) =>
    updateTable((t, m) => {
      m.tables.forEach((other) => other.columns.forEach((c) => c.foreign_key?.table === t.name && (c.foreign_key.table = name)));
      t.name = name;
    });

  const removeTable = () => {
    const name = table.name;
    let removed = 0;
    update((m) => {
      m.tables.splice(selected, 1);
      m.tables.forEach((t) =>
        t.columns.forEach((c) => {
          if (c.foreign_key?.table === name) {
            c.foreign_key = null;
            removed++;
          }
        }),
      );
    });
    setSelected(0);
    if (removed) toast(`Se quitaron ${removed} clave(s) foránea(s) que apuntaban a ${name}.`);
  };

  const save = () => run(() => api.saveStage(project.id, "data_model", view.version, draft, summary.trim() || "Edición del modelo de datos"), "Modelo guardado.");

  return (
    <>
      <StageIntro title="Modelo de datos">
        Revisa la propuesta, edita tablas y columnas, y apruébala cuando el equipo esté de acuerdo. Las relaciones salen de las claves foráneas: una FK única es 1:1; si no, 1:N.
      </StageIntro>
      <Tabs<TabKey>
        tabs={[
          ["diagram", "Diagrama"],
          ["tables", `Tablas (${draft.tables.length})`],
          ["relations", "Relaciones"],
          ["sql", "SQL"],
          ["json", "JSON"],
        ]}
        value={tab}
        onChange={setTab}
      />

      {tab === "diagram" && (
        <div className="section">
          <p className="prose">{data.summary}</p>
          <div className="entity-cards">
            {draft.tables.map((t, i) => (
              <button
                key={t.name + i}
                className="entity-card"
                onClick={() => {
                  setSelected(i);
                  setTab("tables");
                }}
                title={readOnly ? `Ver ${t.name}` : `Editar ${t.name}`}
              >
                <span className="ec-head">
                  <strong>{t.name}</strong>
                  <span className="ec-edit">{readOnly ? "Ver" : "Editar"}</span>
                </span>
                {t.description && <span className="ec-desc">{t.description}</span>}
                <span className="ec-cols">
                  {t.columns.slice(0, 8).map((c) => (
                    <span key={c.name} className="ec-col">
                      <span className={c.primary_key ? "key pk" : c.foreign_key ? "key fk" : "key"}>{c.primary_key ? "PK" : c.foreign_key ? "FK" : ""}</span>
                      <span className="mono">{c.name}</span>
                      <span className="muted mono">{c.type}</span>
                    </span>
                  ))}
                  {t.columns.length > 8 && <span className="muted small">y {t.columns.length - 8} columnas más</span>}
                </span>
              </button>
            ))}
          </div>
          <details className="er-details">
            <summary>Ver diagrama entidad-relación</summary>
            {view.mermaid && <Mermaid code={view.mermaid} />}
          </details>
          {dirty && <p className="small muted">El diagrama muestra la versión guardada. Guarda tus cambios para actualizarlo.</p>}
          {data.notes.length > 0 && (
            <>
              <h4 style={{ marginTop: 18 }}>Reglas que se validan en el backend</h4>
              <ul>
                {data.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {tab === "tables" && (
        <div className="section">
          {editable && view.status === "approved" && (
            <div className="banner info row between">
              <span>Esta etapa está aprobada, por eso no se puede editar. Reábrela para cambiar tablas y columnas; después tendrás que aprobarla otra vez.</span>
              <button className="btn small" disabled={working} onClick={() => run(() => api.reopen(project.id, view.kind, view.version), "Etapa reabierta. Ya puedes editar.")}>
                Reabrir para editar
              </button>
            </div>
          )}
          <div className="entity-list" role="group" aria-label="Tablas">
            {draft.tables.map((t, i) => (
              <button key={i} className="option" aria-pressed={i === selected} onClick={() => setSelected(i)}>
                {t.name}
              </button>
            ))}
            {!readOnly && (
              <button
                className="btn ghost small"
                onClick={() => {
                  update((m) => m.tables.push(newTable(m.tables.length + 1)));
                  setSelected(draft.tables.length);
                }}
              >
                Agregar tabla
              </button>
            )}
          </div>

          {table && (
            <fieldset disabled={readOnly} style={{ border: 0, padding: 0, margin: 0 }}>
              <div className="row" style={{ alignItems: "flex-end", marginBottom: 12 }}>
                <div className="field" style={{ marginBottom: 0, width: 240 }}>
                  <label htmlFor="t-name">Nombre de la tabla</label>
                  <input id="t-name" type="text" className="mono" value={table.name} onChange={(e) => renameTable(e.target.value)} />
                </div>
                <div className="field grow" style={{ marginBottom: 0 }}>
                  <label htmlFor="t-desc">Descripción</label>
                  <input id="t-desc" type="text" value={table.description} onChange={(e) => updateTable((t) => (t.description = e.target.value))} />
                </div>
                {!readOnly && <ConfirmButton label="Eliminar tabla" confirmLabel="Eliminar" question={`¿Eliminar ${table.name}?`} className="btn danger" onConfirm={removeTable} />}
              </div>

              <div className="table-scroll">
                <table className="col-grid">
                  <thead>
                    <tr>
                      <th>Columna</th>
                      <th>Tipo</th>
                      <th title="Si está marcado, no puede quedar vacío">Obligatorio</th>
                      <th>Clave</th>
                      <th>Relación con</th>
                      <th>Descripción</th>
                      <th>
                        <span className="sr-only">Acciones</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {table.columns.map((c, ci) => (
                      <Fragment key={ci}>
                        <tr>
                          <td>
                            <input type="text" className="mono" aria-label="Nombre de columna" value={c.name} onChange={(e) => updateColumn(ci, { name: e.target.value })} style={{ minWidth: 130 }} />
                          </td>
                          <td>
                            <input type="text" className="mono" aria-label="Tipo" list="pg-types" value={c.type} onChange={(e) => updateColumn(ci, { type: e.target.value })} style={{ minWidth: 130 }} />
                          </td>
                          <td className="chk">
                            <input type="checkbox" aria-label="Obligatorio" checked={!c.nullable} disabled={c.primary_key} onChange={(e) => updateColumn(ci, { nullable: !e.target.checked })} />
                          </td>
                          <td>
                            <select
                              aria-label="Clave"
                              value={c.primary_key ? "pk" : c.unique ? "unique" : ""}
                              onChange={(e) => updateColumn(ci, { primary_key: e.target.value === "pk", unique: e.target.value === "unique", nullable: e.target.value === "pk" ? false : c.nullable })}
                            >
                              <option value="">—</option>
                              <option value="pk">Primaria</option>
                              <option value="unique">Única</option>
                            </select>
                          </td>
                          <td>
                            <select
                              aria-label="Tabla relacionada"
                              value={c.foreign_key?.table ?? ""}
                              onChange={(e) =>
                                updateColumn(ci, { foreign_key: e.target.value ? { table: e.target.value, column: "id", on_delete: c.foreign_key?.on_delete ?? "RESTRICT" } : null })
                              }
                            >
                              <option value="">—</option>
                              {draft.tables.map((t) => (
                                <option key={t.name} value={t.name}>
                                  {t.name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <input type="text" aria-label="Descripción" value={c.description} onChange={(e) => updateColumn(ci, { description: e.target.value })} style={{ minWidth: 180 }} />
                          </td>
                          <td className="row-acts">
                            <button className="btn ghost small" aria-expanded={openCol === ci} onClick={() => setOpenCol(openCol === ci ? null : ci)}>
                              {openCol === ci ? "Menos" : "Más"}
                            </button>
                            {!readOnly && (
                              <button className="btn ghost small" aria-label={`Quitar ${c.name}`} onClick={() => updateTable((t) => t.columns.splice(ci, 1))}>
                                Quitar
                              </button>
                            )}
                          </td>
                        </tr>
                        {openCol === ci && (
                          <tr className="col-more">
                            <td colSpan={7}>
                              <label>
                                Valor por defecto
                                <input type="text" className="mono" value={c.default ?? ""} onChange={(e) => updateColumn(ci, { default: e.target.value || null })} placeholder="ej.: now()" />
                              </label>
                              {c.foreign_key && (
                                <>
                                  <label>
                                    Columna de {c.foreign_key.table}
                                    <select value={c.foreign_key.column} onChange={(e) => updateColumn(ci, { foreign_key: { ...c.foreign_key!, column: e.target.value } })}>
                                      {(draft.tables.find((t) => t.name === c.foreign_key!.table)?.columns ?? []).map((pc) => (
                                        <option key={pc.name} value={pc.name}>
                                          {pc.name}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <label>
                                    Si se borra el registro de {c.foreign_key.table}
                                    <select value={c.foreign_key.on_delete} onChange={(e) => updateColumn(ci, { foreign_key: { ...c.foreign_key!, on_delete: e.target.value as FK["on_delete"] } })}>
                                      {ON_DELETE.map((o) => (
                                        <option key={o} value={o}>
                                          {ON_DELETE_LABEL[o]}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                </>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
              <datalist id="pg-types">
                {[...TYPES, ...enumNames].map((t) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
              {!readOnly && (
                <button className="btn ghost small" style={{ marginTop: 8 }} onClick={() => updateTable((t) => t.columns.push(newColumn()))}>
                  Agregar columna
                </button>
              )}

              <details className="advanced">
              <summary>Opciones avanzadas: índices, restricciones y tipos enumerados</summary>
              <div className="split" style={{ marginTop: 12, gap: 24 }}>
                <div>
                  <h4>Índices</h4>
                  {table.indexes.map((ix, i) => (
                    <div className="row" key={i} style={{ marginBottom: 6 }}>
                      <input type="text" className="mono" aria-label="Nombre del índice" value={ix.name} onChange={(e) => updateTable((t) => (t.indexes[i].name = e.target.value))} style={{ width: 200 }} />
                      <input
                        type="text"
                        className="mono grow"
                        aria-label="Columnas del índice"
                        value={ix.columns.join(", ")}
                        onChange={(e) => updateTable((t) => (t.indexes[i].columns = e.target.value.split(",").map((s) => s.trim()).filter(Boolean)))}
                      />
                      <label className="small">
                        <input type="checkbox" checked={ix.unique} onChange={(e) => updateTable((t) => (t.indexes[i].unique = e.target.checked))} /> único
                      </label>
                      {!readOnly && (
                        <button className="btn ghost small" onClick={() => updateTable((t) => t.indexes.splice(i, 1))}>
                          Quitar
                        </button>
                      )}
                    </div>
                  ))}
                  {!readOnly && (
                    <button className="btn ghost small" onClick={() => updateTable((t) => t.indexes.push({ name: `idx_${t.name}_`, columns: [], unique: false }))}>
                      Agregar índice
                    </button>
                  )}
                  <h4 style={{ marginTop: 16 }}>Únicos compuestos</h4>
                  {table.unique_constraints.map((uc, i) => (
                    <div className="row" key={i} style={{ marginBottom: 6 }}>
                      <input
                        type="text"
                        className="mono grow"
                        aria-label="Columnas únicas en conjunto"
                        value={uc.join(", ")}
                        onChange={(e) => updateTable((t) => (t.unique_constraints[i] = e.target.value.split(",").map((s) => s.trim()).filter(Boolean)))}
                      />
                      {!readOnly && (
                        <button className="btn ghost small" onClick={() => updateTable((t) => t.unique_constraints.splice(i, 1))}>
                          Quitar
                        </button>
                      )}
                    </div>
                  ))}
                  {!readOnly && (
                    <button className="btn ghost small" onClick={() => updateTable((t) => t.unique_constraints.push([]))}>
                      Agregar único
                    </button>
                  )}
                </div>
                <div>
                  <h4>Restricciones CHECK</h4>
                  {table.checks.map((ck, i) => (
                    <div className="row" key={i} style={{ marginBottom: 6 }}>
                      <input type="text" className="mono" aria-label="Nombre del check" value={ck.name} onChange={(e) => updateTable((t) => (t.checks[i].name = e.target.value))} style={{ width: 170 }} />
                      <input type="text" className="mono grow" aria-label="Expresión" value={ck.expression} onChange={(e) => updateTable((t) => (t.checks[i].expression = e.target.value))} />
                      {!readOnly && (
                        <button className="btn ghost small" onClick={() => updateTable((t) => t.checks.splice(i, 1))}>
                          Quitar
                        </button>
                      )}
                    </div>
                  ))}
                  {!readOnly && (
                    <button className="btn ghost small" onClick={() => updateTable((t) => t.checks.push({ name: `ck_${t.name}_`, expression: "" }))}>
                      Agregar check
                    </button>
                  )}
                </div>
              </div>

              <h4 style={{ marginTop: 20 }}>Tipos enumerados</h4>
              {draft.enums.map((en, i) => (
                <div className="row" key={i} style={{ marginBottom: 6 }}>
                  <input type="text" className="mono" aria-label="Nombre del enum" value={en.name} onChange={(e) => update((m) => (m.enums[i].name = e.target.value))} style={{ width: 200 }} />
                  <input
                    type="text"
                    className="mono grow"
                    aria-label="Valores del enum"
                    value={en.values.join(", ")}
                    onChange={(e) => update((m) => (m.enums[i].values = e.target.value.split(",").map((s) => s.trim()).filter(Boolean)))}
                  />
                  {!readOnly && (
                    <button className="btn ghost small" onClick={() => update((m) => m.enums.splice(i, 1))}>
                      Quitar
                    </button>
                  )}
                </div>
              ))}
              {!readOnly && (
                <button className="btn ghost small" onClick={() => update((m) => m.enums.push({ name: "nuevo_enum", values: [] }))}>
                  Agregar enum
                </button>
              )}
              </details>
            </fieldset>
          )}

          {!readOnly && (
            <div className="box row" style={{ marginTop: 20, position: "sticky", bottom: 12 }}>
              <input type="text" className="grow" aria-label="Resumen del cambio" placeholder="Resumen del cambio (queda en el historial)" value={summary} onChange={(e) => setSummary(e.target.value)} />
              <button className="btn" disabled={!dirty || working} onClick={save}>
                Guardar cambios
              </button>
              <button className="btn ghost" disabled={!dirty} onClick={() => setDraft(clone(data))}>
                Descartar
              </button>
            </div>
          )}
        </div>
      )}

      {tab === "relations" && (
        <div className="section table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Tabla padre</th>
                <th>Tabla hija</th>
                <th>Columna FK</th>
                <th>Cardinalidad</th>
                <th>Obligatoria</th>
                <th>Al borrar</th>
              </tr>
            </thead>
            <tbody>
              {(view.relationships ?? []).map((r, i) => (
                <tr key={i}>
                  <td className="mono">{r.parent}</td>
                  <td className="mono">{r.child}</td>
                  <td className="mono">{r.column}</td>
                  <td>{r.cardinality}</td>
                  <td>{r.optional ? "No" : "Sí"}</td>
                  <td className="mono">{r.on_delete}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(view.junctions ?? []).map((j) => (
            <p key={j.table} className="small" style={{ marginTop: 10 }}>
              <code>{j.table}</code> implementa la relación N:M entre <code>{j.left}</code> y <code>{j.right}</code>.
            </p>
          ))}
        </div>
      )}

      {tab === "sql" && (
        <div className="section">
          <div className="row between" style={{ marginBottom: 8 }}>
            <p className="section-note" style={{ margin: 0 }}>
              DDL generado de la versión guardada. Es el mismo que va en el documento final.
            </p>
            <button className="btn secondary small" onClick={() => navigator.clipboard?.writeText(view.ddl ?? "").then(() => toast("SQL copiado."))}>
              Copiar SQL
            </button>
          </div>
          <pre>{view.ddl}</pre>
        </div>
      )}

      {tab === "json" && (
        <div className="section">
          <JsonEditor ctx={ctx} value={data} onSave={(d) => run(() => api.saveStage(project.id, "data_model", view.version, d, "Edición avanzada (JSON)"), "Modelo guardado.")} />
        </div>
      )}

      <ChangeRequest ctx={ctx} placeholder="Ej.: agrega una tabla de pagos con monto, estado y fecha, ligada a reservations" />
    </>
  );
}
