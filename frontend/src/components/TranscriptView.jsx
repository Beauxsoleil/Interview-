import { useMemo, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { formatTime } from "../lib/ui.jsx";

export default function TranscriptView({ interview, onUpdated }) {
  const transcript = interview.transcript;
  const audioRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [editingSpeakers, setEditingSpeakers] = useState(false);

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

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <h3 className="font-semibold">Transcript</h3>
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

      <div className="max-h-[520px] space-y-1 overflow-y-auto p-3">
        {transcript.segments.map((seg, i) => {
          const isApplicant = seg.speaker === transcript.applicant_speaker;
          return (
            <button
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
    </div>
  );
}

function SpeakerEditor({ interviewId, speakers, labels, applicantSpeaker, onSaved }) {
  const [names, setNames] = useState(() =>
    Object.fromEntries(speakers.map((s) => [s, labels[s] || ""])),
  );
  const [applicant, setApplicant] = useState(applicantSpeaker || speakers[0] || "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await api.updateSpeakers(interviewId, {
        speaker_labels: names,
        applicant_speaker: applicant,
      });
      onSaved();
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
      <div className="mt-3 flex justify-end">
        <button className="btn-primary !py-1.5 text-sm" disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save speakers"}
        </button>
      </div>
    </div>
  );
}
