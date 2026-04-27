"use client";

import { useState, useEffect } from "react";
import { knowledgeApi } from "@/services/api";
import {
  BookOpen, Code, AlertTriangle, MessageSquare, Lightbulb, Star,
  ChevronDown, ChevronUp, Trash2, RefreshCw, Filter
} from "lucide-react";
import toast from "react-hot-toast";

const KNOWLEDGE_TYPES = [
  { value: "", label: "All Types", icon: BookOpen },
  { value: "code_standard", label: "Code Standards", icon: Code },
  { value: "common_issue", label: "Common Issues", icon: AlertTriangle },
  { value: "historical_dispute", label: "Historical Disputes", icon: MessageSquare },
  { value: "project_context", label: "Project Context", icon: Star },
  { value: "best_practice", label: "Best Practices", icon: Lightbulb },
];

const TYPE_COLORS: Record<string, string> = {
  code_standard: "bg-blue-900/50 text-blue-300 border-blue-700",
  common_issue: "bg-red-900/50 text-red-300 border-red-700",
  historical_dispute: "bg-yellow-900/50 text-yellow-300 border-yellow-700",
  project_context: "bg-green-900/50 text-green-300 border-green-700",
  best_practice: "bg-purple-900/50 text-purple-300 border-purple-700",
};

interface Props {
  repoId: number;
}

export default function KnowledgePanel({ repoId }: Props) {
  const [items, setItems] = useState<any[]>([]);
  const [summary, setSummary] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    loadItems();
    loadSummary();
  }, [repoId, filter, page]);

  const loadItems = async () => {
    setLoading(true);
    try {
      const resp = await knowledgeApi.list(repoId, filter || undefined, page);
      setItems(resp.data);
    } catch {
      toast.error("Failed to load knowledge items");
    } finally {
      setLoading(false);
    }
  };

  const loadSummary = async () => {
    try {
      const resp = await knowledgeApi.summary(repoId);
      setSummary(resp.data);
    } catch {}
  };

  const handleDelete = async (itemId: number) => {
    if (!confirm("Remove this knowledge item?")) return;
    try {
      await knowledgeApi.delete(repoId, itemId);
      setItems(prev => prev.filter(i => i.id !== itemId));
      toast.success("Knowledge item removed");
    } catch {
      toast.error("Failed to remove item");
    }
  };

  return (
    <div>
      {/* Summary */}
      {summary && summary.total > 0 && (
        <div className="grid grid-cols-5 gap-3 mb-6">
          {KNOWLEDGE_TYPES.slice(1).map(({ value, label, icon: Icon }) => {
            const stat = summary.by_type?.[value];
            if (!stat) return null;
            return (
              <div
                key={value}
                onClick={() => setFilter(filter === value ? "" : value)}
                className={`cursor-pointer rounded-xl p-3 border transition-all ${
                  filter === value
                    ? TYPE_COLORS[value] || "bg-slate-800 border-slate-700"
                    : "bg-slate-900 border-slate-800 hover:border-slate-600"
                }`}
              >
                <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                  <Icon className="h-3 w-3" />
                  {label}
                </div>
                <div className="text-2xl font-bold">{stat.count}</div>
                <div className="text-xs text-slate-500">
                  {(stat.avg_confidence * 100).toFixed(0)}% confidence
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-3 mb-4">
        <Filter className="h-4 w-4 text-slate-500" />
        <div className="flex gap-2 flex-wrap">
          {KNOWLEDGE_TYPES.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => { setFilter(value); setPage(1); }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filter === value
                  ? "bg-purple-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <button onClick={loadItems} className="ml-auto p-1.5 hover:bg-slate-800 rounded-lg">
          <RefreshCw className="h-4 w-4 text-slate-500" />
        </button>
      </div>

      {/* Items */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400" />
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          <BookOpen className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg font-medium">No knowledge items yet</p>
          <p className="text-sm mt-1">Collect quality PRs to build the knowledge base</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <KnowledgeCard
              key={item.id}
              item={item}
              expanded={expandedId === item.id}
              onToggle={() => setExpandedId(expandedId === item.id ? null : item.id)}
              onDelete={() => handleDelete(item.id)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {items.length === 20 && (
        <div className="flex justify-center mt-4 gap-2">
          {page > 1 && (
            <button
              onClick={() => setPage(p => p - 1)}
              className="px-4 py-2 bg-slate-800 rounded-lg text-sm hover:bg-slate-700"
            >
              Previous
            </button>
          )}
          <button
            onClick={() => setPage(p => p + 1)}
            className="px-4 py-2 bg-slate-800 rounded-lg text-sm hover:bg-slate-700"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

function KnowledgeCard({
  item,
  expanded,
  onToggle,
  onDelete,
}: {
  item: any;
  expanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const typeColor = TYPE_COLORS[item.knowledge_type] || "bg-slate-800 text-slate-300 border-slate-700";

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
      <div
        className="flex items-start justify-between p-4 cursor-pointer hover:bg-slate-800/50"
        onClick={onToggle}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className={`text-xs px-2 py-0.5 rounded-full border ${typeColor}`}>
              {item.knowledge_type.replace("_", " ")}
            </span>
            <span className="text-xs text-slate-500">
              {(item.confidence_score * 100).toFixed(0)}% confidence
            </span>
            {item.occurrence_count > 1 && (
              <span className="text-xs text-slate-500">×{item.occurrence_count}</span>
            )}
            {item.tags?.map((tag: string) => (
              <span key={tag} className="text-xs bg-slate-800 border border-slate-700 px-2 py-0.5 rounded">
                {tag}
              </span>
            ))}
          </div>
          <h3 className="font-medium text-sm">{item.title}</h3>
          {!expanded && (
            <p className="text-xs text-slate-500 mt-1 line-clamp-2">{item.content}</p>
          )}
        </div>
        <div className="flex items-center gap-1 ml-3">
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-900/20 rounded-lg transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-slate-500" />
          ) : (
            <ChevronDown className="h-4 w-4 text-slate-500" />
          )}
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 border-t border-slate-800 pt-3 space-y-3">
          <p className="text-sm text-slate-300">{item.content}</p>

          {item.examples?.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase mb-1.5">Examples</div>
              <div className="space-y-1">
                {item.examples.map((ex: string, i: number) => (
                  <pre key={i} className="text-xs bg-slate-800 rounded-lg p-2 overflow-x-auto text-green-300">
                    {ex}
                  </pre>
                ))}
              </div>
            </div>
          )}

          {item.file_patterns?.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Applies to:</span>
              {item.file_patterns.map((p: string) => (
                <code key={p} className="text-xs bg-slate-800 px-2 py-0.5 rounded text-slate-300">
                  {p}
                </code>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
