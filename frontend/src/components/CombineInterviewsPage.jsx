import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { formatDate, formatTime } from "../lib/ui.jsx";

const STEPS = ["Select", "Order", "Confirm"];

export default function CombineInterviewsPage() {
  const [searchParams] = useSearchParams();
  const applicantId = searchParams.get("applicant_id") || "";
  const navigate = useNavigate();
  const [interviews, setInterviews] = useState([]);
  const [selected, setSelected] = useState([]);
  const [step, setStep] = useState(1);
  const [title, setTitle] = useState("Combined interview");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.listInterviews({ applicant_id: applicantId, sort: "date", order: "asc" })
      .then((items) => {
        const sources = items.filter((item) => !item.is_combined);
        setInterviews(sources);
        setSelected(
          sources
            .filter((item) => item.has_transcript && item.transcript_reviewed)
            .map((item) => item.id),
        );
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [applicantId]);

  const ordered = useMemo(
    () => selected.map((id) => interviews.find((item) => item.id === id)).filter(Boolean),
    [selected, interviews],
  );
  const applicantName = interviews[0]?.applicant_name || "Applicant";
  const totalDuration = ordered.reduce(
    (total, interview) => total + (interview.audio_duration_seconds || 0),
    0,
  );

  function toggle(id) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : [...current, id],
    );
  }

  function move(index, direction) {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= selected.length) return;
    setSelected((current) => {
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  }

  async function combine() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.combineInterviews({
        source_interview_ids: selected,
        title: title.trim() || "Combined interview",
      });
      navigate(`/interviews/${created.id}`, { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-slate-500">Loading recordings…</p>;
  if (!applicantId) {
    return (
      <div className="mx-auto max-w-xl card p-6 text-center">
        <h1 className="text-xl font-semibold">Choose an applicant first</h1>
        <p className="mt-2 text-sm text-slate-600">
          Filter the interview list by applicant, then choose Combine recordings.
        </p>
        <Link to="/" className="btn-primary mt-4 inline-block">Back to interviews</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Link to={applicantId ? `/?applicant_id=${applicantId}` : "/"} className="text-sm text-slate-500 hover:text-slate-800">
        ← Back to interviews
      </Link>
      <header className="mt-3">
        <p className="text-sm font-medium text-slate-500">{applicantName}</p>
        <h1 className="text-2xl font-semibold tracking-tight">Combine recordings</h1>
        <p className="mt-1 text-sm text-slate-600">
          Create one interview while preserving every original recording.
        </p>
      </header>

      <ol aria-label="Combine recording progress" className="mt-5 grid grid-cols-3 gap-2">
        {STEPS.map((label, index) => {
          const number = index + 1;
          return (
            <li
              key={label}
              aria-current={step === number ? "step" : undefined}
              className={`rounded-lg border px-3 py-2 text-sm ${
                step === number
                  ? "border-slate-900 bg-slate-900 text-white"
                  : number < step
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-slate-200 bg-white text-slate-500"
              }`}
            >
              <span className="font-semibold">{number < step ? "✓" : number}.</span> {label}
            </li>
          );
        })}
      </ol>

      {error && <div role="alert" className="mt-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      <section className="card mt-4 p-5">
        {step === 1 && (
          <>
            <h2 className="text-lg font-semibold">Select the recording parts</h2>
            <p className="mt-1 text-sm text-slate-500">Choose at least two reviewed transcripts from the same interview.</p>
            <div className="mt-4 space-y-2">
              {interviews.map((interview) => {
                const ready = interview.has_transcript && interview.transcript_reviewed;
                return (
                  <label key={interview.id} className={`flex min-h-14 items-center gap-3 rounded-lg border p-3 ${ready ? "cursor-pointer border-slate-200" : "border-slate-100 bg-slate-50 text-slate-400"}`}>
                    <input type="checkbox" checked={selected.includes(interview.id)} disabled={!ready} onChange={() => toggle(interview.id)} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{interview.title || interview.applicant_name}</p>
                      <p className="mt-0.5 truncate text-xs text-slate-500">{formatDate(interview.interview_date)}{interview.audio_filename ? ` · ${interview.audio_filename}` : ""}</p>
                    </div>
                    <span className={`text-xs font-medium ${ready ? "text-emerald-700" : "text-amber-700"}`}>{ready ? "Reviewed" : "Review required"}</span>
                  </label>
                );
              })}
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <h2 className="text-lg font-semibold">Put the parts in order</h2>
            <p className="mt-1 text-sm text-slate-500">Part 1 should be where the conversation begins.</p>
            <ol className="mt-4 space-y-2">
              {ordered.map((interview, index) => (
                <li key={interview.id} className="flex items-center gap-3 rounded-lg border border-slate-200 p-3">
                  <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold">{index + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{interview.title || interview.audio_filename || `Recording ${interview.id}`}</p>
                    <p className="truncate text-xs text-slate-500">{interview.audio_filename || formatDate(interview.interview_date)}</p>
                  </div>
                  <div className="flex gap-1">
                    <button type="button" className="btn-ghost min-h-11 min-w-11 !px-2" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Move part ${index + 1} up`}>↑</button>
                    <button type="button" className="btn-ghost min-h-11 min-w-11 !px-2" disabled={index === ordered.length - 1} onClick={() => move(index, 1)} aria-label={`Move part ${index + 1} down`}>↓</button>
                  </div>
                </li>
              ))}
            </ol>
          </>
        )}

        {step === 3 && (
          <>
            <h2 className="text-lg font-semibold">Review before combining</h2>
            <label className="mt-4 block text-sm font-medium text-slate-700">
              Combined interview title
              <input className="input mt-1" value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <dl className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
              <Summary label="Applicant" value={applicantName} />
              <Summary label="Recording parts" value={String(ordered.length)} />
              <Summary label="Total duration" value={formatTime(totalDuration)} />
              <Summary label="Order" value={ordered.map((item, index) => `${index + 1}. ${item.audio_filename || item.title || `Recording ${item.id}`}`).join("\n")} />
              <Summary label="Originals" value="Preserved and recoverable" />
            </dl>
            <div className="mt-4 rounded-lg bg-blue-50 p-4 text-sm text-blue-900">
              The new combined transcript will require one final review before profile extraction or PIBASE sync.
            </div>
          </>
        )}

        <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
          <button type="button" className="btn-ghost min-h-11" onClick={() => step === 1 ? navigate(-1) : setStep((value) => value - 1)}>{step === 1 ? "Cancel" : "Back"}</button>
          {step < 3 ? (
            <button type="button" className="btn-primary min-h-11" disabled={selected.length < 2} onClick={() => setStep((value) => value + 1)}>Continue</button>
          ) : (
            <button type="button" className="btn-primary min-h-11" disabled={busy || selected.length < 2} onClick={combine}>{busy ? "Combining…" : "Combine and open interview"}</button>
          )}
        </div>
      </section>
    </div>
  );
}

function Summary({ label, value }) {
  return <div className="grid gap-1 px-4 py-3 sm:grid-cols-[10rem_1fr]"><dt className="text-sm font-medium text-slate-500">{label}</dt><dd className="whitespace-pre-wrap text-sm text-slate-900">{value}</dd></div>;
}
