import { useEffect, useState, type ReactNode } from "react";
import { api } from "../../api";
import type { StageKind } from "../../types";
import type { StageCtx } from "../Project";

export function StageIntro({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="stage-head">
      <div>
        <h2>{title}</h2>
        {children && <p className="meta prose">{children}</p>}
      </div>
    </div>
  );
}

export function GenerateFirst({ ctx, what, button }: { ctx: StageCtx; what: string; button: string }) {
  const [instructions, setInstructions] = useState("");
  const { view, editable, run, project, working } = ctx;
  if (view.status === "locked") return <p className="muted">Esta etapa se habilita cuando se aprueba la anterior.</p>;
  return (
    <div className="box">
      <h3>Aún no hay {what}</h3>
      <p className="muted">Ideator lo propone a partir de lo aprobado en las etapas anteriores. Después podrás revisarlo, editarlo y pedir cambios.</p>
      {editable ? (
        <>
          <div className="field">
            <label htmlFor="gen-instr">Indicaciones para la IA (opcional)</label>
            <textarea id="gen-instr" rows={3} value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Ej.: usa nombres en inglés y agrega auditoría de cambios" />
          </div>
          <button className="btn" disabled={working} onClick={() => run(() => api.generate(project.id, view.kind, view.version, instructions.trim() || null), "Propuesta lista para revisar.")}>
            {button}
          </button>
        </>
      ) : (
        <p className="small muted">Un editor del equipo debe generar la propuesta.</p>
      )}
    </div>
  );
}

export function ChangeRequest({ ctx, kind, placeholder }: { ctx: StageCtx; kind?: StageKind; placeholder: string }) {
  const [text, setText] = useState("");
  const { view, run, project, working, editable } = ctx;
  if (!editable || view.status === "approved" || view.status === "locked") return null;
  const errors = view.issues.filter((i) => i.severity === "error");
  const fixAll = () =>
    run(
      () =>
        api.generate(
          project.id,
          kind ?? view.kind,
          view.version,
          "Corrige estos problemas detectados en la validación, manteniendo todo lo demás igual:\n" + errors.map((e) => `- ${e.message}`).join("\n"),
        ),
      "La IA aplicó las correcciones. Revisa el resultado.",
    );
  return (
    <div className="section">
      <h3>Pedir un cambio a la IA</h3>
      {errors.length > 0 && (
        <div className="banner warn">
          Hay {errors.length === 1 ? "1 problema que impide" : `${errors.length} problemas que impiden`} aprobar esta etapa.
          <button className="btn secondary small" disabled={working} onClick={fixAll}>
            Pedir a la IA que {errors.length === 1 ? "lo corrija" : "los corrija"}
          </button>
        </div>
      )}
      <p className="section-note">Describe el cambio en tus palabras. La IA modifica solo eso y mantiene el resto igual.</p>
      <div className="field">
        <label htmlFor={`cr-${view.kind}`} className="sr-only">
          Cambio pedido
        </label>
        <textarea id={`cr-${view.kind}`} rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} />
      </div>
      <button
        className="btn secondary"
        disabled={working || text.trim().length < 5}
        onClick={async () => {
          const ok = await run(() => api.generate(project.id, kind ?? view.kind, view.version, text.trim()), "Cambio aplicado. Revísalo antes de aprobar.");
          if (ok) setText("");
        }}
      >
        Aplicar cambio con IA
      </button>
    </div>
  );
}

export function JsonEditor({ ctx, value, onSave, help }: { ctx: StageCtx; value: unknown; onSave: (data: unknown) => Promise<unknown>; help?: string }) {
  const initial = JSON.stringify(value, null, 2);
  const [text, setText] = useState(initial);
  const [error, setError] = useState("");
  const { editable, view, working, setDirty } = ctx;
  useEffect(() => {
    setText(JSON.stringify(value, null, 2));
    setError("");
  }, [view.version]); // eslint-disable-line react-hooks/exhaustive-deps
  const readOnly = !editable || view.status === "approved" || view.status === "locked";
  return (
    <div>
      <p className="section-note">{help ?? "Edición avanzada: modifica la estructura completa en JSON. Al guardar se valida el formato y se crea una nueva versión."}</p>
      {error && <div className="banner error">{error}</div>}
      <textarea
        className="json-editor"
        value={text}
        readOnly={readOnly}
        spellCheck={false}
        aria-label="Contenido en JSON"
        onChange={(e) => {
          setText(e.target.value);
          setDirty(e.target.value !== initial);
        }}
      />
      {!readOnly && (
        <div className="row" style={{ marginTop: 10 }}>
          <button
            className="btn"
            disabled={working || text === initial}
            onClick={async () => {
              let data: unknown;
              try {
                data = JSON.parse(text);
              } catch (e) {
                setError(`El JSON no es válido: ${(e as Error).message}`);
                return;
              }
              setError("");
              await onSave(data);
            }}
          >
            Guardar cambios
          </button>
          <button className="btn ghost" disabled={text === initial} onClick={() => (setText(initial), setDirty(false))}>
            Descartar
          </button>
        </div>
      )}
    </div>
  );
}

export function List({ items, empty = "Pendiente" }: { items: string[]; empty?: string }) {
  if (!items.length) return <p className="empty">{empty}</p>;
  return (
    <ul style={{ margin: 0, paddingLeft: 20 }}>
      {items.map((i, idx) => (
        <li key={idx}>{i}</li>
      ))}
    </ul>
  );
}
