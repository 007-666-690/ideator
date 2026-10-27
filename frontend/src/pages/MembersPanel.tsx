import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Avatar, Modal, useToast } from "../components/ui";
import type { Invitation, Member, Project, Role } from "../types";
import { ROLE_NAMES } from "../util";

export default function MembersPanel({ project, onClose, onChange }: { project: Project; onClose: () => void; onChange: () => void }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("editor");
  const toast = useToast();
  const { user } = useAuth();
  const navigate = useNavigate();
  const isOwner = project.my_role === "owner";

  const load = async () => {
    const data = await api.members(project.id);
    setMembers(data.members);
    setInvitations(data.invitations);
  };
  useEffect(() => {
    load().catch((e) => toast(e.message, "error"));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast(ok);
      await load();
      onChange();
    } catch (e) {
      toast(e instanceof Error ? e.message : "No se pudo completar", "error");
    }
  };

  const invite = async (e: FormEvent) => {
    e.preventDefault();
    await act(() => api.invite(project.id, email.trim(), role), `Invitación enviada a ${email.trim()}.`);
    setEmail("");
  };

  return (
    <Modal title="Equipo del proyecto" onClose={onClose}>
      <p className="small muted">
        El proyecto es privado. Los editores pueden responder preguntas, editar y aprobar etapas; los lectores solo pueden ver. Solo el dueño invita y cambia roles.
      </p>
      <table className="data" style={{ marginBottom: 18 }}>
        <tbody>
          {members.map((m) => (
            <tr key={m.user.id}>
              <td style={{ width: 36 }}>
                <Avatar name={m.user.name} />
              </td>
              <td>
                {m.user.name}
                <div className="small muted">{m.user.email}</div>
              </td>
              <td style={{ width: 130 }}>
                {isOwner && m.role !== "owner" ? (
                  <select
                    aria-label={`Rol de ${m.user.name}`}
                    value={m.role}
                    onChange={(e) => act(() => api.changeRole(project.id, m.user.id, e.target.value as Role), "Rol actualizado.")}
                  >
                    <option value="editor">Editor</option>
                    <option value="viewer">Lector</option>
                  </select>
                ) : (
                  ROLE_NAMES[m.role]
                )}
              </td>
              <td style={{ width: 90, textAlign: "right" }}>
                {m.role !== "owner" && isOwner && (
                  <button className="btn ghost small" onClick={() => act(() => api.removeMember(project.id, m.user.id), `${m.user.name} salió del proyecto.`)}>
                    Quitar
                  </button>
                )}
                {m.role !== "owner" && !isOwner && m.user.id === user?.id && (
                  <button
                    className="btn ghost small"
                    onClick={async () => {
                      await api.removeMember(project.id, m.user.id);
                      navigate("/");
                    }}
                  >
                    Salir
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {invitations.length > 0 && (
        <>
          <h4>Invitaciones pendientes</h4>
          {invitations.map((i) => (
            <div className="invite" key={i.id}>
              <span>
                {i.email} <span className="muted small">como {ROLE_NAMES[i.role].toLowerCase()}</span>
              </span>
              {isOwner && (
                <button className="btn ghost small" onClick={() => act(() => api.revokeInvitation(project.id, i.id), "Invitación anulada.")}>
                  Anular
                </button>
              )}
            </div>
          ))}
        </>
      )}
      {isOwner && (
        <form onSubmit={invite} style={{ marginTop: 18 }}>
          <h4>Invitar a alguien</h4>
          <div className="row" style={{ alignItems: "flex-end" }}>
            <div className="field grow" style={{ marginBottom: 0 }}>
              <label htmlFor="inv-email">Correo</label>
              <input id="inv-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="compañero@alumnos.uai.cl" />
            </div>
            <div className="field" style={{ marginBottom: 0, width: 120 }}>
              <label htmlFor="inv-role">Rol</label>
              <select id="inv-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                <option value="editor">Editor</option>
                <option value="viewer">Lector</option>
              </select>
            </div>
            <button className="btn" type="submit">
              Invitar
            </button>
          </div>
          <p className="small muted" style={{ marginTop: 8 }}>
            La persona verá la invitación al entrar a Ideator con ese correo.
          </p>
        </form>
      )}
    </Modal>
  );
}
