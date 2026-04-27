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
