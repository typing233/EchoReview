"use client";

import { useState, useEffect } from "react";
import { prApi } from "@/services/api";
import {
  GitPullRequest, GitMerge, Clock, MessageSquare, Play, ChevronDown, ChevronUp,
  ExternalLink, Star, AlertCircle, CheckCircle, Info, AlertTriangle
} from "lucide-react";
import toast from "react-hot-toast";
import { formatDistanceToNow } from "date-fns";

interface Props {
  repoId: number;
}

export default function PRListPanel({ repoId }: Props) {
  const [prs, setPrs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [qualityOnly, setQualityOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [selectedPR, setSelectedPR] = useState<any | null>(null);
  const [reviews, setReviews] = useState<any[]>([]);
  const [triggeringReview, setTriggeringReview] = useState(false);

  useEffect(() => {
    loadPRs();
  }, [repoId, qualityOnly, page]);

  const loadPRs = async () => {
    setLoading(true);
    try {
      const resp = await prApi.list(repoId, qualityOnly, page);
      setPrs(resp.data);
    } catch {
      toast.error("Failed to load PRs");
    } finally {
      setLoading(false);
    }
  };

  const loadPRDetail = async (pr: any) => {
    try {
      const [prResp, reviewsResp] = await Promise.all([
        prApi.get(repoId, pr.platform_pr_number),
        prApi.listReviews(repoId, pr.platform_pr_number),
      ]);
      setSelectedPR(prResp.data);
      setReviews(reviewsResp.data);
    } catch {
      toast.error("Failed to load PR details");
    }
  };

  const handleTriggerReview = async () => {
    if (!selectedPR) return;
    setTriggeringReview(true);
    try {
      const resp = await prApi.triggerReview(repoId, selectedPR.platform_pr_number);
      setReviews(prev => [resp.data, ...prev]);
      toast.success("AI review started!");
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to trigger review");
    } finally {
      setTriggeringReview(false);
    }
  };

  return (
    <div className="flex gap-4 h-full">
      {/* PR List */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={() => { setQualityOnly(false); setPage(1); }}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${!qualityOnly ? "bg-purple-600 text-white" : "bg-slate-800 text-slate-400 hover:text-white"}`}
          >
            All PRs
          </button>
          <button
            onClick={() => { setQualityOnly(true); setPage(1); }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${qualityOnly ? "bg-yellow-600 text-white" : "bg-slate-800 text-slate-400 hover:text-white"}`}
          >
            <Star className="h-3.5 w-3.5" />
            Quality PRs
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400" />
          </div>
        ) : prs.length === 0 ? (
          <div className="text-center py-16 text-slate-500">
            <GitPullRequest className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p>No PRs collected yet.</p>
            <p className="text-sm">Click &quot;Collect PRs&quot; to import data.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {prs.map((pr) => (
              <div
                key={pr.id}
                onClick={() => loadPRDetail(pr)}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  selectedPR?.id === pr.id
                    ? "bg-purple-900/30 border-purple-700"
                    : "bg-slate-900 border-slate-800 hover:border-slate-600"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 mt-0.5">
                    {pr.status === "merged" ? (
                      <GitMerge className="h-4 w-4 text-purple-400" />
                    ) : (
                      <GitPullRequest className="h-4 w-4 text-green-400" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500">#{pr.platform_pr_number}</span>
                      {pr.is_quality_pr && (
                        <Star className="h-3 w-3 text-yellow-400" />
                      )}
                      {pr.quality_score && (
                        <span className="text-xs text-slate-600">
                          {(pr.quality_score * 100).toFixed(0)}% quality
                        </span>
                      )}
                    </div>
                    <p className="text-sm font-medium mt-0.5 truncate">{pr.title}</p>
                    <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-500">
                      <span className="flex items-center gap-1">
                        <MessageSquare className="h-3 w-3" />
                        {pr.comment_count} comments
                      </span>
                      <span className="text-green-400">+{pr.additions}</span>
                      <span className="text-red-400">-{pr.deletions}</span>
                      {pr.platform_created_at && (
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatDistanceToNow(new Date(pr.platform_created_at), { addSuffix: true })}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {prs.length === 20 && (
          <div className="flex justify-center mt-4 gap-2">
            {page > 1 && (
              <button onClick={() => setPage(p => p - 1)} className="px-4 py-2 bg-slate-800 rounded-lg text-sm">
                Previous
              </button>
            )}
            <button onClick={() => setPage(p => p + 1)} className="px-4 py-2 bg-slate-800 rounded-lg text-sm">
              Next
            </button>
          </div>
        )}
      </div>

      {/* PR Detail Panel */}
      {selectedPR && (
        <div className="w-96 flex-shrink-0 bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-800">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-sm">{selectedPR.title}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-slate-500">by {selectedPR.author}</span>
                  {selectedPR.pr_url && (
                    <a href={selectedPR.pr_url} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-0.5">
                      <ExternalLink className="h-3 w-3" />
                      View
                    </a>
                  )}
                </div>
              </div>
              <button
                onClick={handleTriggerReview}
                disabled={triggeringReview}
                className="flex items-center gap-1.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg text-xs font-medium"
              >
                {triggeringReview ? (
                  <div className="animate-spin rounded-full h-3 w-3 border-b border-white" />
                ) : (
                  <Play className="h-3 w-3" />
                )}
                Review
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {/* AI Review Sessions */}
            {reviews.length > 0 && (
              <div className="p-4 border-b border-slate-800">
                <h4 className="text-xs font-semibold text-slate-400 uppercase mb-3">AI Reviews</h4>
                <div className="space-y-3">
                  {reviews.map((session) => (
                    <ReviewSessionCard key={session.id} session={session} />
                  ))}
                </div>
              </div>
            )}

            {/* Review comments */}
            {selectedPR.review_comments?.length > 0 && (
              <div className="p-4">
                <h4 className="text-xs font-semibold text-slate-400 uppercase mb-3">
                  Human Review Comments ({selectedPR.review_comments.length})
                </h4>
                <div className="space-y-2">
                  {selectedPR.review_comments.slice(0, 10).map((c: any) => (
                    <div key={c.id} className="bg-slate-800 rounded-lg p-3 text-xs">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium">{c.author}</span>
                        {c.file_path && (
                          <code className="text-slate-500 truncate max-w-[140px]">{c.file_path}:{c.line_number}</code>
                        )}
                      </div>
                      <p className="text-slate-300">{c.body}</p>
                      {c.is_addressed !== null && (
                        <div className={`mt-1.5 flex items-center gap-1 ${c.is_addressed ? "text-green-400" : "text-red-400"}`}>
                          {c.is_addressed ? <CheckCircle className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
                          {c.is_addressed ? "Addressed" : "Not addressed"}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewSessionCard({ session }: { session: any }) {
  const [expanded, setExpanded] = useState(false);

  const statusColors: Record<string, string> = {
    completed: "text-green-400",
    failed: "text-red-400",
    in_progress: "text-yellow-400",
    pending: "text-slate-400",
  };

  const assessmentIcons: Record<string, any> = {
    LGTM: CheckCircle,
    NEEDS_CHANGES: AlertCircle,
    APPROVE_WITH_SUGGESTIONS: AlertTriangle,
  };

  const AssessIcon = assessmentIcons[session.overall_assessment] || Info;

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700">
      <div className="p-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`text-xs font-medium ${statusColors[session.status] || "text-slate-400"}`}>
              {session.status}
            </span>
            {session.overall_assessment && (
              <div className="flex items-center gap-1 text-xs text-slate-400">
                <AssessIcon className="h-3 w-3" />
                {session.overall_assessment}
              </div>
            )}
          </div>
          <div className="flex items-center gap-1">
            <span className="text-xs text-slate-500">
              {session.ai_comments?.length || 0} comments
            </span>
            {expanded ? <ChevronUp className="h-3 w-3 text-slate-500" /> : <ChevronDown className="h-3 w-3 text-slate-500" />}
          </div>
        </div>
        {session.summary && (
          <p className="text-xs text-slate-400 mt-1.5 line-clamp-2">{session.summary}</p>
        )}
      </div>

      {expanded && session.ai_comments?.length > 0 && (
        <div className="border-t border-slate-700 p-3 space-y-2">
          {session.ai_comments.map((c: any, i: number) => {
            const severityColors: Record<string, string> = {
              error: "border-l-red-500",
              warning: "border-l-yellow-500",
              suggestion: "border-l-blue-500",
              info: "border-l-slate-500",
            };
            return (
              <div key={i} className={`bg-slate-900 rounded-lg p-2.5 border-l-2 ${severityColors[c.severity] || "border-l-slate-500"}`}>
                {c.file_path && (
                  <code className="text-xs text-slate-500 block mb-1">{c.file_path}:{c.line_number}</code>
                )}
                <p className="text-xs text-slate-300">{c.body}</p>
                {c.context_explanation && (
                  <p className="text-xs text-slate-500 mt-1 italic">{c.context_explanation}</p>
                )}
                {c.suggested_fix && (
                  <pre className="text-xs bg-slate-800 rounded p-1.5 mt-1.5 overflow-x-auto text-green-300">
                    {c.suggested_fix}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
