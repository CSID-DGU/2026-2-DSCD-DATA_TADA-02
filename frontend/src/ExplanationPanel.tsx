import { useEffect, useState } from 'react';
import { api } from './api';
import type { Config, Explanation } from './types';

export default function ExplanationPanel({ request, config, accessToken }: { request: Record<string, unknown>; config: Config; accessToken: string }) {
  const [result, setResult] = useState<Explanation | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const serialized = JSON.stringify(request);
  useEffect(() => {
    if (config.llm_auth_required && !accessToken) return;
    let active = true;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const started = performance.now();
    setError(''); setResult(null);
    async function load(attempt = 0) {
      try {
        const response = await api<Explanation>('/explanations', {
          method: 'POST', body: serialized, signal: controller.signal,
          headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
        });
        if (!active) return;
        setResult(response);
        if (response.status === 'running' && attempt < 35) timeout = setTimeout(() => load(attempt + 1), (response.retry_after_seconds || 2) * 1000);
        else if (response.status === 'running') setError('생성 대기가 길어졌습니다. 잠시 후 다시 시도하세요.');
        else performance.measure('ui:commentary-ready', { start: started, end: performance.now() });
      } catch (error) {
        if (active && !(error instanceof DOMException && error.name === 'AbortError')) setError(String(error instanceof Error ? error.message : error));
      }
    }
    void load();
    return () => { active = false; controller.abort(); if (timeout) clearTimeout(timeout); };
  }, [serialized, retry, config.llm_auth_required, accessToken]);

  return <section className="panel explanation" aria-labelledby="explanation-title" aria-live="polite">
    <div className="section-title"><h2 id="explanation-title"><span aria-hidden="true">✧</span> {request.section === 'competition' ? 'AI 종합 해설' : 'AI 상권 해설'}</h2><span className="badge">{result?.cache_hit ? '저장된 해설' : config.llm_enabled ? '근거 기반 해설' : '연결 준비'}</span></div>
    {config.llm_auth_required && !accessToken ? <p>상단의 서비스 접근 인증을 입력하면 해설을 볼 수 있습니다.</p> : error ? <p role="alert">{error}</p> : !result ? <p>이 페이지의 분석 근거를 확인하고 있습니다.</p> : result.content ? <>
      <p className="explanation-summary">{result.content.summary}</p>
      {result.content.blocks.map((block, i) => <div className="explanation-row" key={i}><span className="number">{i + 1}</span><strong>{block.title}</strong><p>{block.text}</p></div>)}
      {result.content.caveats.map((text, i) => <p className="muted" key={i}>{text}</p>)}
    </> : <p>{result.message}</p>}
    {(error || result?.status === 'failed') && <button onClick={() => setRetry(v => v + 1)}>해설 다시 시도</button>}
    <details><summary>해설에 전달하는 근거 보기</summary><p className="muted">해설의 세부 내용은 추후 조정합니다. 현재는 이 페이지에 대응하는 지표와 선택 조건만 전달합니다.</p><pre>{JSON.stringify(result?.evidence || request, null, 2)}</pre></details>
  </section>;
}
