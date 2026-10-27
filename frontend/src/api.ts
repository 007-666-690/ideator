import type {
  Activity,
  DocumentMeta,
  Invitation,
  Me,
  Member,
  Project,
  ProjectListItem,
  Role,
  Scenario,
  StageKind,
  StageSummary,
  StageView,
  SyncState,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  details: any;

  constructor(status: number, code: string, message: string, details?: any) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type Json = Record<string, unknown> | unknown[] | null;

async function request<T>(method: string, path: string, body?: Json): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "include",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network_error", "No hay conexión con el servidor. Revisa tu red e intenta de nuevo.");
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!response.ok) {
    const err = data?.error;
    throw new ApiError(
      response.status,
      err?.code ?? "error",
      err?.message ?? `Error ${response.status}`,
      err?.details,
    );
  }
  return data as T;
}

const get = <T>(path: string) => request<T>("GET", path);
const post = <T>(path: string, body: Json = {}) => request<T>("POST", path, body);
const put = <T>(path: string, body: Json) => request<T>("PUT", path, body);
const patch = <T>(path: string, body: Json) => request<T>("PATCH", path, body);
const del = <T>(path: string) => request<T>("DELETE", path);

const p = (projectId: string) => `/api/projects/${projectId}`;

export const api = {
  // Autenticación
  me: () => get<Me>("/api/auth/me"),
  login: (email: string, password: string) => post<Me>("/api/auth/login", { email, password }),
  register: (name: string, email: string, password: string) => post<Me>("/api/auth/register", { name, email, password }),
  logout: () => post<void>("/api/auth/logout"),
  providers: () => get<{ id: string; name: string; enabled: boolean }[]>("/api/auth/providers"),

  // Proyectos
  projects: () => get<ProjectListItem[]>("/api/projects"),
  createProject: (name: string, idea: string) => post<Project>("/api/projects", { name, idea }),
  project: (id: string) => get<Project>(p(id)),
  updateProject: (id: string, data: { name?: string; idea?: string }) => patch<Project>(p(id), data),
  deleteProject: (id: string) => del<void>(p(id)),
  sync: (id: string) => get<SyncState>(`${p(id)}/sync`),
  activity: (id: string) => get<Activity[]>(`${p(id)}/activity?limit=100`),
  stages: (id: string) => get<StageSummary[]>(`${p(id)}/stages`),

  // Miembros
  members: (id: string) => get<{ members: Member[]; invitations: Invitation[] }>(`${p(id)}/members`),
  invite: (id: string, email: string, role: Role) => post<Invitation>(`${p(id)}/invitations`, { email, role }),
  revokeInvitation: (id: string, invitationId: string) => del<void>(`${p(id)}/invitations/${invitationId}`),
  changeRole: (id: string, userId: string, role: Role) => patch<Member>(`${p(id)}/members/${userId}`, { role }),
  removeMember: (id: string, userId: string) => del<void>(`${p(id)}/members/${userId}`),
  myInvitations: () => get<Invitation[]>("/api/invitations"),
  acceptInvitation: (invitationId: string) => post<{ project_id: string }>(`/api/invitations/${invitationId}/accept`),
  declineInvitation: (invitationId: string) => post<void>(`/api/invitations/${invitationId}/decline`),

  // Etapas
  stage: (id: string, kind: StageKind) => get<StageView>(`${p(id)}/stages/${kind}`),
  startProduct: (id: string, version: number) => post<StageView>(`${p(id)}/product/start`, { version }),
  productTurn: (id: string, version: number, answers: { question_id: string; answer: string }[], message: string | null) =>
    post<StageView>(`${p(id)}/product/turn`, { version, answers, message }),
  dismissQuestion: (id: string, questionId: string, reason: string) => post<StageView>(`${p(id)}/questions/${questionId}/dismiss`, { reason }),
  saveBrief: (id: string, version: number, brief: unknown) => put<StageView>(`${p(id)}/stages/product`, { version, brief } as Json),
  acceptAssumptions: (id: string, version: number, ids: string[] | null) => post<StageView>(`${p(id)}/product/assumptions/accept`, { version, ids }),
  generate: (id: string, kind: StageKind, version: number, instructions: string | null) =>
    post<StageView>(`${p(id)}/stages/${kind}/generate`, { version, instructions }),
  saveStage: (id: string, kind: StageKind, version: number, data: unknown, summary?: string) =>
    put<StageView>(`${p(id)}/stages/${kind}`, { version, data, summary: summary ?? null } as Json),
  approve: (id: string, kind: StageKind, version: number) => post<StageView>(`${p(id)}/stages/${kind}/approve`, { version }),
  reopen: (id: string, kind: StageKind, version: number) => post<StageView>(`${p(id)}/stages/${kind}/reopen`, { version }),
  architectures: () => get<Scenario[]>("/api/architectures"),
  evaluateArchitecture: (id: string, version: number) => post<StageView>(`${p(id)}/architecture/evaluate`, { version }),
  selectArchitecture: (id: string, version: number, scenarioId: string) =>
    post<StageView>(`${p(id)}/architecture/select`, { version, scenario_id: scenarioId }),
  runReview: (id: string, version: number) => post<StageView>(`${p(id)}/review/run`, { version }),
  resolveFinding: (id: string, findingId: string, version: number, resolution: "fixed" | "accepted" | "open", note: string) =>
    post<StageView>(`${p(id)}/review/findings/${findingId}`, { version, resolution, note }),

  // Documentos
  documents: (id: string) => get<DocumentMeta[]>(`${p(id)}/documents`),
  document: (id: string, documentId: string) => get<DocumentMeta>(`${p(id)}/documents/${documentId}`),
  generateDocuments: (id: string) => post<DocumentMeta[]>(`${p(id)}/documents`),
  downloadUrl: (id: string, documentId: string) => `${p(id)}/documents/${documentId}/download`,
  zipUrl: (id: string) => `${p(id)}/documents/latest.zip`,
};
