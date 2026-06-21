const BASE = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:8000";
const TOOL_RT = process.env.NEXT_PUBLIC_TOOL_RUNTIME_URL ?? "http://localhost:8001";

async function get<T>(path: string, base = BASE): Promise<T> {
  const r = await fetch(`${base}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

async function post<T>(path: string, body?: unknown, base = BASE): Promise<T> {
  const r = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

// --- Tasks ---
export const getTasks = (limit = 50) => get<TaskList>(`/tasks?limit=${limit}`);
export const getTask = (id: string) => get<Task>(`/tasks/${id}`);
export const createTask = (body: CreateTaskBody) => post<{ task_id: string }>("/tasks", body);
export const approveTask = (id: string, actor = "studio") => post(`/tasks/${id}/approve`, { actor });
export const rejectTask = (id: string, actor = "studio", reason?: string) =>
  post(`/tasks/${id}/reject`, { actor, reason });
export const approveNode = (id: string, nodeKey: string, actor = "studio") =>
  post(`/tasks/${id}/nodes/${nodeKey}/approve-node`, { actor });

// --- Task details ---
export const getTaskTools = (id: string) => get<ToolInvocations>(`/tasks/${id}/tools`);
export const getTaskCompensations = (id: string) => get<Compensations>(`/tasks/${id}/compensations`);
export const getTaskEvents = (id: string) => get<Events>(`/tasks/${id}/events`);
export const getTaskArtifacts = (id: string) => get<Artifacts>(`/tasks/${id}/artifacts`);

// --- v2.1 Workspace Runtime (builder, via control-plane proxy) ---
export const buildRepo = (taskId: string, stack = "nextjs-prisma-sqlite") =>
  post<BuildRecord>(`/tasks/${taskId}/build?stack=${stack}`);
export const getTaskBuilds = (taskId: string) => get<BuildList>(`/tasks/${taskId}/builds`);
export const getBuild = (buildId: string) => get<BuildDetail>(`/builds/${buildId}`);
export const getBuildFile = (buildId: string, path: string) =>
  get<{ path: string; content: string }>(`/builds/${buildId}/file?path=${encodeURIComponent(path)}`);

// --- v2.2 Build Execution (sandbox, via control-plane proxy) ---
export const runBuild = (buildId: string) => post<BuildRun>(`/builds/${buildId}/run`);
export const getBuildRuns = (buildId: string) => get<BuildRunList>(`/builds/${buildId}/runs`);

// --- v2.3 Live Preview (preview servisi, via control-plane proxy) ---
export const startPreview = (buildId: string) => post<PreviewStatus>(`/builds/${buildId}/preview`);
export const getPreviewStatus = () => get<PreviewStatus>(`/preview/status`);
export const stopPreview = () => post<PreviewStatus>(`/preview/stop`);
export const getMemory = () => get<MemoryList>(`/memory`);
export const recallMemory = (goal: string) => get<RecallResult>(`/memory/recall?goal=${encodeURIComponent(goal)}`);
export const applyCompensation = (taskId: string, execId: string, actor = "studio") =>
  post(`/tasks/${taskId}/compensations/${execId}/apply`, { actor });

// --- Metrics & Observer ---
export const getMetrics = () => get<Record<string, number>>("/metrics");

// --- Tool Runtime (via control-plane proxy) ---
export const getAdapterHealth = () => get<AdapterHealth>("/health/adapters");
export const getToolCapabilities = () => get<ToolCapabilities>("/tools/capabilities");

// --- Observer (v1.3, via control-plane proxy) ---
export type ObserverWindow = "1h" | "24h" | "7d";
export const getObserverScores = (window: ObserverWindow = "24h") =>
  get<ObserverScores>(`/observer/scores?window=${window}`);
export const getObserverClusters = (window: ObserverWindow = "24h") =>
  get<ObserverClusters>(`/observer/clusters?window=${window}`);
export const getObserverRecommendations = (window: ObserverWindow = "24h") =>
  get<ObserverRecommendations>(`/observer/recommendations?window=${window}`);

// --- Types ---
export interface CreateTaskBody {
  goal: string;
  skill?: string;
  actor?: string;
  require_approval?: boolean;
  inputs?: Record<string, unknown>;
}

export interface TaskSummary {
  id: string;
  goal: string;
  status: string;
  skill: string | null;
  created_at: string | null;
}

export interface TaskList {
  count: number;
  tasks: TaskSummary[];
}

export interface PlanNode {
  key: string;
  skill?: string;
  kind?: string;
  tool?: string;
  depends_on: string[];
  agent?: string;
  role?: string;
  status?: string;
}

export interface Task {
  id: string;
  goal: string;
  status: string;
  skill: string | null;
  created_at: string | null;
  plan: PlanNode[];
  nodes?: NodeDetail[];
}

export interface NodeDetail {
  key: string;
  status: string;
  node_kind?: string;
  tool?: string;
  created_at: string | null;
  finished_at: string | null;
  retry_count?: number;
  error?: string;
}

export interface ToolInvocation {
  node_key: string;
  tool: string;
  status: string;
  attempt: number;
  error_code: string | null;
  dry_run: boolean;
  rate_limited: boolean;
  schema_errors: unknown;
  result: Record<string, unknown> | null;
}

export interface ToolInvocations {
  count: number;
  invocations: ToolInvocation[];
}

export interface Compensation {
  id: string;
  node_key: string;
  tool: string;
  exec_id: string;
  compensate_fn: string | null;
  compensate_args: Record<string, unknown> | null;
  status: string;
  applied_result: Record<string, unknown> | null;
  created_at: string | null;
  applied_at: string | null;
}

export interface Compensations {
  count: number;
  compensations: Compensation[];
}

export interface Artifact {
  node_key: string;
  agent: string;
  kind: string | null;
  content: Record<string, unknown> | null;
}

export interface Artifacts {
  task_id: string;
  count: number;
  artifacts: Artifact[];
}

// --- v2.1 Build types ---
export interface BuildRecord {
  build_id: string;
  build_fingerprint: string;
  task_id: string;
  build_number: number;
  stack: string;
  status: string; // validated | failed
  assembler_version: string;
  validator_version: string;
  validator_result: { version: string; status: string; hard: number; soft: number; issues: BuildIssue[] } | null;
  file_count: number;
  created_at: string | null;
  deduped?: boolean;
}

export interface BuildIssue {
  level: string; // hard | soft
  cat: string;
  file: string;
  msg: string;
}

export interface BuildFile {
  path: string;
  sha256: string;
  size: number;
}

export interface BuildDetail extends BuildRecord {
  files: BuildFile[];
}

export interface BuildList {
  count: number;
  builds: BuildRecord[];
}

// --- v2.2 Build Run types ---
export interface BuildError {
  phase: string;
  category: string;
  file: string | null;
  message: string;
  severity: string;
}

export interface BuildRun {
  run_id: string;
  status: string; // passed | failed
  stage: string;  // install | prisma | build | done | setup
  install_ok: boolean;
  prisma_ok: boolean;
  build_ok: boolean;
  duration_s: number;
  errors: BuildError[] | null;
  log_tail: string | null;
  created_at?: string | null;
}

export interface BuildRunList {
  count: number;
  runs: BuildRun[];
}

// --- v2.3 Preview ---
export interface PreviewStatus {
  active: boolean;
  build_id: string | null;
  status: string; // starting | running | failed | stopped
  url: string | null;
  started_at: number | null;
  log_tail?: string;
  public_url?: string;
}

export interface ContextEvent {
  seq: number;
  type: string;
  node_key: string | null;
  agent: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface Events {
  count: number;
  events: ContextEvent[];
}

export interface MemoryEntry {
  task_id: string;
  goal: string;
  workflow_type: string | null;
  outcome: string;
  status: string;
  provider: string | null;
  retrieval_count: number;
  reuse_success_count: number;
  refinement_summary: unknown;
  parent_memory_ids: unknown;
}

export interface MemoryList {
  count: number;
  entries: MemoryEntry[];
}

export interface RecallHit {
  id: string;
  score: number;
  task_id?: string;
  goal?: string;
  outcome?: string;
  workflow_type?: string;
}

export interface RecallResult {
  hits: RecallHit[];
  avg_score: number;
  confidence: string;
}

export interface AdapterHealthItem {
  adapter: string;
  status: string;
  latency_ms: number | null;
  detail: string | null;
}

export interface AdapterHealth {
  adapters: AdapterHealthItem[];
}

export interface ToolCapabilities {
  tools: Record<string, Record<string, boolean>>;
}

// --- Observer types ---
export interface ObserverScores {
  scores: {
    overall_score: number;
    workflow_score: number;
    tool_score: number;
    memory_score: number;
    planner_score: number;
    retry_health: number;
  };
  kpis: Record<string, number>;
  tool_detail: Record<string, number>;
  delta: Record<string, number> | null;
  window: string;
  requested_window: string;
  samples: number;
  node_samples: number;
}

export interface ObserverCluster {
  name: string;
  count: number;
  count_last_10min: number;
  cluster_strength: number;
  severity: string;
  last_seen: string | null;
}

export interface ObserverClusters {
  clusters: ObserverCluster[];
  window: string;
}

export interface ObserverRecommendation {
  id: string;
  severity: string;
  target: string;
  message: string;
  metric_value: number;
  threshold: number;
  linked_kpis: string[];
  window: string;
}

export interface ObserverRecommendations {
  recommendations: ObserverRecommendation[];
  window: string;
}
