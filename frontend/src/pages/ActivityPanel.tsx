import { useEffect, useState } from "react";
import { api } from "../api";
import { Modal } from "../components/ui";
import type { Activity, StageKind } from "../types";
import { STAGE_NAMES, timeAgo } from "../util";

function detail(a: Activity): string {
  const d = a.details ?? {};
  if (d.kind) return STAGE_NAMES[d.kind as StageKind] ?? String(d.kind);
  if (d.email) return String(d.email);
  if (d.user) return String(d.user);
  if (d.scenario_id) return String(d.scenario_id);
  if (d.round) return `ronda ${d.round}`;
  if (d.version) return `versión ${d.version}`;
  if (d.ids) return (d.ids as string[]).join(", ");
  return "";
}

export default function ActivityPanel({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const [items, setItems] = useState<Activity[] | null>(null);
  useEffect(() => {
    api.activity(projectId).then(setItems).catch(() => setItems([]));
  }, [projectId]);
  return (
    <Modal title="Actividad del proyecto" onClose={onClose}>
      <p className="small muted">Cada cambio queda registrado con la persona que lo hizo.</p>
      {items === null && <p className="muted">Cargando…</p>}
      <ul className="activity">
        {items?.map((a) => (
          <li key={a.id}>
            <strong>{a.user?.name ?? "Sistema"}</strong> {a.label} {detail(a) && <span className="muted">{detail(a)}</span>}
            {a.details?.instructions && <div className="small muted">«{String(a.details.instructions)}»</div>}
            <time dateTime={a.created_at}>{timeAgo(a.created_at)}</time>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
