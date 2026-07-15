import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { LabelChip, StatusBadge, formatDate } from "../lib/ui.jsx";
import ProfileCard from "./ProfileCard.jsx";
import TranscriptView from "./TranscriptView.jsx";

export default function InterviewDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [iv, setIv] = useState(null);
  const [labels, setLabels] = useState([]);
  const [meta, setMeta] = useState({ statuses: [] });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    const data = await api.getInterview(id);
    setIv(data);
    return data;
  }, [id]);

  useEffect(() => {
    load().catch((e) => setError(e.message));
    api.listLabels().then(setLabels).catch(() => {});
    api.meta().then(setMeta).catch(() => {});
  }, [load]);

  // Poll while processing.
  useEffect(() => {
    clearInterval(pollRef.current);
    const job = iv?.latest_job;
    if (job && ["queued", "running"].includes(job.state)) {
      pollRef.current = setInterval(() => load().catch(() => {}), 1500);
    }
    return () => clearInterval(pollRef.current);
  }, [iv, load]);

  if (error) return <p className="text-rose-600">{error}</p>;
  if (!iv) return <p className="text-sm text-slate-500">Loading…</p>;

  const job = iv.latest_job;
  const processing = job && ["queued", "running"].includes(job.state);

  async function update(patch) {
    const updated = await api.updateInterview(id, patch);
    setIv(updated);
  }

  async function action(fn) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("Delete this interview and its audio, transcript, and profile?"))
      return;
    await api.deleteInterview(id);
    navigate("/");
  }

  const activeLabelIds = new Set(iv.labels.map((l) => l.id));

  return (
    <div>
      <Link to="/" className="text-sm text-slate-500 hover:text-slate-800">
        ← All interviews
      </Link>

      <div className="mt-3 card p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {iv.applicant_name}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {iv.title ? `${iv.title} · ` : ""}
              {formatDate(iv.interview_date)}
              {iv.audio_filename ? ` · ${iv.audio_filename}` : ""}
              {" · "}
              <Link
                to={`/?applicant_id=${iv.applicant_id}`}
                className="text-slate-600 underline decoration-slate-300 underline-offset-2 hover:text-slate-900"
              >
                all interviews for this applicant
              </Link>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={iv.status}
              onChange={(e) => update({ status: e.target.value })}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm"
            >
              {meta.statuses.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <StatusBadge status={iv.status} />
          </div>
        </div>

        {/* Labels */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {iv.labels.map((l) => (
            <LabelChip
              key={l.id}
              label={l}
              onRemove={() =>
                update({
                  label_ids: iv.labels.filter((x) => x.id !== l.id).map((x) => x.id),
                })
              }
            />
          ))}
          <LabelPicker
            labels={labels.filter((l) => !activeLabelIds.has(l.id))}
            onPick={(labelId) =>
              update({ label_ids: [...iv.labels.map((x) => x.id), labelId] })
            }
            onCreated={(l) => {
              setLabels((ls) => [...ls, l]);
              update({ label_ids: [...iv.labels.map((x) => x.id), l.id] });
            }}
          />
        </div>

        {/* Actions */}
        <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
          <button
            className="btn-ghost"
            disabled={busy || processing}
            onClick={() => action(() => api.reprocess(id))}
          >
            Re-run transcription
          </button>
          <button
            className="btn-ghost"
            disabled={busy || processing || !iv.transcript}
            onClick={() => action(() => api.extractProfile(id))}
            title={
              !iv.transcript ? "Transcript required first" : "Re-extract profile"
            }
          >
            {iv.profile ? "Re-extract profile" : "Extract profile"}
          </button>
          <div className="flex-1" />
          <button
            className="rounded-md border border-rose-200 px-3.5 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50"
            onClick={remove}
          >
            Delete
          </button>
        </div>

        {error && (
          <div className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        )}
      </div>

      {processing && <ProgressBar job={job} />}

      {job?.state === "error" && (
        <div className="mt-4 rounded-md bg-rose-50 px-4 py-3 text-sm text-rose-700">
          Processing failed: {job.error}
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {iv.transcript ? (
          <TranscriptView interview={iv} onUpdated={load} />
        ) : (
          <div className="card p-8 text-center text-sm text-slate-500">
            {processing
              ? "Transcribing…"
              : "No transcript yet."}
          </div>
        )}

        {iv.profile ? (
          <ProfileCard profile={iv.profile} />
        ) : (
          <div className="card p-8 text-center text-sm text-slate-500">
            No profile extracted yet.
            {iv.transcript && !processing && (
              <>
                <br />
                Use “Extract profile” above (requires an Anthropic API key).
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ProgressBar({ job }) {
  return (
    <div className="mt-4 card p-4">
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="font-medium text-slate-700">
          {job.stage || "Processing"}…
        </span>
        <span className="text-slate-500">{job.progress}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full bg-blue-500 transition-all"
          style={{ width: `${job.progress}%` }}
        />
      </div>
    </div>
  );
}

function LabelPicker({ labels, onPick, onCreated }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

  async function create() {
    if (!name.trim()) return;
    const l = await api.createLabel({ name: name.trim(), color: randomColor() });
    setName("");
    setOpen(false);
    onCreated(l);
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="rounded-full border border-dashed border-slate-300 px-2.5 py-0.5 text-xs text-slate-500 hover:border-slate-400"
      >
        + label
      </button>
      {open && (
        <div className="absolute z-10 mt-1 w-56 rounded-lg border border-slate-200 bg-white p-2 shadow-lg">
          {labels.length > 0 && (
            <div className="mb-2 max-h-40 space-y-1 overflow-y-auto">
              {labels.map((l) => (
                <button
                  key={l.id}
                  onClick={() => {
                    onPick(l.id);
                    setOpen(false);
                  }}
                  className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm hover:bg-slate-50"
                >
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: l.color }}
                  />
                  {l.name}
                </button>
              ))}
            </div>
          )}
          <div className="flex gap-1">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && create()}
              placeholder="New label…"
              className="input !py-1 text-xs"
            />
            <button className="btn-primary !px-2 !py-1 text-xs" onClick={create}>
              Add
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const PALETTE = ["#0ea5e9", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#ef4444"];
function randomColor() {
  return PALETTE[Math.floor(Math.random() * PALETTE.length)];
}
