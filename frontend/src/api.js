export async function api(path, options = {}) {
  let response;
  try {
    const deadline = AbortSignal.timeout(75000);
    const signal = options.signal ? AbortSignal.any([options.signal, deadline]) : deadline;
    response = await fetch(`/api${path}`, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...options, signal });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Cannot reach the download service. It may be waking up — please try again in a moment.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(data?.error?.message || 'The service is temporarily unavailable. Please try again.');
    error.code = data?.error?.code;
    throw error;
  }
  return data;
}
export function bytes(value) {
  if (!value) return 'Size varies';
  return value >= 1_000_000_000 ? `${(value / 1_000_000_000).toFixed(1)} GB` : `${(value / 1_000_000).toFixed(1)} MB`;
}
export function duration(value) {
  return Number.isFinite(value) ? `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}` : null;
}
