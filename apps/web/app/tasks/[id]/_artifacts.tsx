"use client";
import { useState } from "react";
import { Card } from "../../components/ui/card";
import { Badge } from "../../components/ui/badge";
import { cn } from "../../lib/utils";
import { FileCode, FileText, ChevronDown, ChevronRight, Boxes } from "lucide-react";
import type { Artifact } from "../../lib/api";

function CodeBlock({ path, code }: { path: string; code: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs font-mono bg-muted/40 hover:bg-muted/70 transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <FileCode className="w-3.5 h-3.5 text-info" />
        {path}
      </button>
      {open && (
        <pre className="text-xs p-3 overflow-x-auto bg-background/50 leading-relaxed">
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}

function ArtifactBody({ content }: { content: Record<string, unknown> | null }) {
  if (!content) return <p className="text-sm text-muted-foreground">(boş)</p>;

  const files = content.files as Record<string, string> | undefined;
  const markdown = content.markdown as string | undefined;
  const summary = content.summary as string | undefined;
  const text = content.text as string | undefined;
  const decisions = content.decisions as string[] | undefined;
  const items = content.items as string[] | undefined;

  // stub fallback işareti
  const isStub = typeof text === "string" && text.includes("draft for:");

  return (
    <div className="space-y-3">
      {isStub && <Badge variant="warning">stub (LLM kapalı)</Badge>}
      {summary && <p className="text-sm">{summary}</p>}
      {markdown && (
        <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed text-foreground/90">{markdown}</pre>
      )}
      {text && !markdown && !summary && <p className="text-sm text-muted-foreground">{text}</p>}

      {decisions && decisions.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground mb-1">Kararlar</p>
          <ul className="list-disc list-inside text-sm space-y-0.5">
            {decisions.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </div>
      )}
      {items && items.length > 0 && (
        <ul className="list-disc list-inside text-sm space-y-0.5">
          {items.map((d, i) => <li key={i}>{d}</li>)}
        </ul>
      )}

      {files && Object.keys(files).length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-muted-foreground">Dosyalar ({Object.keys(files).length})</p>
          {Object.entries(files).map(([path, code]) => (
            <CodeBlock key={path} path={path} code={String(code)} />
          ))}
        </div>
      )}

      {/* tanınmayan şekil → ham JSON */}
      {!markdown && !summary && !text && !files && !decisions && !items && (
        <pre className="text-xs p-3 rounded-lg bg-muted/40 overflow-x-auto">
          {JSON.stringify(content, null, 2)}
        </pre>
      )}
    </div>
  );
}

const KIND_ICON: Record<string, typeof FileText> = {
  draft: FileText, consensus: Boxes,
};

export function ArtifactsPanel({ artifacts }: { artifacts: Artifact[] }) {
  if (artifacts.length === 0) return null;
  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold mb-3">Üretilen Çıktılar ({artifacts.length})</h2>
      <div className="flex flex-col gap-3">
        {artifacts.map((a, i) => {
          const Icon = KIND_ICON[a.kind ?? ""] ?? FileText;
          return (
            <div key={i} className="rounded-lg border border-border p-3">
              <div className="flex items-center gap-2 mb-2">
                <Icon className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm font-mono">{a.node_key}</span>
                <span className="text-xs text-muted-foreground">{a.agent}</span>
                {a.kind && <Badge variant="neutral" className={cn("ml-auto")}>{a.kind}</Badge>}
              </div>
              <ArtifactBody content={a.content} />
            </div>
          );
        })}
      </div>
    </Card>
  );
}
