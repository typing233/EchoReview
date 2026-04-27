"use client";

import { useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuthStore } from "@/hooks/useAuth";
import { authApi } from "@/services/api";
import toast from "react-hot-toast";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { setAuth } = useAuthStore();

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const error = searchParams.get("error");

    if (error) {
      toast.error(`OAuth error: ${error}`);
      router.push("/");
      return;
    }

    if (!code || !state) {
      router.push("/");
      return;
    }

    const storedState = sessionStorage.getItem("oauth_state");
    const platform = sessionStorage.getItem("oauth_platform") || "github";

    if (state !== storedState) {
      toast.error("Invalid OAuth state");
      router.push("/");
      return;
    }

    const handleCallback = async () => {
      try {
        const callFn =
          platform === "gitlab"
            ? authApi.gitlabCallback(code, state)
            : authApi.githubCallback(code, state);
        const resp = await callFn;
        const { access_token, user } = resp.data;
        setAuth(user, access_token);
        sessionStorage.removeItem("oauth_state");
        sessionStorage.removeItem("oauth_platform");
        toast.success(`Welcome, ${user.display_name || user.username}!`);
        router.push("/dashboard");
      } catch (err: any) {
        const msg = err.response?.data?.detail || "Authentication failed";
        toast.error(msg);
        router.push("/");
      }
    };

    handleCallback();
  }, [searchParams, router, setAuth]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-400 mx-auto mb-4" />
        <p className="text-slate-300 text-lg">Completing authentication...</p>
      </div>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-400" />
      </div>
    }>
      <CallbackHandler />
    </Suspense>
  );
}
