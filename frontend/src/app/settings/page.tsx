"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/hooks/useAuth";
import {
  Settings,
  Brain,
  Box,
  ChevronLeft,
} from "lucide-react";
import LLMConfigPanel from "@/components/LLMConfigPanel";
import Sandbox3D from "@/components/Sandbox3D";

type Tab = "llm" | "sandbox";

export default function SettingsPage() {
  const router = useRouter();
  const { user, isLoading, initFromStorage, clearAuth } = useAuthStore();
  const [activeTab, setActiveTab] = useState<Tab>("llm");

  useEffect(() => {
    initFromStorage();
  }, [initFromStorage]);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/");
    }
  }, [user, isLoading, router]);

  if (isLoading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400" />
      </div>
    );
  }

  const tabs = [
    { id: "llm" as Tab, label: "LLM Configuration", icon: Brain },
    { id: "sandbox" as Tab, label: "3D Sandbox", icon: Box },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <nav className="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push("/dashboard")}
            className="flex items-center gap-1 text-slate-400 hover:text-white transition-colors text-sm"
          >
            <ChevronLeft className="h-4 w-4" />
            Back to Dashboard
          </button>
          <div className="flex items-center gap-3">
            <Settings className="h-6 w-6 text-purple-400" />
            <span className="text-xl font-bold">Settings</span>
          </div>
        </div>
      </nav>

      <div className="flex h-[calc(100vh-65px)]">
        <aside className="w-64 bg-slate-900 border-r border-slate-800 p-4">
          <div className="space-y-1">
            {tabs.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  activeTab === id
                    ? "bg-purple-900/50 text-purple-300 border border-purple-700"
                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>

          <div className="mt-8 p-4 bg-slate-800/50 rounded-lg border border-slate-700">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Quick Info
            </h3>
            <div className="space-y-2 text-xs text-slate-400">
              <p>
                <span className="text-slate-500">IDE Plugin:</span> Compatible with Copilot
                Agents
              </p>
              <p>
                <span className="text-slate-500">Cache:</span> IndexedDB for local
                code_standard
              </p>
              <p>
                <span className="text-slate-500">3D Engine:</span> Three.js with榫卯拼合
                animation
              </p>
            </div>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto">
          <div className="p-6">
            {activeTab === "llm" && <LLMConfigPanel />}

            {activeTab === "sandbox" && (
              <div className="h-[calc(100vh-120px)]">
                <div className="mb-4">
                  <h2 className="text-xl font-bold flex items-center gap-2">
                    <Box className="h-5 w-5 text-cyan-400" />
                    3D Architecture Sandbox
                  </h2>
                  <p className="text-sm text-slate-400 mt-1">
                    Visualize your knowledge base as a 3D constellation. New PRs trigger a榫卯
                    (mortise-and-tenon)拼合 animation showing how new code fits into the
                    existing architecture.
                  </p>
                </div>
                <div className="h-full bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
                  <Sandbox3D />
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
