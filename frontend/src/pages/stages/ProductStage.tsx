import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type { Brief, Question } from "../../types";
import { DELEGATED } from "../../util";
import type { StageCtx } from "../Project";
import { JsonEditor, List, StageIntro } from "./common";


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

type TimelineItem =
  | { type: "message"; key: string; at: string; role: string; who: string; text: string }
  | { type: "qa"; key: string; at: string; q: Question };

/** Mensajes y preguntas respondidas, en el orden en que ocurrieron. */
function timeline(messages: NonNullable<StageCtx["view"]["messages"]>, closed: Question[]): TimelineItem[] {
  const items: TimelineItem[] = [
    ...messages.map((m) => ({ type: "message" as const, key: m.id, at: m.created_at, role: m.role, who: m.author?.name ?? "Equipo", text: m.content })),
    ...closed.map((q) => ({ type: "qa" as const, key: q.id, at: q.answered_at ?? q.created_at, q })),
  ];
  return items.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
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

  const submit = (extra?: { id: string; answer: string }) => {
    const answers = ready.map((q) => ({ question_id: q.id, answer: answerOf(drafts[q.id]) }));
    if (extra && !answers.some((a) => a.question_id === extra.id)) answers.push({ question_id: extra.id, answer: extra.answer });
    // Si el texto ya se usó como respuesta a una pregunta, no se manda además como mensaje suelto.
    const note = extra ? null : message.trim() || null;
    return run(() => api.productTurn(project.id, view.version, answers, note), "Listo, Plano actualizó la definición.");
  };

  // La pregunta actual del chat: primero las bloqueantes, una a la vez.
  const current = open.find((q) => !answerOf(drafts[q.id]));
  const answeredNow = open.filter((q) => answerOf(drafts[q.id]));
  const answerCurrent = (q: Question, answer: string) => {
    const next = { ...drafts, [q.id]: { choice: answer, text: "", delegate: answer === DELEGATED } };
    setDrafts(next);
    setMessage("");
    // Al responder la última pregunta de la ronda, se envía sola: nada de botones extra.
    if (open.every((x) => x.id === q.id || answerOf(next[x.id]))) void submit({ id: q.id, answer });
  };

  return (
    <>
      <StageIntro title="Definición del producto">
        Plano te hace preguntas cortas, como en un chat. Responde con un clic o escribiendo; si no sabes, toca «Que decida Plano». Cuando no queden preguntas, aprueba y la IA arma el resto sola.
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

      <section className="chatbox" aria-label="Conversación con Plano">
        <div className="bubble user">
          <span className="who">Idea</span>
          {project.idea}
        </div>
        {timeline(view.messages ?? [], closed).map((item) =>
          item.type === "message" ? (
            <div key={item.key} className={`bubble ${item.role}`}>
              <span className="who">{item.role === "assistant" ? "Plano" : item.who}</span>
              {item.text}
            </div>
          ) : (
            <div key={item.key} className="pair">
              <div className="bubble assistant">
                <span className="who">Plano · {item.q.code}</span>
                {item.q.text}
              </div>
              <div className="bubble user">
                <span className="who">{item.q.answered_by?.name ?? "Equipo"}</span>
                {item.q.status === "dismissed" ? "No aplica" : item.q.answer?.startsWith("[DELEGADO]") ? "Que decida Plano" : item.q.answer}
              </div>
            </div>
          ),
        )}
        {answeredNow.map((q) => (
          <div key={q.id} className="pair">
            <div className="bubble assistant">
              <span className="who">Plano · {q.code}</span>
              {q.text}
            </div>
            <div className="bubble user pending">
              <span className="who">Tú</span>
              {drafts[q.id]?.delegate ? "Que decida Plano" : answerOf(drafts[q.id])}
              {canWork && !working && (
                <button className="linklike" onClick={() => setDrafts((d) => ({ ...d, [q.id]: { choice: null, text: "", delegate: false } }))}>
                  Cambiar
                </button>
              )}
            </div>
          </div>
        ))}
        {pending.length > 0 && !working && (
          <div className="bubble assistant">
            Tengo {pending.length} respuesta(s) guardada(s) sin procesar.
            {canWork && (
              <button className="btn small" style={{ marginLeft: 8 }} onClick={() => run(() => api.productTurn(project.id, view.version, [], null), "Respuestas procesadas.")}>
                Procesar ahora
              </button>
            )}
          </div>
        )}
        {working && (
          <div className="bubble assistant typing" aria-live="polite">
            <span className="dots" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            Plano está pensando…
          </div>
        )}
        {!working && current && (
          <div className={`bubble assistant ask ${current.blocking ? "blocking" : ""}`}>
            <span className="who">
              Plano · {current.code} · pregunta {open.indexOf(current) + 1} de {open.length}
              {current.blocking && <span className="mark-blocking">Necesaria</span>}
            </span>
            <strong>{current.text}</strong>
            {current.rationale && <p className="why">{current.rationale}</p>}
            {canWork && (
              <div className="options" role="group" aria-label="Respuestas rápidas">
                {current.options.map((o) => (
                  <button key={o} type="button" className="option" onClick={() => answerCurrent(current, o)}>
                    {o}
                  </button>
                ))}
                <button type="button" className="option ghost" onClick={() => answerCurrent(current, DELEGATED)}>
                  Que decida Plano
                </button>
                {!current.blocking && (
                  <button type="button" className="option ghost" onClick={() => run(() => api.dismissQuestion(project.id, current.id, "No aplica para el MVP"), "Pregunta descartada.")}>
                    No aplica
                  </button>
                )}
              </div>
            )}
          </div>
        )}
        {!working && !current && open.length === 0 && pending.length === 0 && (
          <div className="bubble assistant done">
            <span className="who">Plano</span>
            {view.can_approve
              ? "¡Tengo todo lo necesario! Revisa la definición abajo y apruébala: después preparo solo el modelo de datos, la API, las pantallas y la arquitectura."
              : "No me quedan preguntas, pero falta completar algo de la definición: revisa los problemas marcados a la derecha o escríbeme qué cambiar."}
          </div>
        )}
        {canWork && (
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              const text = message.trim();
              if (!text) return;
              if (current) answerCurrent(current, text);
              else void submit();
            }}
          >
            <label className="sr-only" htmlFor="composer">
              Escribe tu respuesta
            </label>
            <input
              id="composer"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={current ? "Escribe tu respuesta…" : "Escribe un cambio o algo que Plano deba saber…"}
              disabled={working}
              autoComplete="off"
            />
            <button className="btn" disabled={working || !message.trim()}>
              Enviar
            </button>
            {ready.length > 0 && current && (
              <button type="button" className="btn secondary" disabled={working} onClick={() => submit()}>
                Enviar {ready.length} y seguir
              </button>
            )}
          </form>
        )}
      </section>

      <details className="section brief-details" open={open.length === 0 && pending.length === 0}>
        <summary>
          <strong>Ver la definición completa</strong> <span className="muted small">(lo que Plano entendió hasta ahora)</span>
        </summary>
        <div className="row between" style={{ marginTop: 12 }}>
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
      </details>

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
