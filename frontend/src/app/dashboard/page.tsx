"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/hooks/useAuth";
import { repoApi, knowledgeApi } from "@/services/api";
import {
  GitPullRequest,
  BookOpen,
  Plus,
  Webhook,
  RefreshCw,
  Trash2,
  LogOut,
  Github,
  Gitlab,
  Brain,
  ChevronRight,
  BarChart3,
  Clock,
} from "lucide-react";
import toast from "react-hot-toast";
import { formatDistanceToNow } from "date-fns";
import AddRepositoryModal from "@/components/AddRepositoryModal";
import KnowledgePanel from "@/components/KnowledgePanel";
import PRListPanel from "@/components/PRListPanel";

type Tab = "repositories" | "knowledge" | "prs";

export default function DashboardPage() {
  const router = useRouter();
  const { user, isLoading, initFromStorage, clearAuth } = useAuthStore();
  const [repositories, setRepositories] = useState<any[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<any | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("repositories");
  const [showAddModal, setShowAddModal] = useState(false);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [collectingRepoId, setCollectingRepoId] = useState<number | null>(null);

  useEffect(() => {
    initFromStorage();
  }, [initFromStorage]);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/");
    }
  }, [user, isLoading, router]);

  useEffect(() => {
    if (user) {
      loadRepositories();
    }
  }, [user]);

  const loadRepositories = async () => {
    setLoadingRepos(true);
    try {
      const resp = await repoApi.list();
      setRepositories(resp.data);
    } catch {
      toast.error("Failed to load repositories");
    } finally {
      setLoadingRepos(false);
    }
  };

  const handleCollect = async (repo: any) => {
    setCollectingRepoId(repo.id);
    try {
      await repoApi.collect(repo.id, { days: 90, min_review_comments: 2, max_prs: 100 });
      toast.success("Collection started! This may take a few minutes.");
      setTimeout(loadRepositories, 3000);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Collection failed");
    } finally {
      setCollectingRepoId(null);
    }
  };

  const handleWebhook = async (repo: any) => {
    try {
      if (repo.webhook_active) {
        await repoApi.removeWebhook(repo.id);
        toast.success("Webhook removed");
      } else {
        await repoApi.setupWebhook(repo.id);
        toast.success("Webhook registered! New PRs will be auto-reviewed.");
      }
      await loadRepositories();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Webhook operation failed");
    }
  };

  const handleDelete = async (repo: any) => {
    if (!confirm(`Remove ${repo.full_name} from EchoReview?`)) return;
    try {
      await repoApi.delete(repo.id);
      setRepositories(repos => repos.filter(r => r.id !== repo.id));
      if (selectedRepo?.id === repo.id) setSelectedRepo(null);
      toast.success("Repository removed");
    } catch {
      toast.error("Failed to remove repository");
    }
  };

  const handleLogout = () => {
    clearAuth();
    router.push("/");
  };

  if (isLoading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Top Nav */}
      <nav className="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="h-7 w-7 text-purple-400" />
          <span className="text-xl font-bold">EchoReview</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            {user.avatar_url && (
              <img src={user.avatar_url} alt="avatar" className="w-8 h-8 rounded-full" />
            )}
            <span className="text-sm text-slate-300">{user.display_name || user.username}</span>
            <div className="flex gap-1">
              {user.platforms?.includes("github") && (
                <Github className="h-4 w-4 text-slate-400" />
              )}
              {user.platforms?.includes("gitlab") && (
                <Gitlab className="h-4 w-4 text-orange-400" />
              )}
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </div>
      </nav>

      <div className="flex h-[calc(100vh-65px)]">
        {/* Sidebar */}
        <aside className="w-72 bg-slate-900 border-r border-slate-800 flex flex-col">
          <div className="p-4 flex-1 overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
                Repositories
              </h2>
              <button
                onClick={() => setShowAddModal(true)}
                className="p-1.5 hover:bg-slate-800 rounded-lg transition-colors"
                title="Add repository"
              >
                <Plus className="h-4 w-4 text-slate-400" />
              </button>
            </div>

            {loadingRepos ? (
              <div className="flex justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-400" />
              </div>
            ) : repositories.length === 0 ? (
              <div className="text-center py-8 text-slate-500 text-sm">
                <GitPullRequest className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No repositories yet.</p>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="mt-2 text-purple-400 hover:text-purple-300"
                >
                  Add one
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {repositories.map((repo) => (
                  <div
                    key={repo.id}
                    onClick={() => { setSelectedRepo(repo); setActiveTab("prs"); }}
                    className={`p-3 rounded-lg cursor-pointer transition-all group ${
                      selectedRepo?.id === repo.id
                        ? "bg-purple-900/50 border border-purple-700"
                        : "hover:bg-slate-800 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        {repo.platform === "github" ? (
                          <Github className="h-4 w-4 text-slate-400 flex-shrink-0" />
                        ) : (
                          <Gitlab className="h-4 w-4 text-orange-400 flex-shrink-0" />
                        )}
                        <span className="text-sm font-medium truncate">{repo.name}</span>
                      </div>
                      <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-slate-400 flex-shrink-0" />
                    </div>
                    <div className="mt-1.5 flex items-center gap-3 text-xs text-slate-500">
                      <span className="flex items-center gap-1">
                        <GitPullRequest className="h-3 w-3" />
                        {repo.pr_count || 0} PRs
                      </span>
                      <span className="flex items-center gap-1">
                        <BookOpen className="h-3 w-3" />
                        {repo.quality_pr_count || 0} quality
                      </span>
                      {repo.webhook_active && (
                        <span className="flex items-center gap-1 text-green-400">
                          <Webhook className="h-3 w-3" />
                          live
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto">
          {!selectedRepo ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center text-slate-500">
                <Brain className="h-16 w-16 mx-auto mb-4 opacity-30" />
                <h3 className="text-xl font-semibold mb-2">Select a repository</h3>
                <p className="text-sm">Choose a repository from the sidebar to get started</p>
              </div>
            </div>
          ) : (
            <div className="p-6">
              {/* Repo Header */}
              <div className="mb-6">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      {selectedRepo.platform === "github" ? (
                        <Github className="h-5 w-5 text-slate-400" />
                      ) : (
                        <Gitlab className="h-5 w-5 text-orange-400" />
                      )}
                      <h1 className="text-2xl font-bold">{selectedRepo.full_name}</h1>
                    </div>
                    {selectedRepo.description && (
                      <p className="text-slate-400 text-sm">{selectedRepo.description}</p>
                    )}
                    {selectedRepo.last_collected_at && (
                      <p className="text-slate-500 text-xs mt-1 flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Last collected{" "}
                        {formatDistanceToNow(new Date(selectedRepo.last_collected_at), { addSuffix: true })}
                      </p>
                    )}
                  </div>

                  {/* Action buttons */}
                  <div className="flex items-center gap-2 flex-wrap justify-end">
                    <button
                      onClick={() => handleCollect(selectedRepo)}
                      disabled={collectingRepoId === selectedRepo.id}
                      className="flex items-center gap-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                    >
                      <RefreshCw className={`h-4 w-4 ${collectingRepoId === selectedRepo.id ? "animate-spin" : ""}`} />
                      {collectingRepoId === selectedRepo.id ? "Collecting..." : "Collect PRs"}
                    </button>
                    <button
                      onClick={() => handleWebhook(selectedRepo)}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                        selectedRepo.webhook_active
                          ? "bg-green-900/50 text-green-300 hover:bg-red-900/50 hover:text-red-300 border border-green-700 hover:border-red-700"
                          : "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                      }`}
                    >
                      <Webhook className="h-4 w-4" />
                      {selectedRepo.webhook_active ? "Webhook: ON" : "Setup Webhook"}
                    </button>
                    <button
                      onClick={() => handleDelete(selectedRepo)}
                      className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-900/20 rounded-lg transition-colors"
                      title="Remove repository"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-4 gap-4 mt-4">
                  {[
                    { label: "Total PRs", value: selectedRepo.pr_count || 0, icon: GitPullRequest },
                    { label: "Quality PRs", value: selectedRepo.quality_pr_count || 0, icon: BarChart3 },
                    { label: "Platform", value: selectedRepo.platform, icon: selectedRepo.platform === "github" ? Github : Gitlab },
                    { label: "Branch", value: selectedRepo.default_branch, icon: GitPullRequest },
                  ].map(({ label, value, icon: Icon }) => (
                    <div key={label} className="bg-slate-900 rounded-xl p-4 border border-slate-800">
                      <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
                        <Icon className="h-3.5 w-3.5" />
                        {label}
                      </div>
                      <div className="text-xl font-semibold">{value}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Tabs */}
              <div className="flex gap-1 mb-6 bg-slate-900 rounded-xl p-1 w-fit border border-slate-800">
                {([
                  { id: "prs", label: "Pull Requests", icon: GitPullRequest },
                  { id: "knowledge", label: "Knowledge Base", icon: BookOpen },
                ] as const).map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => setActiveTab(id)}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      activeTab === id
                        ? "bg-purple-600 text-white"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              {activeTab === "prs" && <PRListPanel repoId={selectedRepo.id} />}
              {activeTab === "knowledge" && <KnowledgePanel repoId={selectedRepo.id} />}
            </div>
          )}
        </main>
      </div>

      {showAddModal && (
        <AddRepositoryModal
          onClose={() => setShowAddModal(false)}
          onAdded={(repo) => {
            setRepositories(prev => [...prev, repo]);
            setSelectedRepo(repo);
            setShowAddModal(false);
          }}
          userPlatforms={user.platforms}
        />
      )}
    </div>
  );
}
