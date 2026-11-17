import type { Role, StageKind, StageStatus } from "./types";

export const STAGE_ORDER: StageKind[] = ["product", "data_model", "api", "frontend", "architecture", "review"];

export const STAGE_NAMES: Record<StageKind | "documents", string> = {
  product: "Definición del producto",
  data_model: "Modelo de datos",
  api: "Backend y API",
  frontend: "Pantallas y navegación",
  architecture: "Arquitectura",
  review: "Revisión final",
  documents: "Documentos",
};

export const STATUS_NAMES: Record<StageStatus, string> = {
  locked: "Bloqueada",
  in_progress: "En curso",
  approved: "Aprobada",
  stale: "Por revisar",
};

export const ROLE_NAMES: Record<Role, string> = { owner: "Dueño", editor: "Editor", viewer: "Lector" };

const rtf = new Intl.RelativeTimeFormat("es", { numeric: "auto" });

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return "recién";
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), "day");
  return new Date(iso).toLocaleDateString("es-CL");
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export function canEdit(role: Role): boolean {
  return role === "owner" || role === "editor";
}

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export const DELEGATED = "[DELEGADO] El equipo delega esta decisión a Ideator.";

// Nombre de la app (el proyecto del curso es "Ideator"; cambiar aquí si se quiere otro nombre).
export const APP_NAME = "Plano";
