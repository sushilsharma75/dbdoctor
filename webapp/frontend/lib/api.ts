// Typed client for the DBDoctor backend API.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export interface TokenOut {
  token: string;
  email: string;
  is_admin: boolean;
}

export interface Job {
  id: string;
  status: 'uploaded' | 'processing' | 'review' | 'approved' | 'failed';
  engine: string;
  client_alias: string;
  paid: boolean;
  score: string | null;
  error: string | null;
  created_at: string;
  has_pdf: boolean;
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('dbdoctor_token');
}

export function setSession(t: TokenOut) {
  window.localStorage.setItem('dbdoctor_token', t.token);
  window.localStorage.setItem('dbdoctor_email', t.email);
  window.localStorage.setItem('dbdoctor_admin', String(t.is_admin));
}

export function clearSession() {
  window.localStorage.removeItem('dbdoctor_token');
  window.localStorage.removeItem('dbdoctor_email');
  window.localStorage.removeItem('dbdoctor_admin');
}

export function isAdmin(): boolean {
  return typeof window !== 'undefined' && window.localStorage.getItem('dbdoctor_admin') === 'true';
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!resp.ok) {
    // A 401 on a request that carried a token means the session expired or was
    // revoked. Clear it and bounce to login rather than surfacing a raw
    // "invalid or expired token" next to the form. Auth endpoints are exempt so
    // a failed login keeps showing "invalid credentials" in place.
    if (resp.status === 401 && token && !path.startsWith('/auth/')) {
      clearSession();
      if (typeof window !== 'undefined') {
        window.location.href = '/login?expired=1';
      }
    }
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  register: (email: string, password: string) =>
    request<TokenOut>('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<TokenOut>('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }),

  listJobs: () => request<Job[]>('/jobs'),

  getJob: (id: string) => request<Job>(`/jobs/${id}`),

  approveJob: (id: string) => request<Job>(`/jobs/${id}/approve`, { method: 'POST' }),

  uploadSnapshot: (
    file: File,
    clientAlias: string,
    ddl: File[] = [],
    slowLog?: File,
    workloadMetrics?: File,
  ) => {
    const form = new FormData();
    form.append('snapshot', file);
    form.append('client_alias', clientAlias);
    ddl.forEach((source) => form.append('ddl', source));
    if (slowLog) form.append('slow_log', slowLog);
    if (workloadMetrics) form.append('workload_metrics', workloadMetrics);
    return request<Job>('/jobs', { method: 'POST', body: form });
  },

  reportUrl: (id: string, fmt: 'pdf' | 'html' | 'tasks') => `${API_URL}/jobs/${id}/report?fmt=${fmt}`,

  collectorUrl: (engine: 'postgres' | 'mysql') => `${API_URL}/collectors/${engine}`,
};

// Fetch a report artifact as text (html/tasks) with the auth header attached.
// The report endpoint is bearer-protected, so a plain <a href>/<iframe src>
// can't reach it — we fetch here and hand the caller the body to render inline.
export async function fetchReportText(id: string, fmt: 'html' | 'tasks'): Promise<string> {
  const resp = await fetch(api.reportUrl(id, fmt), {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return resp.text();
}

// Fetch the PDF as an in-memory object URL so it can be shown in an <iframe>
// (the browser's native PDF viewer) without a download. Caller must revoke it.
export async function fetchReportObjectUrl(id: string, fmt: 'pdf'): Promise<string> {
  const resp = await fetch(api.reportUrl(id, fmt), {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail ?? resp.statusText);
  return URL.createObjectURL(await resp.blob());
}

export async function downloadReport(id: string, fmt: 'pdf' | 'html' | 'tasks') {
  const resp = await fetch(api.reportUrl(id, fmt), {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new Error((await resp.json()).detail ?? resp.statusText);
  const blob = await resp.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `dbdoctor_report.${fmt === 'tasks' ? 'md' : fmt}`;
  a.click();
  URL.revokeObjectURL(a.href);
}
