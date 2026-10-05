const BASE = "/api";

async function get(path, params) {
  const url = new URL(BASE + path, window.location.origin);
  if (params) Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v));
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  summary: () => get("/summary"),
  alerts: (params) => get("/alerts", params),
  rings: (params) => get("/rings", params),
  ring: (id) => get(`/rings/${id}`),
  ringGraph: (id) => get(`/rings/${id}/graph`),
  ringTimeline: (id) => get(`/rings/${id}/timeline`),
  ringPatterns: (id) => get(`/rings/${id}/patterns`),
  ringEvidence: (id) => get(`/rings/${id}/evidence`),
  ringExplanation: (id) => get(`/rings/${id}/explanation`),
  account: (id) => get(`/accounts/${id}`),
  transactions: (params) => get("/transactions", params),
  patterns: (params) => get("/patterns", params),
  metrics: () => get("/metrics"),
  leadTime: () => get("/lead-time"),
  models: () => get("/models"),
};
