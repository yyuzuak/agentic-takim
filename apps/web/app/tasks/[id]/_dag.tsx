"use client";
import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { cn } from "../../lib/utils";
import { StatusBadge } from "../../components/status-badge";
import type { PlanNode, NodeDetail } from "../../lib/api";

interface DagNode {
  id: string;
  type: "agentNode";
  position: { x: number; y: number };
  data: {
    label: string;
    kind: string;
    status: string;
    tool?: string;
    onApprove?: () => void;
  };
}

interface DagEdge {
  id: string;
  source: string;
  target: string;
  type: "smoothstep";
  animated: boolean;
  style: Record<string, string>;
}

const STATUS_RING: Record<string, string> = {
  done: "ring-emerald-500/60",
  running: "ring-blue-500/60",
  in_progress: "ring-blue-500/60",
  awaiting_approval: "ring-amber-500/60",
  failed: "ring-red-500/60",
  pending: "ring-zinc-600/40",
  ready: "ring-zinc-500/40",
};

function AgentNode({ data }: NodeProps) {
  const d = data as DagNode["data"];
  const ring = STATUS_RING[d.status] ?? "ring-zinc-600/40";
  const isApproval = d.kind === "approval";
  const needsApproval = isApproval && d.status === "awaiting_approval";

  return (
    <div className={cn(
      "rounded-xl border border-border bg-card px-4 py-3 min-w-[160px] shadow-lg ring-2 transition-all",
      ring,
      needsApproval && "animate-pulse ring-amber-400/80",
    )}>
      <Handle type="target" position={Position.Top} className="!bg-border !w-2 !h-2" />
      <div className="flex flex-col gap-1.5">
        <StatusBadge status={d.status} className="text-[10px]" />
        <p className="text-sm font-medium text-foreground">{d.label}</p>
        {d.tool && <p className="text-xs text-muted-foreground">{d.tool}</p>}
        {needsApproval && d.onApprove && (
          <button
            onClick={e => { e.stopPropagation(); d.onApprove?.(); }}
            className="mt-1 rounded-md bg-amber-500 hover:bg-amber-400 text-black text-xs font-semibold px-2 py-1 transition-colors"
          >
            Onayla
          </button>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-border !w-2 !h-2" />
    </div>
  );
}

const nodeTypes = { agentNode: AgentNode };

function layoutNodes(plan: PlanNode[], nodeMap: Map<string, NodeDetail>): { nodes: DagNode[]; edges: DagEdge[] } {
  // Topological layering by BFS from roots
  const levels = new Map<string, number>();
  const deps = new Map<string, string[]>();
  plan.forEach(n => deps.set(n.key, n.depends_on ?? []));

  const visited = new Set<string>();
  const queue: string[] = plan.filter(n => !n.depends_on?.length).map(n => n.key);
  queue.forEach(k => levels.set(k, 0));

  while (queue.length) {
    const cur = queue.shift()!;
    if (visited.has(cur)) continue;
    visited.add(cur);
    const curLevel = levels.get(cur) ?? 0;
    plan.forEach(n => {
      if (n.depends_on?.includes(cur)) {
        levels.set(n.key, Math.max(levels.get(n.key) ?? 0, curLevel + 1));
        queue.push(n.key);
      }
    });
  }

  const levelGroups = new Map<number, string[]>();
  plan.forEach(n => {
    const l = levels.get(n.key) ?? 0;
    if (!levelGroups.has(l)) levelGroups.set(l, []);
    levelGroups.get(l)!.push(n.key);
  });

  const nodes: DagNode[] = plan.map(n => {
    const level = levels.get(n.key) ?? 0;
    const group = levelGroups.get(level) ?? [n.key];
    const idx = group.indexOf(n.key);
    const totalInLevel = group.length;
    const x = (idx - (totalInLevel - 1) / 2) * 220;
    const y = level * 130;
    const nd = nodeMap.get(n.key);
    const status = nd?.status ?? "pending";
    const label = n.tool ?? n.skill ?? n.key;
    const kind = n.kind ?? (n.tool ? "tool" : "reasoning");
    return {
      id: n.key,
      type: "agentNode" as const,
      position: { x, y },
      data: { label, kind, status, tool: n.tool },
    };
  });

  const edges: DagEdge[] = [];
  plan.forEach(n => {
    (n.depends_on ?? []).forEach(dep => {
      const depStatus = nodeMap.get(dep)?.status ?? "pending";
      edges.push({
        id: `${dep}-${n.key}`,
        source: dep,
        target: n.key,
        type: "smoothstep",
        animated: depStatus === "in_progress" || depStatus === "running",
        style: { stroke: depStatus === "done" ? "#10b981" : "#334155", strokeWidth: 2 },
      });
    });
  });

  return { nodes, edges };
}

interface DagProps {
  plan: PlanNode[];
  nodeMap: Map<string, NodeDetail>;
  onApproveNode: (key: string) => void;
}

export function DagView({ plan, nodeMap, onApproveNode }: DagProps) {
  const { nodes, edges } = useMemo(() => {
    const { nodes: n, edges: e } = layoutNodes(plan, nodeMap);
    // inject onApprove callback
    n.forEach(node => {
      const nd = nodeMap.get(node.id);
      if (nd?.status === "awaiting_approval") {
        node.data.onApprove = () => onApproveNode(node.id);
      }
    });
    return { nodes: n, edges: e };
  }, [plan, nodeMap, onApproveNode]);

  return (
    <div className="w-full h-full rounded-xl border border-border bg-muted overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e2535" gap={20} />
        <Controls className="!bg-card !border-border !text-foreground" />
      </ReactFlow>
    </div>
  );
}
