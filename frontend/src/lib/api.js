// Thin API client. All calls are same-origin relative (dev server proxies /api).

async function req(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

const json = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => req("/api/health"),
  meta: () => req("/api/meta"),

  // Applicants
  listApplicants: () => req("/api/applicants"),
  createApplicant: (payload) => req("/api/applicants", json(payload)),

  // Labels
  listLabels: () => req("/api/labels"),
  createLabel: (payload) => req("/api/labels", json(payload)),
  deleteLabel: (id) => req(`/api/labels/${id}`, { method: "DELETE" }),

  // Interviews
  listInterviews: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null),
    ).toString();
    return req(`/api/interviews${qs ? `?${qs}` : ""}`);
  },
  getInterview: (id) => req(`/api/interviews/${id}`),
  createInterview: (formData) =>
    req("/api/interviews", { method: "POST", body: formData }),
  updateInterview: (id, payload) =>
    req(`/api/interviews/${id}`, { method: "PATCH", ...json(payload) }),
  deleteInterview: (id) => req(`/api/interviews/${id}`, { method: "DELETE" }),
  updateSpeakers: (id, payload) =>
    req(`/api/interviews/${id}/speakers`, { method: "PATCH", ...json(payload) }),
  reprocess: (id) => req(`/api/interviews/${id}/reprocess`, { method: "POST" }),
  extractProfile: (id) =>
    req(`/api/interviews/${id}/extract-profile`, { method: "POST" }),
  audioUrl: (id) => `/api/interviews/${id}/audio`,
};
