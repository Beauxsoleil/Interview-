// Small shared UI helpers.

export const STATUS_STYLES = {
  "Pending Review": "bg-slate-100 text-slate-700",
  Priority: "bg-amber-100 text-amber-800",
  Approved: "bg-emerald-100 text-emerald-800",
  Rejected: "bg-rose-100 text-rose-800",
};

export function StatusBadge({ status }) {
  const cls = STATUS_STYLES[status] || "bg-slate-100 text-slate-700";
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

export function LabelChip({ label, onRemove }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium text-white"
      style={{ backgroundColor: label.color }}
    >
      {label.name}
      {onRemove && (
        <button
          onClick={onRemove}
          className="ml-0.5 rounded-full leading-none hover:opacity-70"
          title="Remove label"
        >
          ×
        </button>
      )}
    </span>
  );
}

export function formatDate(value) {
  if (!value) return "";
  const d = new Date(value);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatTime(seconds) {
  if (seconds == null) return "";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function JobBadge({ job }) {
  if (!job) return null;
  const map = {
    queued: "bg-slate-100 text-slate-600",
    running: "bg-blue-100 text-blue-700",
    done: "bg-emerald-100 text-emerald-700",
    error: "bg-rose-100 text-rose-700",
  };
  const label =
    job.state === "running"
      ? `processing ${job.progress}%`
      : job.state === "queued"
      ? "queued"
      : job.state === "error"
      ? "failed"
      : "done";
  if (job.state === "done") return null;
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        map[job.state] || map.queued
      }`}
      title={job.stage || ""}
    >
      {label}
    </span>
  );
}
