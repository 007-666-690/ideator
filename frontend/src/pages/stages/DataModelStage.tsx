import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { ConfirmButton, Mermaid, Tabs, useToast } from "../../components/ui";
import type { Column, DataModel, FK, Table } from "../../types";
import { clone } from "../../util";
import type { StageCtx } from "../Project";
import { ChangeRequest, GenerateFirst, JsonEditor, StageIntro } from "./common";

const TYPES = ["uuid", "text", "varchar(120)", "varchar(254)", "integer", "bigint", "numeric(12,2)", "boolean", "date", "time", "timestamptz", "jsonb"];
const ON_DELETE: FK["on_delete"][] = ["CASCADE", "RESTRICT", "SET NULL", "NO ACTION"];

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
          {view.mermaid && <Mermaid code={view.mermaid} />}
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
                      <th>Nulo</th>
                      <th>PK</th>
                      <th>Único</th>
                      <th>Por defecto</th>
                      <th>FK a tabla</th>
                      <th>Columna</th>
                      <th>Al borrar</th>
                      <th>Descripción</th>
                      <th>
                        <span className="sr-only">Acciones</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {table.columns.map((c, ci) => (
                      <tr key={ci}>
                        <td>
                          <input type="text" className="mono" aria-label="Nombre de columna" value={c.name} onChange={(e) => updateColumn(ci, { name: e.target.value })} style={{ minWidth: 130 }} />
                        </td>
                        <td>
                          <input type="text" className="mono" aria-label="Tipo" list="pg-types" value={c.type} onChange={(e) => updateColumn(ci, { type: e.target.value })} style={{ minWidth: 150 }} />
                        </td>
                        <td className="chk">
                          <input type="checkbox" aria-label="Admite nulos" checked={c.nullable} onChange={(e) => updateColumn(ci, { nullable: e.target.checked })} />
                        </td>
                        <td className="chk">
                          <input type="checkbox" aria-label="Clave primaria" checked={c.primary_key} onChange={(e) => updateColumn(ci, { primary_key: e.target.checked, nullable: e.target.checked ? false : c.nullable })} />
                        </td>
                        <td className="chk">
                          <input type="checkbox" aria-label="Único" checked={c.unique} onChange={(e) => updateColumn(ci, { unique: e.target.checked })} />
                        </td>
                        <td>
                          <input type="text" className="mono" aria-label="Valor por defecto" value={c.default ?? ""} onChange={(e) => updateColumn(ci, { default: e.target.value || null })} style={{ minWidth: 90 }} />
                        </td>
                        <td>
                          <select
                            aria-label="Tabla referenciada"
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
                          {c.foreign_key && (
                            <select
                              aria-label="Columna referenciada"
                              value={c.foreign_key.column}
                              onChange={(e) => updateColumn(ci, { foreign_key: { ...c.foreign_key!, column: e.target.value } })}
                            >
                              {(draft.tables.find((t) => t.name === c.foreign_key!.table)?.columns ?? []).map((pc) => (
                                <option key={pc.name} value={pc.name}>
                                  {pc.name}
                                </option>
                              ))}
                            </select>
                          )}
                        </td>
                        <td>
                          {c.foreign_key && (
                            <select
                              aria-label="Acción al borrar"
                              value={c.foreign_key.on_delete}
                              onChange={(e) => updateColumn(ci, { foreign_key: { ...c.foreign_key!, on_delete: e.target.value as FK["on_delete"] } })}
                            >
                              {ON_DELETE.map((o) => (
                                <option key={o}>{o}</option>
                              ))}
                            </select>
                          )}
                        </td>
                        <td>
                          <input type="text" aria-label="Descripción" value={c.description} onChange={(e) => updateColumn(ci, { description: e.target.value })} style={{ minWidth: 160 }} />
                        </td>
                        <td>
                          {!readOnly && (
                            <button className="btn ghost small" aria-label={`Quitar ${c.name}`} onClick={() => updateTable((t) => t.columns.splice(ci, 1))}>
                              Quitar
                            </button>
                          )}
                        </td>
                      </tr>
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

              <div className="split" style={{ marginTop: 20, gap: 24 }}>
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
