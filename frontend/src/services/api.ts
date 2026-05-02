import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: { "Content-Type": "application/json" },
});

// Attach token from localStorage
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Auto-redirect on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");
      window.location.href = "/";
    }
    return Promise.reject(error);
  }
);

// Auth
export const authApi = {
  getGitHubUrl: () => api.get("/auth/github/url"),
  getGitLabUrl: () => api.get("/auth/gitlab/url"),
  githubCallback: (code: string, state: string) =>
    api.get(`/auth/github/callback?code=${code}&state=${state}`),
  gitlabCallback: (code: string, state: string) =>
    api.get(`/auth/gitlab/callback?code=${code}&state=${state}`),
  getMe: () => api.get("/auth/me"),
};

// Repositories
export const repoApi = {
  listAvailable: (platform: string) =>
    api.get(`/repositories/available?platform=${platform}`),
  list: () => api.get("/repositories"),
  get: (id: number) => api.get(`/repositories/${id}`),
  add: (data: any) => api.post("/repositories", data),
  delete: (id: number) => api.delete(`/repositories/${id}`),
  collect: (id: number, options?: any) =>
    api.post(`/repositories/${id}/collect`, options || {}),
  setupWebhook: (id: number) => api.post(`/repositories/${id}/webhook`),
  removeWebhook: (id: number) => api.delete(`/repositories/${id}/webhook`),
};

// PRs
export const prApi = {
  list: (repoId: number, qualityOnly?: boolean, page?: number) =>
    api.get(`/prs/${repoId}?quality_only=${qualityOnly || false}&page=${page || 1}`),
  get: (repoId: number, prNumber: number) =>
    api.get(`/prs/${repoId}/${prNumber}`),
  triggerReview: (repoId: number, prNumber: number) =>
    api.post(`/prs/${repoId}/${prNumber}/review`),
  listReviews: (repoId: number, prNumber: number) =>
    api.get(`/prs/${repoId}/${prNumber}/reviews`),
};

// Knowledge
export const knowledgeApi = {
  list: (repoId: number, type?: string, page?: number) =>
    api.get(`/knowledge/${repoId}?${type ? `knowledge_type=${type}&` : ""}page=${page || 1}`),
  get: (repoId: number, itemId: number) =>
    api.get(`/knowledge/${repoId}/${itemId}`),
  delete: (repoId: number, itemId: number) =>
    api.delete(`/knowledge/${repoId}/${itemId}`),
  summary: (repoId: number) =>
    api.get(`/knowledge/${repoId}/stats/summary`),
};

// IDE Plugin API
export const ideApi = {
  getLLMConfig: () => api.get("/ide/llm/config"),
  updateLLMConfig: (data: {
    base_url?: string;
    api_key?: string;
    model_name?: string;
    provider?: string;
  }) => api.put("/ide/llm/config", data),
  testLLMConnection: (data: {
    base_url: string;
    api_key: string;
    model_name: string;
    provider?: string;
  }) => api.post("/ide/llm/test", data),
  syncCodeStandards: (repoId: number, lastSyncAt?: string) =>
    api.get(`/ide/sync/code_standards?repo_id=${repoId}${lastSyncAt ? `&last_sync_at=${encodeURIComponent(lastSyncAt)}` : ""}`),
  getHighFrequencyStandards: (repoId: number, limit?: number) =>
    api.get(`/ide/sync/high_frequency?repo_id=${repoId}&limit=${limit || 20}`),
  runPreReview: (data: {
    repo_id: number;
    files: Array<{
      filename: string;
      path?: string;
      additions?: number;
      deletions?: number;
      diff?: string;
    }>;
    diff_content?: string;
    branch?: string;
  }) => api.post("/ide/pre-review", data),
};

// Dialectic Logic Detection
export const dialecticApi = {
  runCheck: (repoId: number, prNumber: number) =>
    api.get(`/dialectic/check/${repoId}/${prNumber}`),
};
