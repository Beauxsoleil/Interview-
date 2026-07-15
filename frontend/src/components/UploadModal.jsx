import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

export default function UploadModal({ open, onClose, onCreated }) {
  const [applicants, setApplicants] = useState([]);
  const [applicantName, setApplicantName] = useState("");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      api.listApplicants().then(setApplicants).catch(() => {});
      setError(null);
    }
  }, [open]);

  if (!open) return null;

  async function submit(e) {
    e.preventDefault();
    setError(null);
    if (!file) return setError("Choose an audio file.");
    if (!applicantName.trim()) return setError("Enter an applicant name.");

    const fd = new FormData();
    fd.append("audio", file);
    fd.append("applicant_name", applicantName.trim());
    if (title.trim()) fd.append("title", title.trim());
    if (date) fd.append("interview_date", new Date(date).toISOString());

    setSubmitting(true);
    try {
      const created = await api.createInterview(fd);
      onCreated(created);
      onClose();
      reset();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    setApplicantName("");
    setTitle("");
    setFile(null);
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">New interview</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            ×
          </button>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Applicant name">
            <input
              list="applicant-options"
              value={applicantName}
              onChange={(e) => setApplicantName(e.target.value)}
              placeholder="e.g. Jane Doe"
              className="input"
            />
            <datalist id="applicant-options">
              {applicants.map((a) => (
                <option key={a.id} value={a.name} />
              ))}
            </datalist>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Interview date">
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Title (optional)">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Screening call"
                className="input"
              />
            </Field>
          </div>

          <Field label="Audio file (mp3 / wav / m4a)">
            <input
              type="file"
              accept=".mp3,.wav,.m4a,audio/*"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-slate-200"
            />
          </Field>

          {error && (
            <div className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost">
              Cancel
            </button>
            <button type="submit" disabled={submitting} className="btn-primary">
              {submitting ? "Uploading…" : "Upload & transcribe"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}
