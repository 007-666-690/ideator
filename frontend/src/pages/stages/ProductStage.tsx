import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type { Brief, Question } from "../../types";
import { DELEGATED, timeAgo } from "../../util";
import type { StageCtx } from "../Project";
import { JsonEditor, List, StageIntro } from "./common";

const AFFECTS: Record<string, string> = {
  datos: "Modelo de datos",
  backend: "API",
  interfaz: "Pantallas",
  arquitectura: "Arquitectura",
  alcance: "Alcance",
  negocio: "Reglas de negocio",
  seguridad: "Seguridad",
};

const EDGE: Record<string, string> = {
  falta_informacion: "Falta información",
  accion_fallida: "Acción que no se completa",
  sin_permisos: "Sin permisos",
  recurso_inexistente: "Recurso inexistente",
  datos_invalidos: "Datos inválidos",
  dependencia_caida: "Dependencia caída",
  concurrencia: "Concurrencia",
  otro: "Otro",
};

interface Draft {
  choice: string | null;
  text: string;
  delegate: boolean;
}

function answerOf(d: Draft | undefined): string {
  if (!d) return "";
  if (d.delegate) return DELEGATED;
  const text = d.text.trim();
  if (d.choice && text) return `${d.choice}. ${text}`;
  return d.choice ?? text;
}

export default function ProductStage({ ctx }: { ctx: StageCtx }) {
  const { project, view, editable, run, working, setDirty } = ctx;
  const brief: Brief = view.content.brief;
  const started: boolean = view.content.started;
  const questions = view.questions ?? [];
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [message, setMessage] = useState("");
  const [tab, setTab] = useState<"read" | "json">("read");

  useEffect(() => {
    setDrafts({});
    setMessage("");
  }, [view.version]);

  const open = useMemo(() => questions.filter((q) => q.status === "open").sort((a, b) => Number(b.blocking) - Number(a.blocking)), [questions]);
  const pending = questions.filter((q) => q.status === "answered");
  const closed = questions.filter((q) => q.status === "resolved" || q.status === "dismissed");
  const ready = open.filter((q) => answerOf(drafts[q.id]).length > 0);
  const canWork = editable && view.status !== "approved" && view.status !== "locked";

  useEffect(() => {
    setDirty(ready.length > 0 || message.trim().length > 0);
  }, [ready.length, message, setDirty]);

  const setDraft = (q: Question, patch: Partial<Draft>) =>
    setDrafts((d) => {
      const base: Draft = d[q.id] ?? { choice: null, text: "", delegate: false };
      return { ...d, [q.id]: { ...base, ...patch } };
    });

  if (!started) {
    return (
      <>
        <StageIntro title="Definición del producto">
          Plano conversa con el equipo para entender el problema, los usuarios y el alcance del MVP. Cuando falte una decisión que cambia la solución, la marca como bloqueante y no avanza hasta resolverla.
        </StageIntro>
        <div className="box">
          <h3>La idea inicial</h3>
          <p className="prose" style={{ whiteSpace: "pre-wrap" }}>
            {project.idea}
          </p>
          {editable ? (
            <button className="btn" disabled={working} onClick={() => run(() => api.startProduct(project.id, view.version), "Primera ronda de preguntas lista.")}>
              Comenzar la definición
            </button>
          ) : (
            <p className="small muted">Un editor del equipo debe comenzar la definición.</p>
          )}
        </div>
      </>
    );
  }

  const submit = () =>
    run(
      () =>
        api.productTurn(
          project.id,
          view.version,
          ready.map((q) => ({ question_id: q.id, answer: answerOf(drafts[q.id]) })),
          message.trim() || null,
        ),
      "Respuestas procesadas.",
    );

  return (
    <>
      <StageIntro title="Definición del producto">
        Ronda {view.content.round}. Responde las preguntas; las bloqueantes deben resolverse antes de aprobar la etapa. Si prefieres que Plano decida, usa «Que decida Plano» y quedará registrado como decisión delegada.
      </StageIntro>

      {view.content.contradictions?.length > 0 && (
        <div className="banner warn">
          <strong>Contradicciones detectadas:</strong>
          <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
            {view.content.contradictions.map((c: string, i: number) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {pending.length > 0 && (
        <div className="banner info">
          Hay {pending.length} respuesta(s) guardada(s) que la IA aún no procesa.
          {canWork && (
            <button className="btn secondary small" disabled={working} onClick={() => run(() => api.productTurn(project.id, view.version, [], null), "Respuestas procesadas.")}>
              Procesar ahora
            </button>
          )}
        </div>
      )}

      <section className="section">
        <h3>{open.length ? `Preguntas abiertas (${open.length})` : "Preguntas abiertas"}</h3>
        {open.length === 0 && <p className="muted">No hay preguntas pendientes. Revisa la definición y, si está completa, apruébala.</p>}
        {open.map((q) => {
          const d = drafts[q.id];
          return (
            <article key={q.id} className={`question ${q.blocking ? "blocking" : ""}`} aria-label={`Pregunta ${q.code}`}>
              <div className="qhead">
                <span className="code">{q.code}</span>
                {q.blocking && <span className="mark-blocking">Bloqueante</span>}
                <span className="tags">
                  {q.affects.map((a) => (
                    <span key={a} className="tag">
                      {AFFECTS[a] ?? a}
                    </span>
                  ))}
                </span>
              </div>
              <div className="text">{q.text}</div>
              {q.rationale && <p className="why">{q.rationale}</p>}
              {canWork && (
                <>
                  {q.options.length > 0 && (
                    <div className="options" role="group" aria-label="Opciones sugeridas">
                      {q.options.map((o) => (
                        <button
                          key={o}
                          type="button"
                          className="option"
                          aria-pressed={d?.choice === o && !d.delegate}
                          onClick={() => setDraft(q, { choice: d?.choice === o ? null : o, delegate: false })}
                        >
                          {o}
                        </button>
                      ))}
                    </div>
                  )}
                  <label className="sr-only" htmlFor={`ans-${q.id}`}>
                    Respuesta a {q.code}
                  </label>
                  <textarea
                    id={`ans-${q.id}`}
                    rows={2}
                    value={d?.text ?? ""}
                    disabled={d?.delegate}
                    onChange={(e) => setDraft(q, { text: e.target.value, delegate: false })}
                    placeholder={q.options.length ? "Precisa o explica tu elección (opcional)" : "Tu respuesta"}
                  />
                  <div className="row" style={{ marginTop: 8 }}>
                    <button type="button" className="option" aria-pressed={!!d?.delegate} onClick={() => setDraft(q, { delegate: !d?.delegate })}>
                      Que decida Plano
                    </button>
                    {!q.blocking && (
                      <button type="button" className="btn ghost small" disabled={working} onClick={() => run(() => api.dismissQuestion(project.id, q.id, "No aplica para el MVP"), "Pregunta descartada.")}>
                        Descartar
                      </button>
                    )}
                  </div>
                </>
              )}
            </article>
          );
        })}
        {canWork && (
          <div className="box" style={{ marginTop: 6 }}>
            <div className="field">
              <label htmlFor="msg">Algo más que Plano deba saber (opcional)</label>
              <textarea id="msg" rows={2} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Ej.: cambiamos de idea, el MVP no incluye pagos" />
            </div>
            <button className="btn" disabled={working || (ready.length === 0 && message.trim().length === 0)} onClick={submit}>
              {ready.length ? `Enviar ${ready.length} respuesta${ready.length === 1 ? "" : "s"}` : "Enviar mensaje"}
            </button>
          </div>
        )}
      </section>

      {view.messages && view.messages.length > 0 && (
        <details className="section">
          <summary>
            <strong>Conversación</strong> <span className="muted small">({view.messages.length} mensajes)</span>
          </summary>
          <div className="chat">
            {view.messages.map((m) => (
              <div key={m.id} className={`msg ${m.role}`}>
                <div className="who">
                  {m.role === "assistant" ? "Plano" : m.author?.name ?? "Equipo"}, {timeAgo(m.created_at)}
                </div>
                <div className="body">{m.content}</div>
              </div>
            ))}
          </div>
        </details>
      )}

      <section className="section">
        <div className="row between">
          <h3 style={{ border: 0, margin: 0 }}>Definición actual</h3>
          <div className="row">
            <button className={`btn small ${tab === "read" ? "" : "secondary"}`} onClick={() => setTab("read")}>
              Lectura
            </button>
            <button className={`btn small ${tab === "json" ? "" : "secondary"}`} onClick={() => setTab("json")}>
              Editar
            </button>
          </div>
        </div>
        <hr style={{ margin: "10px 0 18px" }} />
        {tab === "read" ? (
          <BriefView brief={brief} ctx={ctx} />
        ) : (
          <JsonEditor
            ctx={ctx}
            value={brief}
            help="Edita la definición completa. Mantén los ids (U1, RF-01, CB-01…): las etapas siguientes los usan para conectar requisitos, endpoints y pantallas."
            onSave={(data) => run(() => api.saveBrief(project.id, view.version, data), "Definición guardada.")}
          />
        )}
      </section>

      {closed.length > 0 && (
        <details className="section">
          <summary>
            <strong>Decisiones respondidas</strong> <span className="muted small">({closed.length})</span>
          </summary>
          <div style={{ marginTop: 10 }}>
            {closed.map((q) => (
              <div key={q.id} className="req">
                <span className="rid">{q.code}</span>
                <strong>{q.text}</strong>
                <div className="answered">
                  {q.status === "dismissed" ? "Descartada" : "Respuesta"}: <strong>{q.answer?.startsWith("[DELEGADO]") ? "Delegada a Plano" : q.answer}</strong>
                  {q.answered_by && <span className="muted"> ({q.answered_by.name}, {timeAgo(q.answered_at)})</span>}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
    </>
  );
}

function BriefView({ brief, ctx }: { brief: Brief; ctx: StageCtx }) {
  const { project, view, run, working, editable } = ctx;
  const pendingAssumptions = brief.assumptions.filter((a) => !a.accepted);
  return (
    <div className="prose" style={{ maxWidth: "none" }}>
      <dl className="kv section">
        <dt>Producto</dt>
        <dd>{brief.product_name || <span className="empty">Pendiente</span>}</dd>
        <dt>En una frase</dt>
        <dd>{brief.one_liner || <span className="empty">Pendiente</span>}</dd>
        <dt>Problema</dt>
        <dd>{brief.problem || <span className="empty">Pendiente</span>}</dd>
        <dt>Contexto</dt>
        <dd>{brief.context || <span className="empty">Pendiente</span>}</dd>
        <dt>Situación actual</dt>
        <dd>{brief.current_situation || <span className="empty">Pendiente</span>}</dd>
        <dt>Mejora esperada</dt>
        <dd>{brief.desired_improvement || <span className="empty">Pendiente</span>}</dd>
      </dl>

      <div className="section">
        <h4>Usuarios y permisos</h4>
        {brief.user_types.length ? (
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Id</th>
                  <th>Tipo</th>
                  <th>Objetivos</th>
                  <th>Puede</th>
                  <th>No puede</th>
                </tr>
              </thead>
              <tbody>
                {brief.user_types.map((u) => (
                  <tr key={u.id}>
                    <td className="mono">{u.id}</td>
                    <td>
                      <strong>{u.name}</strong>
                      <div className="small muted">{u.description}</div>
                    </td>
                    <td>{u.goals.join("; ")}</td>
                    <td>{u.permissions.join("; ")}</td>
                    <td>{u.restrictions.join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">Pendiente</p>
        )}
      </div>

      <div className="section">
        <h4>Resultados esperados</h4>
        {brief.expected_outcomes.length ? (
          <ul>
            {brief.expected_outcomes.map((o) => (
              <li key={o.id}>
                <strong>{o.description}</strong> — se mide con {o.metric.toLowerCase()}; meta: {o.target}
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">Pendiente</p>
        )}
      </div>

      <div className="section split" style={{ gap: 24 }}>
        <div>
          <h4>Dentro del MVP</h4>
          <List items={brief.mvp_in_scope.map((s) => `${s.id} ${s.description}`)} />
        </div>
        <div>
          <h4>Fuera del MVP</h4>
          <List items={brief.mvp_out_of_scope.map((s) => `${s.id} ${s.description}${s.reason ? ` (${s.reason})` : ""}`)} />
        </div>
      </div>

      <div className="section">
        <h4>Recorrido principal{brief.main_journey.name ? `: ${brief.main_journey.name}` : ""}</h4>
        {brief.main_journey.steps.length ? (
          <>
            <ol className="steps">
              {brief.main_journey.steps.map((s) => (
                <li key={s.number}>
                  <strong>{s.actor}</strong> {s.action}. <span className="muted">{s.system_response}.</span>
                </li>
              ))}
            </ol>
            <p className="small">Resultado: {brief.main_journey.success_result}</p>
          </>
        ) : (
          <p className="empty">Pendiente</p>
        )}
      </div>

      <div className="section">
        <h4>Requisitos funcionales</h4>
        {brief.functional_requirements.length === 0 && <p className="empty">Pendiente</p>}
        {brief.functional_requirements.map((r) => (
          <div key={r.id} className="req">
            <span className="rid">{r.id}</span>
            <strong>{r.title}</strong> <span className="tag">{r.priority === "must" ? "Obligatorio" : r.priority === "should" ? "Deseable" : "Opcional"}</span>
            <div className="small muted">
              {r.description} Usuarios: {r.user_types.join(", ")}.
            </div>
            <ul>
              {r.acceptance_criteria.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="section">
        <h4>Reglas de negocio</h4>
        <List items={brief.business_rules.map((r) => `${r.id} ${r.description}`)} />
      </div>

      <div className="section">
        <h4>Casos borde</h4>
        {brief.edge_cases.length ? (
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Id</th>
                  <th>Categoría</th>
                  <th>Escenario</th>
                  <th>Comportamiento esperado</th>
                </tr>
              </thead>
              <tbody>
                {brief.edge_cases.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{e.id}</td>
                    <td>{EDGE[e.category] ?? e.category}</td>
                    <td>{e.scenario}</td>
                    <td>{e.expected_behavior}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">Pendiente</p>
        )}
      </div>

      <div className="section split" style={{ gap: 24 }}>
        <div>
          <h4>Seguridad</h4>
          <List items={brief.security_requirements} />
          <h4 style={{ marginTop: 16 }}>No funcionales</h4>
          <List items={brief.non_functional_requirements} empty="Ninguno" />
        </div>
        <div>
          <h4>Integraciones externas</h4>
          <List items={brief.integrations.map((i) => `${i.name}: ${i.purpose}. Si falla: ${i.failure_behavior}`)} empty="Ninguna" />
          <h4 style={{ marginTop: 16 }}>Restricciones técnicas</h4>
          <List items={brief.technical_constraints} empty="Ninguna" />
        </div>
      </div>

      <div className="section">
        <div className="row between">
          <h4 style={{ margin: 0 }}>Supuestos</h4>
          {editable && pendingAssumptions.length > 1 && (
            <button className="btn secondary small" disabled={working} onClick={() => run(() => api.acceptAssumptions(project.id, view.version, null), "Supuestos aceptados.")}>
              Aceptar todos
            </button>
          )}
        </div>
        <p className="section-note" style={{ marginTop: 6 }}>
          Detalles menores que la IA propuso con un valor estándar. Deben aceptarse (o corregirse) antes de generar los documentos.
        </p>
        {brief.assumptions.length === 0 && <p className="empty">Ninguno</p>}
        {brief.assumptions.map((a) => (
          <div key={a.id} className="assumption">
            <span>
              <span className="rid mono">{a.id}</span> {a.description}
            </span>
            {a.accepted ? (
              <span className="small" style={{ color: "var(--stamp)", fontWeight: 600 }}>
                Aceptado
              </span>
            ) : editable ? (
              <button className="btn secondary small" disabled={working} onClick={() => run(() => api.acceptAssumptions(project.id, view.version, [a.id]), `${a.id} aceptado.`)}>
                Aceptar
              </button>
            ) : (
              <span className="small muted">Pendiente</span>
            )}
          </div>
        ))}
      </div>

      <div className="section">
        <h4>Decisiones registradas</h4>
        {brief.decisions.length ? (
          <table className="data">
            <tbody>
              {brief.decisions.map((d) => (
                <tr key={d.id}>
                  <td className="mono" style={{ width: 60 }}>
                    {d.id}
                  </td>
                  <td style={{ width: "30%" }}>{d.topic}</td>
                  <td>{d.decision}</td>
                  <td className="small muted" style={{ width: 110 }}>
                    {d.source === "usuario" ? "Equipo" : "Delegada"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="empty">Todavía no hay decisiones</p>
        )}
      </div>

      {brief.glossary.length > 0 && (
        <div className="section">
          <h4>Glosario</h4>
          <dl className="kv">
            {brief.glossary.map((g) => (
              <div key={g.term} style={{ display: "contents" }}>
                <dt>{g.term}</dt>
                <dd>{g.definition}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
