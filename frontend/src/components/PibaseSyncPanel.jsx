import { useMemo, useState } from "react";
import { api } from "../lib/api.js";

const FIELD_LABELS = {
  age: "Age",
  priorService: "Prior service",
  physicalHealth: "Physical health",
  legalIssues: "Legal issues",
  educationLevel: "Education level",
  maritalStatus: "Marital status",
  dependents: "Dependents",
  tattoosBrandsPiercings: "Tattoos, brands, and piercings",
  generalArea: "General area",
};

export default function PibaseSyncPanel({ interview }) {
  const [extraction, setExtraction] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [search, setSearch] = useState(interview.applicant_name || "");
  const [selection, setSelection] = useState("");
  const [createNew, setCreateNew] = useState(false);
  const [newName, setNewName] = useState(interview.applicant_name || "");
  const [proposal, setProposal] = useState(null);
  const [approved, setApproved] = useState(new Set());
  const [approvedBy, setApprovedBy] = useState("Recruiter");
  const [unarchive, setUnarchive] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const targetPayload = useMemo(
    () =>
      createNew
        ? { create_new: true, new_applicant_name: newName.trim() }
        : { applicant_id: selection, create_new: false },
    [createNew, newName, selection],
  );

  async function run(task) {
    setBusy(true);
    setError(null);
    try {
      return await task();
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function extract() {
    const data = await run(() => api.extractSyncProfile(interview.id));
    if (!data) return;
    setExtraction(data);
    setProposal(null);
    setResult(null);
    const name = data.extraction.applicant_name?.value;
    const suggested = name && name !== "not mentioned" ? String(name) : search;
    setSearch(suggested);
    setNewName(suggested || interview.applicant_name || "");
    const matches = await run(() =>
      api.findPibaseApplicants(interview.id, suggested),
    );
    if (matches) setCandidates(matches);
  }

  async function findCandidates(event) {
    event?.preventDefault();
    const matches = await run(() =>
      api.findPibaseApplicants(interview.id, search),
    );
    if (matches) {
      setCandidates(matches);
      setProposal(null);
    }
  }

  async function buildProposal() {
    const data = await run(() =>
      api.proposePibaseSync(interview.id, targetPayload),
    );
    if (!data) return;
    setProposal(data);
    setApproved(new Set());
    setUnarchive(false);
    setResult(null);
  }

  function toggleField(field) {
    setApproved((current) => {
      const next = new Set(current);
      if (next.has(field)) next.delete(field);
      else next.add(field);
      return next;
    });
  }

  function approveAll() {
    setApproved(
      new Set(
        proposal.changes
          .filter((change) => change.changed && change.proposed_value != null)
          .map((change) => change.field),
      ),
    );
  }

  async function confirmSync() {
    const data = await run(() =>
      api.confirmPibaseSync(interview.id, {
        ...targetPayload,
        approved_fields: [...approved],
        approved_by: approvedBy.trim(),
        unarchive,
      }),
    );
    if (data) setResult(data);
  }

  return (
    <section className="mt-4 card overflow-hidden">
      <div className="border-b border-slate-100 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">Send reviewed details to PIBASE</h2>
            <p className="mt-1 text-sm text-slate-500">
              Nothing is written until you choose an applicant and confirm the
              proposed fields.
            </p>
          </div>
          <button
            className="btn-primary"
            disabled={busy}
            onClick={extract}
          >
            {extraction ? "Extract again" : "Prepare PIBASE review"}
          </button>
        </div>
      </div>

      <div className="space-y-6 p-5">
        {error && (
          <div className="rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {!extraction && (
          <p className="text-sm text-slate-500">
            Prepare a review to extract PIBASE-compatible fields from this
            transcript. This does not write to Firestore.
          </p>
        )}

        {extraction && (
          <>
            <div>
              <StepHeading number="1" title="Choose the PIBASE applicant" />
              <form className="mt-3 flex gap-2" onSubmit={findCandidates}>
                <input
                  className="input"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by applicant name"
                />
                <button className="btn-ghost" disabled={busy} type="submit">
                  Search
                </button>
              </form>

              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {candidates.map((candidate) => (
                  <label
                    key={candidate.id}
                    className={`cursor-pointer rounded-lg border p-3 ${
                      !createNew && selection === candidate.id
                        ? "border-slate-700 bg-slate-50"
                        : "border-slate-200"
                    } ${candidate.archived ? "opacity-70" : ""}`}
                  >
                    <div className="flex gap-3">
                      <input
                        type="radio"
                        name="pibase-target"
                        checked={!createNew && selection === candidate.id}
                        onChange={() => {
                          setCreateNew(false);
                          setSelection(candidate.id);
                          setProposal(null);
                        }}
                      />
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{candidate.name}</span>
                          {candidate.archived && (
                            <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
                              Archived
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          {[candidate.phone, candidate.statusStage]
                            .filter(Boolean)
                            .join(" · ") || "No additional details"}
                        </p>
                      </div>
                    </div>
                  </label>
                ))}

                <label
                  className={`cursor-pointer rounded-lg border p-3 ${
                    createNew
                      ? "border-slate-700 bg-slate-50"
                      : "border-slate-200"
                  }`}
                >
                  <div className="flex gap-3">
                    <input
                      type="radio"
                      name="pibase-target"
                      checked={createNew}
                      onChange={() => {
                        setCreateNew(true);
                        setSelection("");
                        setProposal(null);
                      }}
                    />
                    <div className="w-full">
                      <span className="font-medium">Create new applicant</span>
                      {createNew && (
                        <input
                          className="input mt-2"
                          value={newName}
                          onChange={(event) => setNewName(event.target.value)}
                          placeholder="Applicant name"
                        />
                      )}
                    </div>
                  </div>
                </label>
              </div>

              <button
                className="btn-primary mt-3"
                disabled={
                  busy || (!createNew && !selection) || (createNew && !newName.trim())
                }
                onClick={buildProposal}
              >
                Review proposed changes
              </button>
            </div>

            {proposal && (
              <div className="border-t border-slate-100 pt-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <StepHeading number="2" title="Approve individual fields" />
                  <button className="btn-ghost !py-1.5" onClick={approveAll}>
                    Approve all changed fields
                  </button>
                </div>

                {proposal.archived && (
                  <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                    <p className="font-medium">This applicant is archived.</p>
                    <label className="mt-2 flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={unarchive}
                        onChange={(event) => setUnarchive(event.target.checked)}
                      />
                      Unarchive this applicant before syncing
                    </label>
                  </div>
                )}

                <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full min-w-[720px] text-left text-sm">
                    <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="px-3 py-2">Approve</th>
                        <th className="px-3 py-2">Field</th>
                        <th className="px-3 py-2">Current PIBASE value</th>
                        <th className="px-3 py-2">Proposed value</th>
                        <th className="px-3 py-2">Transcript support</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {proposal.changes.map((change) => {
                        const canApprove =
                          change.changed && change.proposed_value != null;
                        return (
                          <tr key={change.field}>
                            <td className="px-3 py-3">
                              <input
                                type="checkbox"
                                disabled={!canApprove}
                                checked={approved.has(change.field)}
                                onChange={() => toggleField(change.field)}
                                aria-label={`Approve ${FIELD_LABELS[change.field]}`}
                              />
                            </td>
                            <td className="px-3 py-3 font-medium">
                              {FIELD_LABELS[change.field]}
                            </td>
                            <td className="max-w-48 px-3 py-3 text-slate-500">
                              <Value value={change.current_value} />
                            </td>
                            <td className="max-w-48 px-3 py-3">
                              <Value value={change.proposed_value} />
                            </td>
                            <td className="max-w-64 px-3 py-3 text-xs text-slate-500">
                              {change.evidence || "Not mentioned"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-4">
                  <p className="text-sm font-medium text-blue-900">
                    Recruiter note — always added as a new entry
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-blue-800">
                    {proposal.note || "No additional summary was extracted."}
                  </p>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                  <label className="text-sm font-medium text-slate-700">
                    Approved by
                    <input
                      className="input mt-1"
                      value={approvedBy}
                      onChange={(event) => setApprovedBy(event.target.value)}
                      placeholder="Your name"
                    />
                  </label>
                  <button
                    className="btn-primary"
                    disabled={
                      busy ||
                      Boolean(result) ||
                      !approvedBy.trim() ||
                      (proposal.archived && !unarchive)
                    }
                    onClick={confirmSync}
                  >
                    Confirm note and approved fields
                  </button>
                </div>
              </div>
            )}

            {result && (
              <div className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                <p className="font-medium">PIBASE sync completed.</p>
                <p className="mt-1">
                  Note added. {result.fields_written.length} structured field
                  {result.fields_written.length === 1 ? "" : "s"} updated. Audit
                  log #{result.log.id} recorded.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function StepHeading({ number, title }) {
  return (
    <h3 className="flex items-center gap-2 font-medium">
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs text-white">
        {number}
      </span>
      {title}
    </h3>
  );
}

function Value({ value }) {
  if (value == null || value === "") {
    return <span className="italic text-slate-400">Not set</span>;
  }
  return <span className="whitespace-pre-wrap">{String(value)}</span>;
}
