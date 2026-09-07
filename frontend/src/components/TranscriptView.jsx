import { useMemo, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { formatTime } from "../lib/ui.jsx";

export default function TranscriptView({ interview, onUpdated }) {
  const transcript = interview.transcript;
  const audioRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [editingSpeakers, setEditingSpeakers] = useState(false);
  const [editingText, setEditingText] = useState(false);
  const [draftSegments, setDraftSegments] = useState(transcript.segments);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const speakers = useMemo(() => {
    const seen = [];
    for (const s of transcript.segments) {
      if (!seen.includes(s.speaker)) seen.push(s.speaker);
    }
    return seen;
  }, [transcript.segments]);

  const labelFor = (raw) => transcript.speaker_labels?.[raw] || raw;

  function seek(t) {
    if (audioRef.current) {
      audioRef.current.currentTime = t;
      audioRef.current.play().catch(() => {});
    }
  }

  const activeIdx = transcript.segments.findIndex(
    (s) => currentTime >= s.start && currentTime < s.end,
  );

  async function saveTranscript() {
    setBusy(true); setError(null);
    try {
      await api.updateTranscript(interview.id, draftSegments);
      setEditingText(false);
      await onUpdated();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function markReviewed() {
    setBusy(true); setError(null);
    try {
      await api.reviewTranscript(interview.id);
      await onUpdated();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div><h3 className="font-semibold">Transcript</h3><p className="text-xs text-slate-500">Revision {transcript.revision} · {transcript.reviewed_at ? "reviewed" : "review required"}</p></div>
        <div className="flex items-center gap-2">
          {transcript.language && (
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              {transcript.language}
            </span>
          )}
          <button
            className="btn-ghost !py-1 text-xs"
            onClick={() => setEditingSpeakers((v) => !v)}
          >
            {editingSpeakers ? "Close" : "Rename speakers"}
          </button>
          <button className="btn-ghost !py-1 text-xs" onClick={() => { setDraftSegments(transcript.segments); setEditingText((value) => !value); }}>
            {editingText ? "Cancel edits" : "Correct transcript"}
          </button>
          <button className="btn-primary !py-1 text-xs" disabled={busy || editingText || Boolean(transcript.reviewed_at)} onClick={markReviewed}>
            {transcript.reviewed_at ? "Reviewed" : "Mark reviewed"}
          </button>
        </div>
      </div>

      <div className="border-b border-slate-100 bg-slate-50 px-4 py-3">
        <audio
          ref={audioRef}
          src={api.audioUrl(interview.id)}
          controls
          onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
          className="w-full"
        />
      </div>

      {editingSpeakers && (
        <SpeakerEditor
          interviewId={interview.id}
          speakers={speakers}
          labels={transcript.speaker_labels || {}}
          applicantSpeaker={transcript.applicant_speaker}
          onSaved={() => {
            setEditingSpeakers(false);
            onUpdated();
          }}
        />
      )}

      {error && <div role="alert" className="m-3 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

      <div className="max-h-[520px] space-y-1 overflow-y-auto p-3">
        {(editingText ? draftSegments : transcript.segments).map((seg, i) => {
          const isApplicant = seg.speaker === transcript.applicant_speaker;
          return (
            editingText ? (
              <div key={i} className="rounded-lg border border-slate-200 p-3">
                <div className="mb-1 text-xs font-semibold text-slate-500">{labelFor(seg.speaker)} · {formatTime(seg.start)}</div>
                <textarea aria-label={`Transcript text at ${formatTime(seg.start)}`} rows={3} className="input resize-y" value={seg.text} onChange={(event) => setDraftSegments((items) => items.map((item, index) => index === i ? { ...item, text: event.target.value } : item))} />
              </div>
            ) : <button
              key={i}
              onClick={() => seek(seg.start)}
              className={`block w-full rounded-lg px-3 py-2 text-left transition ${
                i === activeIdx ? "bg-amber-50 ring-1 ring-amber-200" : "hover:bg-slate-50"
              }`}
            >
              <div className="mb-0.5 flex items-center gap-2">
                <span
                  className={`text-xs font-semibold ${
                    isApplicant ? "text-emerald-700" : "text-slate-500"
                  }`}
                >
                  {labelFor(seg.speaker)}
                  {isApplicant && " · applicant"}
                </span>
                <span className="text-[11px] text-slate-400">
                  {formatTime(seg.start)}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-slate-800">{seg.text}</p>
            </button>
          );
        })}
      </div>
      {editingText && <div className="flex justify-end border-t border-slate-100 p-3"><button className="btn-primary" disabled={busy} onClick={saveTranscript}>{busy ? "Saving…" : "Save transcript corrections"}</button></div>}
    </div>
  );
}

function SpeakerEditor({ interviewId, speakers, labels, applicantSpeaker, onSaved }) {
  const [names, setNames] = useState(() =>
    Object.fromEntries(speakers.map((s) => [s, labels[s] || ""])),
  );
  const [applicant, setApplicant] = useState(applicantSpeaker || speakers[0] || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.updateSpeakers(interviewId, {
        speaker_labels: names,
        applicant_speaker: applicant,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border-b border-slate-100 bg-slate-50 px-4 py-3">
      <p className="mb-2 text-xs text-slate-500">
        Rename each speaker and mark which one is the applicant (used for profile
        extraction).
      </p>
      <div className="space-y-2">
        {speakers.map((s) => (
          <div key={s} className="flex items-center gap-3">
            <span className="w-20 shrink-0 text-sm text-slate-500">{s}</span>
            <input
              value={names[s]}
              onChange={(e) => setNames((n) => ({ ...n, [s]: e.target.value }))}
              placeholder="e.g. Interviewer / Applicant"
              className="input flex-1"
            />
            <label className="flex items-center gap-1.5 text-xs text-slate-600">
              <input
                type="radio"
                name="applicant"
                checked={applicant === s}
                onChange={() => setApplicant(s)}
              />
              applicant
            </label>
          </div>
        ))}
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-rose-700">{error}</p>}
      <div className="mt-3 flex justify-end">
        <button className="btn-primary !py-1.5 text-sm" disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save speakers"}
        </button>
      </div>
    </div>
  );
}
