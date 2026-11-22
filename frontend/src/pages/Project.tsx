import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import TopBar from "../components/TopBar";
import { Avatar, Busy, Checklist, ConfirmButton, IssueList, useToast } from "../components/ui";
import type { Project, StageKind, StageView, SyncState } from "../types";
import { canEdit, STAGE_NAMES, STAGE_ORDER, STATUS_NAMES, timeAgo } from "../util";
import ActivityPanel from "./ActivityPanel";
import MembersPanel from "./MembersPanel";
import ApiStage from "./stages/ApiStage";
import ArchitectureStage from "./stages/ArchitectureStage";
import DataModelStage from "./stages/DataModelStage";
import DocumentsStage from "./stages/DocumentsStage";
import FrontendStage from "./stages/FrontendStage";
import ProductStage from "./stages/ProductStage";
import ReviewStage from "./stages/ReviewStage";

export interface StageCtx {
  project: Project;
  view: StageView;
  editable: boolean;
  working: boolean;
  run: (fn: () => Promise<StageView>, success?: string) => Promise<boolean>;
  setDirty: (dirty: boolean) => void;
  reload: () => Promise<void>;
}

type Current = StageKind | "documents";

const STAGES: Record<StageKind, (ctx: StageCtx) => JSX.Element> = {
  product: (ctx) => <ProductStage ctx={ctx} />,
  data_model: (ctx) => <DataModelStage ctx={ctx} />,
  api: (ctx) => <ApiStage ctx={ctx} />,
  frontend: (ctx) => <FrontendStage ctx={ctx} />,
  architecture: (ctx) => <ArchitectureStage ctx={ctx} />,
  review: (ctx) => <ReviewStage ctx={ctx} />,
};

function changed(a: SyncState, b: SyncState): boolean {
  if (a.last_activity_id !== b.last_activity_id) return true;
  return STAGE_ORDER.some((k) => {
    const x = a.stages[k];
    const y = b.stages[k];
    return !x || !y || x.version !== y.version || x.status !== y.status || x.generating !== y.generating || x.auto_error !== y.auto_error;
  });
}

export default function ProjectPage() {
  const { projectId = "", stage } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuth();
  const [project, setProject] = useState<Project | null>(null);
  const [view, setView] = useState<StageView | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [remote, setRemote] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [panel, setPanel] = useState<"members" | "activity" | null>(null);
  const dirty = useRef(false);
  const sync = useRef<SyncState | null>(null);
  const viewRef = useRef<StageView | null>(null);
  viewRef.current = view;

  const current: Current = (stage as Current) || project?.current_stage || "product";

  const loadProject = useCallback(async () => {
    try {
      setProject(await api.project(projectId));
    } catch (e) {
      if (e instanceof ApiError) setLoadError(e);
    }
  }, [projectId]);

  const loadStage = useCallback(
    async (kind: Current) => {
      if (kind === "documents") return;
      try {
        setView(await api.stage(projectId, kind));
        dirty.current = false;
        setRemote(null);
        setConflict(null);
      } catch (e) {
        if (e instanceof ApiError) setLoadError(e);
      }
    },
    [projectId],
  );

  useEffect(() => {
    setProject(null);
    setLoadError(null);
    sync.current = null;
    void loadProject();
  }, [loadProject]);

  useEffect(() => {
    if (!project) return;
    if (!stage) {
      navigate(`/p/${projectId}/${project.current_stage}`, { replace: true });
      return;
    }
    setView(null);
    void loadStage(current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, project?.id]);

  // Colaboración: cada 4 s se consulta un estado liviano y se recarga lo que cambió.
  useEffect(() => {
    const timer = setInterval(async () => {
      if (document.hidden) return;
      try {
        const next = await api.sync(projectId);
        const prev = sync.current;
        sync.current = next;
        // La etapa en pantalla puede haber quedado atrás (por ejemplo, la IA terminó justo al cargarla).
        const shown = viewRef.current;
        const live = current !== "documents" ? next.stages[current] : undefined;
        if (shown && live && shown.kind === current && !working && !dirty.current && (live.version !== shown.version || live.generating !== shown.generating)) {
          await loadStage(current);
        }
        if (!prev || !changed(prev, next)) return;
        await loadProject();
        if (current !== "documents") {
          const a = prev.stages[current];
          const b = next.stages[current];
          if (a && b && (a.version !== b.version || a.status !== b.status || a.generating !== b.generating || a.auto_error !== b.auto_error)) {
            if (dirty.current && a.version !== b.version) setRemote(`Otra persona guardó una versión más nueva (v${b.version}).`);
            else if (!working) await loadStage(current);
          }
        }
        if (next.last_activity_id !== prev.last_activity_id) {
          const [last] = await api.activity(projectId);
          if (last?.user && last.user.id !== user?.id) toast(`${last.user.name} ${last.label}${last.details?.kind ? ` (${STAGE_NAMES[last.details.kind as StageKind] ?? last.details.kind})` : ""}.`);
        }
      } catch {
        /* sin conexión momentánea: se reintenta en el siguiente ciclo */
      }
    }, 4000);
    return () => clearInterval(timer);
  }, [projectId, current, working, loadProject, loadStage, toast, user?.id]);

  const run = useCallback(
    async (fn: () => Promise<StageView>, success?: string) => {
      setWorking(true);
      setConflict(null);
      try {
        const next = await fn();
        setView(next);
        dirty.current = false;
        setRemote(null);
        await loadProject();
        if (success) toast(success);
        return true;
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.code === "version_conflict") {
            const who = e.details?.updated_by ? ` Último cambio de ${e.details.updated_by}.` : "";
            setConflict(`${e.message}${who}`);
          } else if (e.code === "stage_not_ready") {
            toast("Todavía no se puede aprobar: revisa los problemas de la etapa.", "error");
            await loadStage(current);
          } else toast(e.message, "error");
        } else toast("Ocurrió un error inesperado.", "error");
        return false;
      } finally {
        setWorking(false);
      }
    },
    [current, loadProject, loadStage, toast],
  );

  if (loadError) {
    const msg =
      loadError.status === 403
        ? "No tienes acceso a este proyecto. Pídele al dueño que te invite."
        : loadError.status === 404
          ? "Este proyecto no existe o fue eliminado."
          : loadError.message;
    return (
      <>
        <TopBar />
        <main className="page">
          <div className="banner error">{msg}</div>
          <button className="btn secondary" onClick={() => navigate("/")}>
            Volver a mis proyectos
          </button>
        </main>
      </>
    );
  }

  if (!project) {
    return (
      <>
        <TopBar />
        <main className="page muted">Cargando proyecto…</main>
      </>
    );
  }

  const editable = canEdit(project.my_role);
  const statusOf = (k: StageKind) => project.stages.find((s) => s.kind === k)!;
  const ctx: StageCtx | null = view && view.kind === current ? { project, view, editable, working, run, setDirty: (d) => {
          dirty.current = d;
        }, reload: () => loadStage(current) } : null;
  const reviewApproved = statusOf("review").status === "approved";

  return (
    <>
      <TopBar>
        <span className="crumb">
          <strong>{project.name}</strong>
        </span>
      </TopBar>
      <div className="project-layout">
        <nav className="rail" aria-label="Etapas del proyecto">
          <ol>
            {STAGE_ORDER.map((k, i) => {
              const s = statusOf(k);
              return (
                <li key={k} className={`${s.status} ${current === k ? "active" : ""}`}>
                  <span className="node" aria-hidden="true">
                    {s.status === "approved" ? "✓" : s.status === "stale" ? "!" : i + 1}
                  </span>
                  <button onClick={() => navigate(`/p/${project.id}/${k}`)} disabled={s.status === "locked"} aria-current={current === k ? "step" : undefined}>
                    {STAGE_NAMES[k]}
                    <span className="state">{s.generating ? "La IA está trabajando" : STATUS_NAMES[s.status]}</span>
                  </button>
                </li>
              );
            })}
            <li className={`${reviewApproved ? "in_progress" : "locked"} ${current === "documents" ? "active" : ""}`}>
              <span className="node" aria-hidden="true">
                7
              </span>
              <button onClick={() => navigate(`/p/${project.id}/documents`)}>
                Documentos
                <span className="state">{project.documents ? `${project.documents / 2} versión(es)` : reviewApproved ? "Listos para generar" : "Al final del proceso"}</span>
              </button>
            </li>
          </ol>
        </nav>

        <main>
          {conflict && (
            <div className="banner warn">
              {conflict}
              <button className="btn secondary small" onClick={() => loadStage(current)}>
                Cargar la versión vigente
              </button>
            </div>
          )}
          {remote && (
            <div className="banner info">
              {remote} Tus cambios sin guardar se perderán si recargas.
              <button className="btn secondary small" onClick={() => loadStage(current)}>
                Ver versión nueva
              </button>
            </div>
          )}
          {current === "documents" ? (
            <DocumentsStage project={project} editable={editable} onChange={loadProject} />
          ) : ctx ? (
            <>
              {(working || ctx.view.generating) && <Busy />}
              {ctx.view.content?.auto_error && !ctx.view.generating && (
                <div className="banner error row between">
                  <span>La IA no pudo preparar esta etapa: {String(ctx.view.content.auto_error)}</span>
                  {editable && (
                    <button
                      className="btn small"
                      onClick={async () => {
                        await api.autopilot(project.id);
                        toast("Reintentando. La IA vuelve a trabajar en esta etapa.");
                        await loadStage(current);
                      }}
                    >
                      Reintentar
                    </button>
                  )}
                </div>
              )}
              {STAGES[current as StageKind](ctx)}
            </>
          ) : (
            <p className="muted">Cargando etapa…</p>
          )}
        </main>

        <aside className="aside" aria-label="Estado de la etapa">
          {ctx && <StageStatusBox ctx={ctx} />}
          {ctx?.view.checklist && (
            <div className="box">
              <h4>Checklist de la definición</h4>
              <Checklist items={ctx.view.checklist} />
            </div>
          )}
          {ctx && ctx.view.status !== "locked" && (
            <div className="box">
              <h4>Problemas detectados</h4>
              <IssueList
                issues={ctx.view.checklist ? ctx.view.issues.filter((i) => !ctx.view.checklist!.some((c) => i.code === `product.${c.key}`)) : ctx.view.issues}
                empty={ctx.view.checklist ? "Nada más fuera de la checklist." : undefined}
              />
            </div>
          )}
          <div className="box">
            <h4>Equipo</h4>
            <div className="row" style={{ marginBottom: 10 }}>
              <span className="avatars">
                {project.members.map((m) => (
                  <Avatar key={m.user.id} name={m.user.name} />
                ))}
              </span>
              <span className="small muted">{project.members.length} en el proyecto</span>
            </div>
            <div className="row">
              <button className="btn secondary small" onClick={() => setPanel("members")}>
                {project.my_role === "owner" ? "Invitar y gestionar" : "Ver equipo"}
              </button>
              <button className="btn ghost small" onClick={() => setPanel("activity")}>
                Actividad
              </button>
            </div>
          </div>
        </aside>
      </div>
      {panel === "members" && <MembersPanel project={project} onClose={() => setPanel(null)} onChange={loadProject} />}
      {panel === "activity" && <ActivityPanel projectId={project.id} onClose={() => setPanel(null)} />}
    </>
  );
}

function StageStatusBox({ ctx }: { ctx: StageCtx }) {
  const { view, editable, run, project, working } = ctx;
  const { user } = useAuth();
  const errors = view.issues.filter((i) => i.severity === "error").length;
  const team = view.approvals;
  const mine = team?.people.find((p) => p.user.id === user?.id)?.approved ?? false;
  const pending = team ? team.people.filter((p) => !p.approved).map((p) => p.user.name.split(" ")[0]) : [];
  const open = view.status === "in_progress" || view.status === "stale";
  const approveLabel = !team || team.required <= 1 ? "Aprobar etapa" : `Aprobar (${team.count} de ${team.required})`;
  const navigate = useNavigate();
  const afterApprove = async () => {
    let approved = false;
    const ok = await run(async () => {
      const next = await api.approve(project.id, view.kind, view.version);
      approved = next.status === "approved";
      return next;
    }, !team || team.count + 1 >= team.required ? "Etapa aprobada. La IA ya está preparando la siguiente." : "Tu aprobación quedó registrada. Falta que aprueben los demás.");
    // Con el piloto automático la siguiente etapa ya se está generando: se va directo a verla.
    if (ok && approved) {
      const idx = STAGE_ORDER.indexOf(view.kind);
      navigate(`/p/${project.id}/${idx + 1 < STAGE_ORDER.length ? STAGE_ORDER[idx + 1] : "documents"}`);
    }
  };
  return (
    <div className="box">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h4 style={{ margin: 0 }}>Estado</h4>
        {view.status === "approved" ? (
          <span className="stamp">Aprobada v{view.approved_version}</span>
        ) : view.status === "stale" ? (
          <span className="stamp stale">Por revisar</span>
        ) : (
          <span className="small muted">{STATUS_NAMES[view.status]}</span>
        )}
      </div>
      <p className="small muted">
        Versión {view.version}
        {view.updated_by ? `, editada por ${view.updated_by.name} ${timeAgo(view.updated_at)}` : ""}.
        {view.status === "approved" && view.approved_by ? ` Aprobada por ${team && team.required > 1 ? "todo el equipo" : view.approved_by.name}.` : ""}
      </p>
      {team && team.required > 1 && view.status !== "locked" && (
        <div className="approvals" aria-label="Aprobaciones del equipo">
          <p className="small" style={{ margin: "0 0 6px" }}>
            <strong>Aprobación del equipo:</strong> {team.count} de {team.required}
          </p>
          <ul>
            {team.people.map((p) => (
              <li key={p.user.id} className={p.approved ? "ok" : ""}>
                <Avatar name={p.user.name} />
                <span>{p.user.name}</span>
                <span className="small muted">{p.approved ? `aprobó ${timeAgo(p.approved_at)}` : "pendiente"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {view.status === "stale" && <p className="small">Una etapa anterior cambió. Revisa esta etapa y vuelve a aprobarla.</p>}
      {view.status === "locked" && <p className="small">Se habilita cuando se aprueba la etapa anterior.</p>}
      {editable && open && !mine && (
        <>
          <button className="btn approve" disabled={!view.can_approve || working} onClick={afterApprove}>
            {approveLabel}
          </button>
          {!view.can_approve && (
            <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
              {errors ? `Resuelve ${errors === 1 ? "el problema marcado" : `los ${errors} problemas marcados`} en rojo para poder aprobar.` : "Completa la etapa para poder aprobarla."}
            </p>
          )}
        </>
      )}
      {editable && open && mine && (
        <>
          <p className="small" style={{ marginTop: 0 }}>
            Ya aprobaste esta versión. Falta que {pending.length === 1 ? "apruebe" : "aprueben"} {pending.join(", ")}. Si alguien cambia la etapa, hay que volver a aprobarla.
          </p>
          <button className="btn ghost small" disabled={working} onClick={() => run(() => api.withdrawApproval(project.id, view.kind), "Retiraste tu aprobación.")}>
            Retirar mi aprobación
          </button>
        </>
      )}
      {editable && view.status === "approved" && (
        <ConfirmButton
          label="Reabrir para editar"
          confirmLabel="Sí, reabrir"
          question={team && team.required > 1 ? "Las etapas siguientes quedarán por revisar y todos tendrán que volver a aprobar." : "Las etapas siguientes quedarán por revisar."}
          onConfirm={() => run(() => api.reopen(project.id, view.kind, view.version), "Etapa reabierta.")}
          disabled={working}
        />
      )}
      {!editable && <p className="small muted">Tienes rol de lector: puedes ver todo, pero no modificar ni aprobar.</p>}
      {view.kind !== "review" && view.status !== "locked" && <ExportStage projectId={project.id} kind={view.kind} />}
    </div>
  );
}

function ExportStage({ projectId, kind }: { projectId: string; kind: StageKind }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const fetchDoc = async () => {
    setBusy(true);
    try {
      return await api.stageMarkdown(projectId, kind);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "No se pudo exportar la etapa.", "error");
      return null;
    } finally {
      setBusy(false);
    }
  };
  const download = (filename: string, content: string) => {
    const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };
  const copy = async () => {
    const doc = await fetchDoc();
    if (!doc) return;
    try {
      await navigator.clipboard.writeText(doc.content);
      toast(doc.status === "approved" ? "Etapa copiada en Markdown. Pégala en la IA que quieras." : "Copiada en Markdown. Ojo: la etapa todavía no está aprobada.");
    } catch {
      download(doc.filename, doc.content);
      toast("Tu navegador no permitió copiar: se descargó el archivo .md.");
    }
  };
  return (
    <div className="export-stage">
      <button className="btn secondary small" disabled={busy} onClick={copy}>
        Copiar para la IA
      </button>
      <button
        className="btn ghost small"
        disabled={busy}
        onClick={async () => {
          const doc = await fetchDoc();
          if (doc) download(doc.filename, doc.content);
        }}
      >
        Descargar .md
      </button>
    </div>
  );
}
