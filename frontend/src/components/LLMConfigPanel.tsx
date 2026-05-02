"use client";

import { useState, useEffect } from "react";
import { ideApi } from "@/services/api";
import {
  Settings,
  TestTube,
  Check,
  X,
  Loader2,
  Save,
  Key,
  Globe,
  Cpu,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import toast from "react-hot-toast";

interface LLMConfig {
  base_url: string | null;
  model_name: string;
  provider: string;
  has_api_key: boolean;
}

interface TestResult {
  status: string;
  connected: boolean;
  response?: string;
  latency_ms?: number;
  error?: string;
  details?: string;
}

const PROVIDERS = [
  { value: "openai", label: "OpenAI Compatible", icon: Globe },
  { value: "anthropic", label: "Anthropic Claude", icon: Cpu },
];

const DEFAULT_BASE_URLS: Record<string, string> = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com",
};

const SUGGESTED_MODELS: Record<string, string[]> = {
  openai: [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
    "gpt-4",
  ],
  anthropic: [
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
  ],
};

export default function LLMConfigPanel() {
  const [config, setConfig] = useState<LLMConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  const [formData, setFormData] = useState({
    base_url: "",
    api_key: "",
    model_name: "",
    provider: "openai",
  });
  const [showApiKey, setShowApiKey] = useState(false);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const resp = await ideApi.getLLMConfig();
      const data = resp.data;
      setConfig(data);
      setFormData({
        base_url: data.base_url || DEFAULT_BASE_URLS[data.provider] || "",
        api_key: "",
        model_name: data.model_name || "gpt-4o",
        provider: data.provider || "openai",
      });
    } catch (err: any) {
      console.error("Failed to load LLM config:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleProviderChange = (provider: string) => {
    setFormData((prev) => ({
      ...prev,
      provider,
      base_url: DEFAULT_BASE_URLS[provider] || "",
      model_name: SUGGESTED_MODELS[provider]?.[0] || "",
    }));
  };

  const handleSave = async () => {
    if (!formData.base_url) {
      toast.error("Base URL is required");
      return;
    }

    setSaving(true);
    try {
      const updateData: {
        base_url?: string;
        api_key?: string;
        model_name?: string;
        provider?: string;
      } = {
        base_url: formData.base_url,
        model_name: formData.model_name,
        provider: formData.provider,
      };

      if (formData.api_key) {
        updateData.api_key = formData.api_key;
      }

      const resp = await ideApi.updateLLMConfig(updateData);
      setConfig(resp.data.config);
      toast.success("Configuration saved successfully");

      if (formData.api_key) {
        setFormData((prev) => ({ ...prev, api_key: "" }));
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!formData.base_url || !formData.api_key) {
      toast.error("Base URL and API Key are required for testing");
      return;
    }

    setTesting(true);
    setTestResult(null);

    try {
      const resp = await ideApi.testLLMConnection({
        base_url: formData.base_url,
        api_key: formData.api_key,
        model_name: formData.model_name,
        provider: formData.provider,
      });
      setTestResult(resp.data);

      if (resp.data.connected) {
        toast.success(
          `Connection successful! Latency: ${resp.data.latency_ms?.toFixed(0) || "N/A"}ms`
        );
      } else {
        toast.error(`Connection failed: ${resp.data.error || "Unknown error"}`);
      }
    } catch (err: any) {
      const errorData = {
        status: "error",
        connected: false,
        error: err.response?.data?.detail || err.message || "Connection failed",
        details: err.response?.data?.details || "",
      };
      setTestResult(errorData);
      toast.error(`Connection failed: ${errorData.error}`);
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <Settings className="h-6 w-6 text-purple-400" />
        <h2 className="text-xl font-bold">LLM Configuration</h2>
      </div>

      <div className="bg-slate-900 rounded-xl border border-slate-800 p-6">
        <div className="text-sm text-slate-400 mb-6">
          Configure your LLM provider settings for pre-review and IDE plugin integration.
          These settings allow the system to use compatible OpenAI or Anthropic APIs.
        </div>

        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              <Cpu className="h-4 w-4 inline mr-2" />
              Provider
            </label>
            <div className="flex gap-3">
              {PROVIDERS.map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  onClick={() => handleProviderChange(value)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    formData.provider === value
                      ? "bg-purple-600 text-white"
                      : "bg-slate-800 text-slate-400 hover:text-white"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              <Globe className="h-4 w-4 inline mr-2" />
              Base URL
              <span className="text-slate-500 font-normal ml-2">
                (e.g., https://api.openai.com/v1)
              </span>
            </label>
            <input
              type="url"
              value={formData.base_url}
              onChange={(e) =>
                setFormData((prev) => ({ ...prev, base_url: e.target.value }))
              }
              placeholder={DEFAULT_BASE_URLS[formData.provider] || "https://..."}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              <Key className="h-4 w-4 inline mr-2" />
              API Key
              {config?.has_api_key && (
                <span className="text-green-400 font-normal ml-2">
                  ✓ Previously configured
                </span>
              )}
            </label>
            <div className="relative">
              <input
                type={showApiKey ? "text" : "password"}
                value={formData.api_key}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, api_key: e.target.value }))
                }
                placeholder={
                  config?.has_api_key
                    ? "Enter new key to update, or leave blank to keep current"
                    : "sk-..."
                }
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 pr-24 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white text-xs"
              >
                {showApiKey ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Model Name
            </label>
            <div className="space-y-2">
              <input
                type="text"
                value={formData.model_name}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, model_name: e.target.value }))
                }
                placeholder="e.g., gpt-4o"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
              {SUGGESTED_MODELS[formData.provider] && (
                <div className="flex flex-wrap gap-2">
                  <span className="text-xs text-slate-500 self-center">Suggestions:</span>
                  {SUGGESTED_MODELS[formData.provider].map((model) => (
                    <button
                      key={model}
                      onClick={() =>
                        setFormData((prev) => ({ ...prev, model_name: model }))
                      }
                      className={`text-xs px-2 py-1 rounded ${
                        formData.model_name === model
                          ? "bg-purple-600 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-white"
                      }`}
                    >
                      {model}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3 pt-4 border-t border-slate-800">
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white px-6 py-2.5 rounded-lg text-sm font-medium transition-colors"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save Configuration
            </button>

            <button
              onClick={handleTest}
              disabled={testing || !formData.api_key}
              className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-300 px-6 py-2.5 rounded-lg text-sm font-medium transition-colors border border-slate-700"
            >
              {testing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <TestTube className="h-4 w-4" />
              )}
              Test Connection
            </button>

            <button
              onClick={loadConfig}
              className="flex items-center gap-2 text-slate-400 hover:text-white px-4 py-2.5 rounded-lg text-sm transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {testResult && (
        <div
          className={`rounded-xl border p-6 ${
            testResult.connected
              ? "bg-green-900/20 border-green-700"
              : "bg-red-900/20 border-red-700"
          }`}
        >
          <div className="flex items-center gap-2 mb-3">
            {testResult.connected ? (
              <Check className="h-5 w-5 text-green-400" />
            ) : (
              <X className="h-5 w-5 text-red-400" />
            )}
            <span className="font-semibold">
              {testResult.connected ? "Connection Successful" : "Connection Failed"}
            </span>
          </div>

          {testResult.connected ? (
            <div className="space-y-2 text-sm text-slate-300">
              <p>
                <span className="text-slate-500">Response:</span> {testResult.response}
              </p>
              {testResult.latency_ms !== undefined && (
                <p>
                  <span className="text-slate-500">Latency:</span>{" "}
                  {testResult.latency_ms.toFixed(0)}ms
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-2 text-sm">
              {testResult.error && (
                <p className="text-red-300 flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  {testResult.error}
                </p>
              )}
              {testResult.details && (
                <details className="mt-2">
                  <summary className="text-slate-400 cursor-pointer hover:text-white">
                    Show details
                  </summary>
                  <pre className="mt-2 text-xs bg-slate-900 p-3 rounded-lg overflow-x-auto text-slate-400">
                    {testResult.details}
                  </pre>
                </details>
              )}
            </div>
          )}
        </div>
      )}

      <div className="bg-slate-900/50 rounded-xl border border-slate-800 p-6">
        <h3 className="font-medium text-slate-300 mb-3">💡 Usage Notes</h3>
        <ul className="space-y-2 text-sm text-slate-400">
          <li>
            • <strong>OpenAI Compatible</strong>: Works with any API that follows the
            OpenAI format (e.g., OpenRouter, Together.ai, local models with vLLM/Ollama)
          </li>
          <li>
            • <strong>Anthropic</strong>: Uses the native Anthropic API format with
            x-api-key header
          </li>
          <li>
            • <strong>Security</strong>: API keys are stored server-side. Use &quot;Test
            Connection&quot; to verify your configuration.
          </li>
          <li>
            • <strong>IDE Plugin</strong>: These settings are used by the IDE plugin for
            pre-commit reviews and code_standard caching.
          </li>
        </ul>
      </div>
    </div>
  );
}
