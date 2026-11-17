import { useEffect, useState } from "react";
import { api } from "../../api";
import { Markdown, Tabs, useToast } from "../../components/ui";
import type { DocumentMeta, Project } from "../../types";
import { STAGE_NAMES, STAGE_ORDER, timeAgo } from "../../util";
import { StageIntro } from "./common";

export default function DocumentsStage({ project, editable, onChange }: { project: Project; editable: boolean; onChange: () => void }) {
  const [docs, setDocs] = useState<DocumentMeta[] | null>(null);
  const [current, setCurrent] = useState<DocumentMeta | null>(null);
  const [mode, setMode] = useState<"rendered" | "raw">("rendered");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const pending = STAGE_ORDER.filter((k) => project.stages.find((s) => s.kind === k)?.status !== "approved");

  const open = async (d: DocumentMeta) => setCurrent(await api.document(project.id, d.id));

  const load = async () => {
    const list = await api.documents(project.id);
    setDocs(list);
    if (list.length && !current) await open(list[0]);
  };

  useEffect(() => {
    load().catch((e) => toast(e.message, "error"));
  }, [project.id, project.documents]); // eslint-disable-line react-hooks/exhaustive-deps

  const generate = async () => {
    setBusy(true);
    try {
      const created = await api.generateDocuments(project.id);
      toast(`Documentos generados (versión ${created[0].version}).`);
      setCurrent(created[0]);
      await load();
      onChange();
    } catch (e) {
      toast(e instanceof Error ? e.message : "No se pudo generar", "error");
    } finally {
      setBusy(false);
    }
  };

  const versions = [...new Set((docs ?? []).map((d) => d.version))];

  return (
    <>
      <StageIntro title="Documentos">
        Plano genera dos archivos Markdown pensados para entregarlos a otra IA: la especificación del producto y la arquitectura. Se arman desde lo aprobado, sin depender de la conversación.
      </StageIntro>
      <div className="box section">
        {pending.length ? (
          <p style={{ margin: 0 }}>
            Para generar los documentos faltan por aprobar: <strong>{pending.map((k) => STAGE_NAMES[k]).join(", ")}</strong>.
          </p>
        ) : (
          <div className="row between">
            <span>Todas las etapas están aprobadas.</span>
            {editable && (
              <button className="btn" disabled={busy} onClick={generate}>
                {docs?.length ? "Generar nueva versión" : "Generar documentos"}
              </button>
            )}
          </div>
        )}
      </div>

      {docs && docs.length > 0 && (
        <section className="section">
          <div className="row between">
            <h3 style={{ border: 0, margin: 0 }}>Versiones</h3>
            <a className="btn secondary small" href={api.zipUrl(project.id)}>
              Descargar la última (.zip)
            </a>
          </div>
          <hr style={{ margin: "10px 0" }} />
          {versions.map((v) => (
            <div key={v} className="invite">
              <span>
                <strong>Versión {v}</strong>{" "}
                <span className="small muted">
                  generada {timeAgo(docs.find((d) => d.version === v)?.created_at)} por {docs.find((d) => d.version === v)?.generated_by?.name ?? "—"}
                </span>
              </span>
              <span className="row">
                {docs
                  .filter((d) => d.version === v)
                  .map((d) => (
                    <span key={d.id} className="row" style={{ gap: 4 }}>
                      <button className="btn ghost small" aria-pressed={current?.id === d.id} onClick={() => open(d)}>
                        {d.filename}
                      </button>
                      <a className="btn ghost small" href={api.downloadUrl(project.id, d.id)} aria-label={`Descargar ${d.filename} versión ${v}`}>
                        Descargar
                      </a>
                    </span>
                  ))}
              </span>
            </div>
          ))}
        </section>
      )}

      {current?.content && (
        <section className="section">
          <div className="row between">
            <h3 style={{ border: 0, margin: 0 }}>
              {current.filename} <span className="muted small">versión {current.version}</span>
            </h3>
            <Tabs
              tabs={[
                ["rendered", "Vista"],
                ["raw", "Markdown"],
              ]}
              value={mode}
              onChange={setMode}
            />
          </div>
          {mode === "rendered" ? (
            <div className="doc-view">
              <Markdown text={current.content} />
            </div>
          ) : (
            <pre style={{ whiteSpace: "pre-wrap" }}>{current.content}</pre>
          )}
        </section>
      )}
    </>
  );
}
