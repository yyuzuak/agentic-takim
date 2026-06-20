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

export interface ContextEvent {
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Events {
  count: number;
  events: ContextEvent[];
}

export interface MemoryEntry {
  id: string;
  goal: string;
  skill: string;
  reuse_success_count: number;
  created_at: string | null;
}

export interface MemoryList {
  count: number;
  entries: MemoryEntry[];
}

export interface RecallResult {
  hits: Array<{ goal: string; skill: string; score: number; reuse_success_count: number }>;
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
