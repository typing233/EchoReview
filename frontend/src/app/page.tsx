"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/hooks/useAuth";
import { Github, Gitlab, Brain, GitPullRequest, BookOpen, Zap } from "lucide-react";
import { authApi } from "@/services/api";
import toast from "react-hot-toast";

export default function HomePage() {
  const router = useRouter();
  const { user, isLoading, initFromStorage } = useAuthStore();

  useEffect(() => {
    initFromStorage();
  }, [initFromStorage]);

  useEffect(() => {
    if (!isLoading && user) {
      router.push("/dashboard");
    }
  }, [user, isLoading, router]);

  const handleGitHubLogin = async () => {
    try {
      const resp = await authApi.getGitHubUrl();
      const { url, state } = resp.data;
      if (typeof window !== "undefined") {
        sessionStorage.setItem("oauth_state", state);
        sessionStorage.setItem("oauth_platform", "github");
      }
      window.location.href = url;
    } catch {
      toast.error("Failed to get GitHub OAuth URL");
    }
  };

  const handleGitLabLogin = async () => {
    try {
      const resp = await authApi.getGitLabUrl();
      const { url, state } = resp.data;
      if (typeof window !== "undefined") {
        sessionStorage.setItem("oauth_state", state);
        sessionStorage.setItem("oauth_platform", "gitlab");
      }
      window.location.href = url;
    } catch {
      toast.error("Failed to get GitLab OAuth URL");
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Hero */}
      <div className="container mx-auto px-4 py-16">
        <div className="text-center mb-16">
          <div className="flex items-center justify-center gap-3 mb-6">
            <Brain className="h-12 w-12 text-purple-400" />
            <h1 className="text-5xl font-bold text-white">EchoReview</h1>
          </div>
          <p className="text-xl text-slate-300 max-w-2xl mx-auto mb-8">
            AI-powered code review that learns your team&apos;s standards, captures knowledge
            from past discussions, and delivers expert-level feedback on every PR.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={handleGitHubLogin}
              className="flex items-center gap-3 bg-gray-900 hover:bg-gray-800 text-white px-8 py-4 rounded-xl font-semibold transition-all border border-gray-700 hover:border-gray-600"
            >
              <Github className="h-5 w-5" />
              Connect with GitHub
            </button>
            <button
              onClick={handleGitLabLogin}
              className="flex items-center gap-3 bg-orange-600 hover:bg-orange-500 text-white px-8 py-4 rounded-xl font-semibold transition-all"
            >
              <Gitlab className="h-5 w-5" />
              Connect with GitLab
            </button>
          </div>
        </div>

        {/* Features */}
        <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          <FeatureCard
            icon={<GitPullRequest className="h-8 w-8 text-blue-400" />}
            title="Smart PR Collection"
            description="Automatically pulls your team's best PRs from GitHub/GitLab, analyzes diffs, review comments, and tracks how feedback was adopted."
          />
          <FeatureCard
            icon={<BookOpen className="h-8 w-8 text-green-400" />}
            title="Team Knowledge Base"
            description="Distills your historical reviews into structured knowledge: code standards, common issues, historical disputes, and project context."
          />
          <FeatureCard
            icon={<Zap className="h-8 w-8 text-yellow-400" />}
            title="Automated AI Review"
            description="Webhook-triggered reviews simulate your senior engineers, delivering line-level comments with historical context and fix suggestions."
          />
        </div>

        {/* How it works */}
        <div className="mt-20 text-center">
          <h2 className="text-3xl font-bold text-white mb-10">How It Works</h2>
          <div className="grid md:grid-cols-4 gap-6 max-w-5xl mx-auto">
            {[
              { step: "1", title: "Connect", desc: "Link your GitHub or GitLab account with OAuth" },
              { step: "2", title: "Collect", desc: "Import quality PRs from the past 90 days" },
              { step: "3", title: "Learn", desc: "LLM extracts team standards and review patterns" },
              { step: "4", title: "Review", desc: "New PRs get expert AI reviews via webhook" },
            ].map(({ step, title, desc }) => (
              <div key={step} className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
                <div className="text-4xl font-bold text-purple-400 mb-3">{step}</div>
                <h3 className="text-lg font-semibold text-white mb-2">{title}</h3>
                <p className="text-slate-400 text-sm">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl p-6">
      <div className="mb-4">{icon}</div>
      <h3 className="text-xl font-semibold text-white mb-3">{title}</h3>
      <p className="text-slate-400">{description}</p>
    </div>
  );
}
