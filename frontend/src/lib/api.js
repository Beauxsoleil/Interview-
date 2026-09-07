// Thin API client. All calls are same-origin relative (dev server proxies /api).

async function req(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
      if (detail && typeof detail === "object") {
        detail = detail.message || JSON.stringify(detail);
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

const json = (body, method = "POST") => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function upload(path, body, { onProgress, signal } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.responseType = "json";
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
    });
    xhr.addEventListener("load", () => {
      const response = xhr.response || {};
      if (xhr.status >= 200 && xhr.status < 300) resolve(response);
      else {
        const detail = response.detail;
        reject(new Error(typeof detail === "object" ? detail?.message : detail || xhr.statusText));
      }
    });
    xhr.addEventListener("error", () => reject(new Error("Upload failed. Check the connection and try again.")));
    xhr.addEventListener("abort", () => reject(new DOMException("Upload cancelled", "AbortError")));
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(body);
  });
}

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
  createInterview: (formData, options) => upload("/api/interviews", formData, options),
  updateInterview: (id, payload) =>
    req(`/api/interviews/${id}`, json(payload, "PATCH")),
  deleteInterview: (id) => req(`/api/interviews/${id}`, { method: "DELETE" }),
  updateSpeakers: (id, payload) =>
    req(`/api/interviews/${id}/speakers`, json(payload, "PATCH")),
  updateTranscript: (id, segments) =>
    req(`/api/interviews/${id}/transcript`, json({ segments }, "PATCH")),
  reviewTranscript: (id) =>
    req(`/api/interviews/${id}/transcript/review`, { method: "POST" }),
  reprocess: (id) => req(`/api/interviews/${id}/reprocess`, { method: "POST" }),
  extractProfile: (id) =>
    req(`/api/interviews/${id}/extract-profile`, { method: "POST" }),
  audioUrl: (id) => `/api/interviews/${id}/audio`,

  // Reviewed PIBASE Firestore sync
  extractSyncProfile: (id) =>
    req(`/api/interviews/${id}/sync/extract`, { method: "POST" }),
  findPibaseApplicants: (id, query = "") =>
    req(`/api/interviews/${id}/sync/candidates?q=${encodeURIComponent(query)}`),
  proposePibaseSync: (id, payload) =>
    req(`/api/interviews/${id}/sync/proposal`, json(payload)),
  confirmPibaseSync: (id, payload) =>
    req(`/api/interviews/${id}/sync/confirm`, json(payload)),
  listPibaseSyncLogs: (id) => req(`/api/interviews/${id}/sync/logs`),
};
