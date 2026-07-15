import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { JobBadge, LabelChip, StatusBadge, formatDate } from "../lib/ui.jsx";
import UploadModal from "./UploadModal.jsx";

export default function InterviewListPage() {
  const [interviews, setInterviews] = useState([]);
  const [labels, setLabels] = useState([]);
  const [meta, setMeta] = useState({ statuses: [] });
  const [filters, setFilters] = useState({
    q: "",
    status: "",
    label_id: "",
    sort: "date",
    order: "desc",
  });
  const [uploadOpen, setUploadOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    const data = await api.listInterviews(filters);
    setInterviews(data);
    setLoading(false);
  }, [filters]);

  useEffect(() => {
    api.listLabels().then(setLabels).catch(() => {});
    api.meta().then(setMeta).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while any interview is still processing.
  useEffect(() => {
    const anyProcessing = interviews.some(
      (i) => i.latest_job && ["queued", "running"].includes(i.latest_job.state),
    );
    clearInterval(pollRef.current);
    if (anyProcessing) {
      pollRef.current = setInterval(load, 1500);
    }
    return () => clearInterval(pollRef.current);
  }, [interviews, load]);

  const setFilter = (k, v) => setFilters((f) => ({ ...f, [k]: v }));

  return (
    <div>
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Interviews</h1>
        <button className="btn-primary" onClick={() => setUploadOpen(true)}>
          + New interview
        </button>
      </div>

      <div className="card mb-4 flex flex-wrap items-center gap-3 p-3">
        <input
          value={filters.q}
          onChange={(e) => setFilter("q", e.target.value)}
          placeholder="Search transcripts, profiles, applicants…"
          className="input max-w-xs flex-1"
        />
        <Select
          value={filters.status}
          onChange={(v) => setFilter("status", v)}
          options={[["", "All statuses"], ...meta.statuses.map((s) => [s, s])]}
        />
        <Select
          value={filters.label_id}
          onChange={(v) => setFilter("label_id", v)}
          options={[["", "All labels"], ...labels.map((l) => [l.id, l.name])]}
        />
        <Select
          value={filters.sort}
          onChange={(v) => setFilter("sort", v)}
          options={[
            ["date", "Sort: date"],
            ["applicant", "Sort: applicant"],
            ["status", "Sort: status"],
            ["created", "Sort: created"],
          ]}
        />
        <button
          className="btn-ghost"
          onClick={() =>
            setFilter("order", filters.order === "desc" ? "asc" : "desc")
          }
          title="Toggle sort direction"
        >
          {filters.order === "desc" ? "↓" : "↑"}
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : interviews.length === 0 ? (
        <div className="card p-10 text-center text-slate-500">
          No interviews yet. Upload an audio file to get started.
        </div>
      ) : (
        <div className="card divide-y divide-slate-100">
          {interviews.map((iv) => (
            <Link
              key={iv.id}
              to={`/interviews/${iv.id}`}
              className="flex items-center gap-4 px-4 py-3 hover:bg-slate-50"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">
                    {iv.applicant_name}
                  </span>
                  {iv.title && (
                    <span className="truncate text-sm text-slate-400">
                      · {iv.title}
                    </span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>{formatDate(iv.interview_date)}</span>
                  {iv.has_transcript && <Dot label="transcript" />}
                  {iv.has_profile && <Dot label="profile" />}
                  {iv.labels.map((l) => (
                    <LabelChip key={l.id} label={l} />
                  ))}
                </div>
              </div>
              <JobBadge job={iv.latest_job} />
              <StatusBadge status={iv.status} />
            </Link>
          ))}
        </div>
      )}

      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onCreated={() => load()}
      />
    </div>
  );
}

function Dot({ label }) {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
      {label}
    </span>
  );
}

function Select({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-md border border-slate-300 bg-white px-2.5 py-2 text-sm outline-none focus:border-slate-500"
    >
      {options.map(([v, label]) => (
        <option key={v} value={v}>
          {label}
        </option>
      ))}
    </select>
  );
}
