export const API_BASE = '/api';

export async function startCompare(vb1File, vb2File) {
  const form = new FormData();
  form.append('vb1', vb1File);
  form.append('vb2', vb2File);
  const res = await fetch(`${API_BASE}/compare`, { method: 'POST', body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload thất bại (${res.status})`);
  }
  return res.json();
}

export async function getJobStatus(jobId) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/status`);
  if (!res.ok) throw new Error('Không lấy được trạng thái');
  return res.json();
}

export async function getJobResults(jobId) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/results`);
  if (!res.ok) throw new Error('Không lấy được kết quả');
  return res.json();
}

export function getFileUrl(jobId, doc) {
  return `${API_BASE}/jobs/${jobId}/file/${doc}`;
}

export async function sendChat(jobId, question) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'LLM không phản hồi');
  }
  return res.json();
}
