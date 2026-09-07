import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";

export default function UploadModal({ open, onClose, onCreated, meta, returnFocusRef }) {
  const [applicants, setApplicants] = useState([]);
  const [applicantName, setApplicantName] = useState("");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const dialogRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    api.listApplicants().then(setApplicants).catch((err) => setError(err.message));
    setError(null);
    requestAnimationFrame(() => dialogRef.current?.querySelector("input")?.focus());
    function keydown(event) {
      if (event.key === "Escape") close();
      if (event.key !== "Tab") return;
      const focusable = [...dialogRef.current.querySelectorAll("button, input, select, [tabindex]:not([tabindex='-1'])")].filter((element) => !element.disabled);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [open]);

  if (!open) return null;

  function close() {
    abortRef.current?.abort();
    onClose();
    requestAnimationFrame(() => returnFocusRef?.current?.focus());
  }

  async function submit(event) {
    event.preventDefault();
    setError(null);
    if (!file) return setError("Choose an audio file.");
    if (!applicantName.trim()) return setError("Enter an applicant name.");
    if (meta.max_upload_bytes && file.size > meta.max_upload_bytes) return setError(`The selected file exceeds the ${formatBytes(meta.max_upload_bytes)} limit.`);
    const form = new FormData();
    form.append("audio", file);
    form.append("applicant_name", applicantName.trim());
    if (title.trim()) form.append("title", title.trim());
    if (date) form.append("interview_date", new Date(date).toISOString());
    const controller = new AbortController();
    abortRef.current = controller;
    setSubmitting(true); setProgress(0);
    try {
      const created = await api.createInterview(form, { onProgress: setProgress, signal: controller.signal });
      onCreated(created); reset(); close();
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
    } finally {
      abortRef.current = null; setSubmitting(false);
    }
  }

  function reset() {
    setApplicantName(""); setTitle(""); setFile(null); setProgress(0);
  }

  const durationMinutes = Math.floor((meta.max_audio_duration_seconds || 0) / 60);
  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="upload-title" className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 id="upload-title" className="text-lg font-semibold">New interview</h2>
          <button type="button" onClick={close} aria-label="Close upload dialog" className="text-2xl text-slate-400 hover:text-slate-600">×</button>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <Field id="applicant-name" label="Applicant name">
            <input id="applicant-name" list="applicant-options" value={applicantName} onChange={(e) => setApplicantName(e.target.value)} placeholder="e.g. Jane Doe" className="input" required />
            <datalist id="applicant-options">{applicants.map((a) => <option key={a.id} value={a.name} />)}</datalist>
          </Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field id="interview-date" label="Interview date"><input id="interview-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input" /></Field>
            <Field id="interview-title" label="Title (optional)"><input id="interview-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Screening call" className="input" /></Field>
          </div>
          <Field id="audio-file" label="Audio file (mp3 / wav / m4a)">
            <input id="audio-file" type="file" accept=".mp3,.wav,.m4a,audio/*" onChange={(e) => setFile(e.target.files?.[0] || null)} className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-slate-200" required />
            <p className="mt-1 text-xs text-slate-500">Long recordings are processed in smaller sections. Maximum {formatBytes(meta.max_upload_bytes || 0)}{durationMinutes ? ` and ${durationMinutes} minutes` : ""}.</p>
          </Field>
          {submitting && <div aria-live="polite"><div className="mb-1 flex justify-between text-xs text-slate-600"><span>Uploading audio</span><span>{progress}%</span></div><progress className="h-2 w-full" max="100" value={progress}>{progress}%</progress></div>}
          {error && <div role="alert" className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={close} className="btn-ghost">{submitting ? "Cancel upload" : "Cancel"}</button>
            <button type="submit" disabled={submitting} className="btn-primary">{submitting ? (progress < 100 ? "Uploading…" : "Validating audio…") : "Upload & transcribe"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ id, label, children }) {
  return <div><label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">{label}</label>{children}</div>;
}

function formatBytes(bytes) {
  if (!bytes) return "the configured size limit";
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}
