export type Role = "owner" | "editor" | "viewer";
export type StageKind = "product" | "data_model" | "api" | "frontend" | "architecture" | "testing" | "review";
export type StageStatus = "locked" | "in_progress" | "approved" | "stale";

export interface UserRef {
  id: string;
  name: string;
  email: string;
}

export interface Me extends UserRef {
  has_password: boolean;
  sso_providers: string[];
}

export interface StageSummary {
  kind: StageKind;
  label: string;
  status: StageStatus;
  version: number;
  updated_at: string | null;
  generating: boolean;
  auto_error?: string | null;
}

export interface QuestionCounts {
  open: number;
  open_blocking: number;
  answered: number;
}

export interface Member {
  user: UserRef;
  role: Role;
  added_at: string;
}

export interface Project {
  id: string;
  name: string;
  idea: string;
  owner: UserRef;
  my_role: Role;
  created_at: string;
  updated_at: string;
  current_stage: StageKind | "documents";
  stages: StageSummary[];
  members: Member[];
  questions: QuestionCounts;
  documents: number;
}

export interface ProjectListItem {
  id: string;
  name: string;
  idea: string;
  my_role: Role;
  owner: UserRef;
  updated_at: string;
  current_stage: StageKind | "documents";
  approved_stages: number;
  members: number;
}

export interface Invitation {
  id: string;
  project_id: string;
  project_name: string | null;
  email: string;
  role: Role;
  status: string;
  invited_by: UserRef | null;
  created_at: string;
}

export interface Issue {
  severity: "error" | "warning";
  code: string;
  message: string;
  path: string;
}

export interface ChecklistItem {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
}

export interface Question {
  id: string;
  code: string;
  text: string;
  rationale: string;
  blocking: boolean;
  affects: string[];
  options: string[];
  section: string;
  status: "open" | "answered" | "resolved" | "dismissed";
  answer: string | null;
  answered_by: UserRef | null;
  answered_at: string | null;
  round: number;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  author: UserRef | null;
  content: string;
  created_at: string;
}

// --- Contenido de las etapas ---------------------------------------------------

export interface UserType {
  id: string;
  name: string;
  description: string;
  goals: string[];
  permissions: string[];
  restrictions: string[];
}
export interface Outcome {
  id: string;
  description: string;
  metric: string;
  target: string;
}
export interface ScopeItem {
  id: string;
  description: string;
  reason: string;
}
export interface JourneyStep {
  number: number;
  actor: string;
  action: string;
  system_response: string;
}
export interface Requirement {
  id: string;
  title: string;
  description: string;
  user_types: string[];
  priority: "must" | "should" | "could";
  acceptance_criteria: string[];
}
export interface EdgeCase {
  id: string;
  category: string;
  scenario: string;
  expected_behavior: string;
}
export interface Assumption {
  id: string;
  description: string;
  accepted: boolean;
}
export interface Brief {
  product_name: string;
  one_liner: string;
  problem: string;
  context: string;
  current_situation: string;
  desired_improvement: string;
  user_types: UserType[];
  expected_outcomes: Outcome[];
  mvp_in_scope: ScopeItem[];
  mvp_out_of_scope: ScopeItem[];
  main_journey: { name: string; actor: string; goal: string; preconditions: string[]; steps: JourneyStep[]; success_result: string };
  functional_requirements: Requirement[];
  business_rules: { id: string; description: string }[];
  technical_constraints: string[];
  integrations: { name: string; purpose: string; required_for_mvp: boolean; failure_behavior: string }[];
  security_requirements: string[];
  non_functional_requirements: string[];
  edge_cases: EdgeCase[];
  assumptions: Assumption[];
  decisions: { id: string; topic: string; decision: string; source: string }[];
  glossary: { term: string; definition: string }[];
}

export interface FK {
  table: string;
  column: string;
  on_delete: "CASCADE" | "RESTRICT" | "SET NULL" | "NO ACTION";
}
export interface Column {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  unique: boolean;
  default: string | null;
  foreign_key: FK | null;
  description: string;
}
export interface Table {
  name: string;
  description: string;
  columns: Column[];
  indexes: { name: string; columns: string[]; unique: boolean }[];
  unique_constraints: string[][];
  checks: { name: string; expression: string }[];
}
export interface DataModel {
  summary: string;
  enums: { name: string; values: string[] }[];
  tables: Table[];
  notes: string[];
}
export interface Relationship {
  parent: string;
  child: string;
  column: string;
  references: string;
  cardinality: string;
  optional: boolean;
  on_delete: string;
  parent_exists: boolean;
}

export interface ApiField {
  name: string;
  type: string;
  required: boolean;
  description: string;
  validation: string;
}
export interface Endpoint {
  id: string;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  summary: string;
  description: string;
  auth: "public" | "authenticated";
  allowed_roles: string[];
  authorization_rule: string;
  params: { name: string; location: string; type: string; required: boolean; description: string }[];
  request_body: ApiField[];
  responses: { status: number; description: string; body_kind: string; fields: ApiField[] }[];
  tables: string[];
  requirements: string[];
}
export interface ApiSpec {
  summary: string;
  conventions: { base_path: string; auth_mechanism: string; error_format: string; pagination: string; datetime_format: string; id_format: string };
  endpoints: Endpoint[];
}

export interface UIAction {
  label: string;
  kind: string;
  endpoint_id: string | null;
  target_screen: string | null;
  roles: string[];
}
export interface Screen {
  id: string;
  name: string;
  route: string;
  purpose: string;
  roles: string[];
  data_endpoints: string[];
  sections: { title: string; kind: string; elements: string[]; actions: UIAction[] }[];
  states: string[];
  journey_steps: number[];
}
export interface FrontendSpec {
  summary: string;
  layout: string;
  design_guidelines: string[];
  start_screen: string;
  screens: Screen[];
  navigation: { from_screen: string; to_screen: string; trigger: string }[];
}

export interface Scenario {
  id: string;
  name: string;
  summary: string;
  when_to_use: string[];
  avoid_when: string[];
  persistence: string;
  backend: string;
  frontend: string;
  communication: string;
  auth: string;
  deployment: string;
  observability: string;
}
export interface ArchitectureEvaluation {
  scores: { scenario_id: string; fit: number; strengths: string[]; risks: string[] }[];
  recommended: string;
  justification: string;
}
export interface ArchitectureSpec {
  scenario_id: string;
  summary: string;
  rationale: string;
  stack: { layer: string; technology: string; version: string; justification: string }[];
  components: { name: string; responsibility: string; technology: string; communicates_with: string[] }[];
  repository_structure: string;
  persistence: string;
  backend: string;
  frontend: string;
  communication: string;
  authentication: string;
  sso: string;
  authorization: string;
  configuration: { name: string; description: string; example: string; secret: boolean; required: boolean }[];
  environments: string[];
  deployment: string;
  observability: string;
  testing: string;
  security: string[];
  risks: string[];
}

export interface Finding {
  id: string;
  severity: "critica" | "importante" | "menor";
  area: string;
  description: string;
  suggestion: string;
  source: "auto" | "ia";
  status: "open" | "resolved" | "accepted";
  note: string;
  resolved_by: string | null;
}

export interface StageApprovals {
  required: number;
  count: number;
  people: { user: UserRef; role: Role; approved: boolean; approved_at: string | null }[];
}

export interface StageView {
  kind: StageKind;
  label: string;
  status: StageStatus;
  version: number;
  updated_at: string | null;
  updated_by: UserRef | null;
  approved_at: string | null;
  approved_by: UserRef | null;
  approved_version: number | null;
  generating: boolean;
  content: any;
  issues: Issue[];
  can_approve: boolean;
  approvals: StageApprovals;
  my_role: Role;
  // producto
  checklist?: ChecklistItem[];
  questions?: Question[];
  messages?: ChatMessage[];
  // datos
  mermaid?: string;
  ddl?: string;
  relationships?: Relationship[];
  junctions?: { table: string; left: string; right: string }[];
  // pantallas
  navigation_map?: string;
  coverage?: Record<string, string[]>;
  seed_sql?: string;
  // arquitectura
  scenarios?: Scenario[];
  // revisión
  assumptions?: Assumption[];
}

export interface DocumentMeta {
  id: string;
  kind: "product_spec" | "architecture";
  filename: string;
  version: number;
  size: number;
  generated_by: UserRef | null;
  created_at: string;
  content?: string;
}

export interface Activity {
  id: number;
  action: string;
  label: string;
  details: Record<string, any>;
  user: UserRef | null;
  created_at: string;
}

export interface SyncState {
  stages: Record<StageKind, StageSummary>;
  last_activity_id: number;
  questions: QuestionCounts;
}
