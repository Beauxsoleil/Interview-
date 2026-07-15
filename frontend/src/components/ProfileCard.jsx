const FIELDS = [
  ["age", "Age"],
  ["physical_health", "Physical health"],
  ["prior_service_history", "Prior service history"],
  ["legal_history", "Legal history"],
  ["education_level", "Education level"],
  ["marital_status", "Marital status"],
  ["number_of_dependents", "Dependents"],
  ["tattoos_brandings_piercings", "Tattoos / brandings / piercings"],
];

export default function ProfileCard({ profile }) {
  const data = profile.data;
  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-semibold">Applicant profile</h3>
        <span className="text-xs text-slate-400">{profile.model}</span>
      </div>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
        {FIELDS.map(([key, label]) => (
          <ProfileRow key={key} label={label} field={data[key]} />
        ))}
      </dl>
      {data.free_text_notes && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Notes
          </dt>
          <dd className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
            {data.free_text_notes}
          </dd>
        </div>
      )}
    </div>
  );
}

function ProfileRow({ label, field }) {
  const notMentioned = !field || field.value === "not mentioned";
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">
        {label}
      </dt>
      <dd
        className={`mt-0.5 text-sm ${
          notMentioned ? "italic text-slate-400" : "text-slate-800"
        }`}
      >
        {notMentioned ? "not mentioned" : field.value}
      </dd>
      {!notMentioned && field.evidence && (
        <dd className="mt-0.5 text-xs text-slate-400">“{field.evidence}”</dd>
      )}
    </div>
  );
}
