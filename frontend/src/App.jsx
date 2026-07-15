import { useEffect, useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { api } from "./lib/api.js";

export default function App() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "down" }));
  }, []);

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="flex items-center gap-2">
            <span className="text-lg font-semibold tracking-tight">
              Interview Profiling
            </span>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              local-only
            </span>
          </Link>
          {health && <PipelineStatus health={health} />}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

function PipelineStatus({ health }) {
  const stub = health.pipeline_backend === "stub";
  return (
    <div className="flex items-center gap-3 text-xs">
      <span
        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ${
          stub
            ? "bg-amber-50 text-amber-700"
            : "bg-emerald-50 text-emerald-700"
        }`}
        title={
          stub
            ? "ML models not installed — using the built-in sample-transcript backend."
            : "Whisper + pyannote available."
        }
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            stub ? "bg-amber-500" : "bg-emerald-500"
          }`}
        />
        {stub ? "stub pipeline" : "ML pipeline"}
      </span>
      <span
        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ${
          health.profile_extraction_enabled
            ? "bg-emerald-50 text-emerald-700"
            : "bg-slate-100 text-slate-500"
        }`}
        title={
          health.profile_extraction_enabled
            ? `Profile extraction via ${health.profile_model}`
            : "Set ANTHROPIC_API_KEY to enable profile extraction."
        }
      >
        profile: {health.profile_extraction_enabled ? "on" : "off"}
      </span>
    </div>
  );
}
