import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import TopBar from "../components/TopBar";
import { useToast } from "../components/ui";
import type { Invitation, ProjectListItem } from "../types";
import { ROLE_NAMES, STAGE_NAMES, timeAgo } from "../util";

export default function Dashboard() {
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [name, setName] = useState("");
  const [idea, setIdea] = useState("");
  const [team, setTeam] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    const [p, i] = await Promise.all([api.projects(), api.myInvitations()]);
    setProjects(p);
    setInvitations(i);
  };

  useEffect(() => {
    load().catch((e) => toast(e.message, "error"));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const emails = team.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
      const bad = emails.filter((x) => !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(x));
      if (bad.length) {
        toast(`Revisa ${bad.length === 1 ? "este correo" : "estos correos"}: ${bad.join(", ")}`, "error");
        return;
      }
      const project = await api.createProject(name.trim(), idea.trim(), emails);
      if (emails.length) toast(`Invitaste a ${emails.length === 1 ? "1 persona" : `${emails.length} personas`} como editores.`);
      navigate(`/p/${project.id}/product`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "No se pudo crear el proyecto", "error");
    } finally {
      setBusy(false);
    }
  };

  const respond = async (inv: Invitation, accept: boolean) => {
    try {
      if (accept) {
        await api.acceptInvitation(inv.id);
        navigate(`/p/${inv.project_id}`);
      } else {
        await api.declineInvitation(inv.id);
        await load();
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : "No se pudo responder", "error");
    }
  };

  return (
    <>
      <TopBar />
      <main className="page">
        {invitations.length > 0 && (
          <section className="box" style={{ marginBottom: 28 }}>
            <h3>Te invitaron a colaborar</h3>
            {invitations.map((inv) => (
              <div className="invite" key={inv.id}>
                <span>
                  <strong>{inv.project_name}</strong>
                  <span className="muted small">
                    {" "}
                    — {inv.invited_by?.name ?? "Alguien"} te invitó como {ROLE_NAMES[inv.role].toLowerCase()}
                  </span>
                </span>
                <span className="row">
                  <button className="btn small" onClick={() => respond(inv, true)}>
                    Unirme
                  </button>
                  <button className="btn ghost small" onClick={() => respond(inv, false)}>
                    Rechazar
                  </button>
                </span>
              </div>
            ))}
          </section>
        )}
        <div className="split">
          <section>
            <h1>Tus proyectos</h1>
            {projects === null && <p className="muted">Cargando…</p>}
            {projects?.length === 0 && (
              <p className="muted">Todavía no tienes proyectos. Escribe tu idea a la derecha y Ideator te guiará pregunta a pregunta.</p>
            )}
            {projects && projects.length > 0 && (
              <div className="project-list">
                {projects.map((p) => (
                  <Link key={p.id} to={`/p/${p.id}`} className="project-row">
                    <h3>{p.name}</h3>
                    <span className="row">
                      <span className="ticks" aria-label={`${p.approved_stages} de 6 etapas aprobadas`}>
                        {Array.from({ length: 6 }, (_, i) => (
                          <span key={i} className={`tick ${i < p.approved_stages ? "done" : i === p.approved_stages ? "current" : ""}`} />
                        ))}
                      </span>
                    </span>
                    <p>{p.idea}</p>
                    <p className="small">
                      {p.current_stage === "documents" ? "Listo para generar documentos." : `En ${STAGE_NAMES[p.current_stage].toLowerCase()}.`} Eres{" "}
                      {ROLE_NAMES[p.my_role].toLowerCase()} en un equipo de {p.members}. Actualizado {timeAgo(p.updated_at)}.
                    </p>
                  </Link>
                ))}
              </div>
            )}
          </section>
          <section className="box">
            <h3>Nuevo proyecto</h3>
            <form onSubmit={create}>
              <div className="field">
                <label htmlFor="pname">Nombre</label>
                <input id="pname" type="text" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} placeholder="Ej.: Reserva de canchas del club" />
              </div>
              <div className="field">
                <label htmlFor="pidea">La idea, como la contarías en voz alta</label>
                <textarea
                  id="pidea"
                  value={idea}
                  onChange={(e) => setIdea(e.target.value)}
                  required
                  minLength={10}
                  maxLength={6000}
                  rows={7}
                  placeholder="Qué problema quieres resolver, para quién y por qué ahora. No importa si está incompleta: Ideator te preguntará lo que falte."
                />
              </div>
              <div className="field">
                <label htmlFor="pteam">Equipo (opcional)</label>
                <input
                  id="pteam"
                  type="text"
                  value={team}
                  onChange={(e) => setTeam(e.target.value)}
                  placeholder="Correos separados por coma: tomas@uai.cl, ignacio@uai.cl"
                />
                <p className="small muted" style={{ margin: "6px 0 0" }}>
                  Entran como editores y cada etapa avanza cuando aprueban todos.
                </p>
              </div>
              <button className="btn" type="submit" disabled={busy || name.trim().length === 0 || idea.trim().length < 10}>
                Crear proyecto
              </button>
              <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
                El proyecto es privado: solo lo ven las personas que invites.
              </p>
            </form>
          </section>
        </div>
      </main>
    </>
  );
}
