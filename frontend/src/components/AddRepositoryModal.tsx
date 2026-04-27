"use client";

import { useState, useEffect } from "react";
import { repoApi } from "@/services/api";
import { Github, Gitlab, X, Search, Plus } from "lucide-react";
import toast from "react-hot-toast";

interface Props {
  onClose: () => void;
  onAdded: (repo: any) => void;
  userPlatforms: string[];
}

export default function AddRepositoryModal({ onClose, onAdded, userPlatforms }: Props) {
  const [platform, setPlatform] = useState<string>(userPlatforms[0] || "github");
  const [availableRepos, setAvailableRepos] = useState<any[]>([]);
  const [filtered, setFiltered] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);

  useEffect(() => {
    loadRepos();
  }, [platform]);

  useEffect(() => {
    if (!search) {
      setFiltered(availableRepos);
    } else {
      setFiltered(
        availableRepos.filter((r) =>
          r.full_name.toLowerCase().includes(search.toLowerCase())
        )
      );
    }
  }, [search, availableRepos]);

  const loadRepos = async () => {
    setLoading(true);
    try {
      const resp = await repoApi.listAvailable(platform);
      setAvailableRepos(resp.data);
      setFiltered(resp.data);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to load repositories");
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async (repo: any) => {
    setAdding(repo.platform_repo_id);
    try {
      const result = await repoApi.add({
        platform_repo_id: repo.platform_repo_id,
        full_name: repo.full_name,
        name: repo.name,
        description: repo.description,
        default_branch: repo.default_branch,
        platform: repo.platform,
      });
      toast.success(`${repo.full_name} added!`);
      onAdded(result.data);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to add repository");
    } finally {
      setAdding(null);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 rounded-2xl border border-slate-700 w-full max-w-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-800">
          <h2 className="text-lg font-semibold">Add Repository</h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-800 rounded-lg">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Platform switcher */}
        {userPlatforms.length > 1 && (
          <div className="p-4 border-b border-slate-800 flex gap-2">
            {userPlatforms.map((p) => (
              <button
                key={p}
                onClick={() => setPlatform(p)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
                  platform === p
                    ? "bg-purple-600 text-white"
                    : "bg-slate-800 text-slate-400 hover:text-white"
                }`}
              >
                {p === "github" ? <Github className="h-4 w-4" /> : <Gitlab className="h-4 w-4" />}
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>
        )}

        {/* Search */}
        <div className="p-4 border-b border-slate-800">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search repositories..."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-4 py-2.5 text-sm placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-600"
            />
          </div>
        </div>

        {/* Repo list */}
        <div className="max-h-80 overflow-y-auto p-4 space-y-2">
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-400" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-center text-slate-500 py-8 text-sm">No repositories found</p>
          ) : (
            filtered.map((repo) => (
              <div
                key={repo.platform_repo_id}
                className="flex items-center justify-between p-3 bg-slate-800 rounded-xl hover:bg-slate-750 group"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    {repo.platform === "github" ? (
                      <Github className="h-4 w-4 text-slate-400 flex-shrink-0" />
                    ) : (
                      <Gitlab className="h-4 w-4 text-orange-400 flex-shrink-0" />
                    )}
                    <span className="text-sm font-medium truncate">{repo.full_name}</span>
                    {repo.private && (
                      <span className="text-xs bg-slate-700 px-1.5 py-0.5 rounded text-slate-400">
                        private
                      </span>
                    )}
                  </div>
                  {repo.description && (
                    <p className="text-xs text-slate-500 mt-1 truncate">{repo.description}</p>
                  )}
                </div>
                <button
                  onClick={() => handleAdd(repo)}
                  disabled={adding === repo.platform_repo_id}
                  className="flex items-center gap-1.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ml-3 flex-shrink-0"
                >
                  {adding === repo.platform_repo_id ? (
                    <div className="animate-spin rounded-full h-3 w-3 border-b border-white" />
                  ) : (
                    <Plus className="h-3 w-3" />
                  )}
                  Add
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
