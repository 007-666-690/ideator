import { useState } from "react";
import { api } from "../../api";
import type { Finding, Issue } from "../../types";
import { timeAgo } from "../../util";
import type { StageCtx } from "../Project";
import { StageIntro } from "./common";

const SEV: Record<Finding["severity"], string> = { critica: "Crítica", importante: "Importante", menor: "Menor" };
const STATUS: Record<Finding["status"], string> = { open: "Abierto", resolved: "Corregido", accepted: "Aceptado sin cambios" };

function FindingCard({ f, ctx }: { f: Finding; ctx: StageCtx }) {
  const { project, view, run, editable, working } = ctx;
  const [note, setNote] = useState("");
  const [asking, setAsking] = useState(false);
  const canWork = editable && view.status !== "approved" && view.status !== "locked";
  return (
    <div className={`finding ${f.severity} ${f.status !== "open" ? "closed" : ""}`}>
      <div className="row between">
        <span>
          <span className={`sev ${f.severity}`}>{SEV[f.severity]}</span>{" "}
          <span className="small muted">
            {f.id}, {f.source === "auto" ? "detectado automáticamente" : "detectado por la IA"}, área {f.area}
          </span>
        </span>
        <span className="small">{STATUS[f.status]}</span>
      </div>
      <p style={{ margin: "6px 0" }}>{f.description}</p>
      <p className="small muted" style={{ marginBottom: 6 }}>
        Sugerencia: {f.suggestion}
      </p>
      {f.note && (
        <p className="small">
          Nota de {f.resolved_by}: {f.note}
        </p>
      )}
      {canWork && f.source === "ia" && f.status === "open" && !asking && (
        <div className="row">
          <button className="btn secondary small" disabled={working} onClick={() => run(() => api.resolveFinding(project.id, f.id, view.version, "fixed", ""), "Hallazgo marcado como corregido.")}>
            Ya lo corregimos
          </button>
          <button className="btn ghost small" onClick={() => setAsking(true)}>
            Aceptar sin cambios
          </button>
        </div>
      )}
      {asking && (
        <div className="stack">
          <label className="small" htmlFor={`note-${f.id}`}>
            ¿Por qué se acepta sin cambios? Queda registrado.
          </label>
          <textarea id={`note-${f.id}`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="row">
            <button
              className="btn small"
              disabled={note.trim().length < 3 || working}
              onClick={async () => {
                if (await run(() => api.resolveFinding(project.id, f.id, view.version, "accepted", note.trim()), "Hallazgo aceptado.")) setAsking(false);
              }}
            >
              Aceptar hallazgo
            </button>
            <button className="btn ghost small" onClick={() => setAsking(false)}>
              Cancelar
            </button>
          </div>
        </div>
      )}
      {canWork && f.source === "ia" && f.status !== "open" && (
        <button className="btn ghost small" disabled={working} onClick={() => run(() => api.resolveFinding(project.id, f.id, view.version, "open", ""), "Hallazgo reabierto.")}>
          Reabrir
        </button>
      )}
    </div>
  );
}

export default function ReviewStage({ ctx }: { ctx: StageCtx }) {
  const { project, view, run, editable, working } = ctx;
  const content = view.content;
  const findings: Finding[] = content.findings ?? [];
  const warnings: (Issue & { stage: string })[] = content.warnings ?? [];
  const pendingAssumptions = (view.assumptions ?? []).filter((a) => !a.accepted);
  const canWork = editable && view.status !== "approved" && view.status !== "locked";
  const outdated = view.issues.some((i) => i.code === "review.outdated" || i.code === "review.not_run");

  const acceptAll = async () => {
    const stages = await api.stages(project.id);
    const product = stages.find((s) => s.kind === "product")!;
    await run(async () => {
      await api.acceptAssumptions(project.id, product.version, null);
      return api.stage(project.id, "review");
    }, "Supuestos aceptados.");
  };

  return (
    <>
      <StageIntro title="Revisión final">
        Antes de generar los documentos, Plano revisa la consistencia de todo el proyecto: problemas automáticos y contradicciones entre etapas detectadas por la IA. Los hallazgos críticos impiden generar.
      </StageIntro>

      <div className="box section">
        <div className="row between">
          <div>
            <strong>{content.ran_at ? `Última revisión ${timeAgo(content.ran_at)}` : "Aún no se ejecuta la revisión"}</strong>
            {content.summary && <p className="small muted" style={{ margin: "4px 0 0" }}>{content.summary}</p>}
            {content.ran_at && outdated && <p className="small" style={{ color: "var(--stale)", margin: "4px 0 0" }}>Hubo cambios después de esa revisión.</p>}
          </div>
          {canWork && (
            <button className={`btn ${content.ran_at && !outdated ? "secondary" : ""}`} disabled={working} onClick={() => run(() => api.runReview(project.id, view.version), "Revisión completa.")}>
              {content.ran_at ? "Volver a revisar" : "Ejecutar revisión"}
            </button>
          )}
        </div>
      </div>

      {pendingAssumptions.length > 0 && (
        <section className="section">
          <h3>Supuestos por aceptar ({pendingAssumptions.length})</h3>
          {pendingAssumptions.map((a) => (
            <div key={a.id} className="assumption">
              <span>
                <span className="mono small">{a.id}</span> {a.description}
              </span>
            </div>
          ))}
          {editable && (
            <button className="btn secondary" style={{ marginTop: 10 }} disabled={working} onClick={acceptAll}>
              Aceptar todos los supuestos
            </button>
          )}
          <p className="small muted" style={{ marginTop: 8 }}>
            Si alguno no es correcto, corrígelo en la definición del producto (reábrela) y vuelve a revisar.
          </p>
        </section>
      )}

      {findings.length > 0 && (
        <section className="section">
          <h3>Hallazgos ({findings.filter((f) => f.status === "open").length} abiertos)</h3>
          {(["critica", "importante", "menor"] as const).flatMap((sev) => findings.filter((f) => f.severity === sev)).map((f) => (
            <FindingCard key={f.id} f={f} ctx={ctx} />
          ))}
        </section>
      )}
      {content.ran_at && findings.length === 0 && <p className="muted">No hay hallazgos: la definición es consistente.</p>}

      {warnings.length > 0 && (
        <details className="section">
          <summary>
            <strong>Advertencias menores</strong> <span className="small muted">({warnings.length}, no bloquean)</span>
          </summary>
          <ul className="issues" style={{ marginTop: 10 }}>
            {warnings.map((w, i) => (
              <li key={i} className="warning">
                <span className="dot" aria-hidden="true" />
                <span>{w.message}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
