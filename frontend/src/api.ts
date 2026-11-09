export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const started = performance.now();
  const response = await fetch(`/api/v1${path}`, {
    ...options, headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  const body = await response.json();
  // Bounded, local browser measurements; no telemetry export or user inputs.
  performance.measure(`api:${path.split('?')[0]}`, { start: started, end: performance.now() });
  if (performance.getEntriesByType('measure').length > 100) performance.clearMeasures();
  if (!response.ok) {
    if (body.status === 'failed') return body as T;
    throw new Error(body.error?.message || `요청 실패 (${response.status})`);
  }
  return body as T;
}
