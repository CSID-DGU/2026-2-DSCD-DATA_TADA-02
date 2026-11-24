import { useEffect, useState } from 'react';
import { api } from './api';
import AnalysisIcon from './AnalysisIcon';
import type { Commentary } from './demoCommentary';
import type { Config, Explanation } from './types';

export function DemoExplanationPanel({ question, lead, paragraphs, note, reportLayout = false }: Commentary & { reportLayout?: boolean }) {
  return <section className={reportLayout ? 'panel explanation demo-explanation report-explanation' : 'panel explanation demo-explanation'} aria-labelledby="explanation-title" aria-live="polite">
    <div className="section-title"><h2 id="explanation-title" tabIndex={-1}>{reportLayout ? <AnalysisIcon name="sparkle" /> : <span aria-hidden="true">✧</span>} {reportLayout ? 'AI 해설' : 'AI 상권 해설'}</h2><span className="badge">발표용 예시</span></div>
    <div className="explanation-body">
      <p className="explanation-question">{question}</p>
      <p className="explanation-summary">{lead}</p>
      {paragraphs.map(paragraph => <p className="explanation-paragraph" key={paragraph}>{paragraph}</p>)}
      {note && <p className="explanation-note">{note}</p>}
    </div>
  </section>;
}

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

  const overview = request.scope === 'comparison' && request.section === 'competition';
  const salesDetail = request.scope === 'detail' && request.section === 'profitability';
  const reportLayout = overview || salesDetail;
  const displayedEvidence = JSON.stringify(result?.evidence || request, (key, value) =>
    key === 'model_version' || key === 'interval_method' ? undefined : value, 2);
  return <section className={reportLayout ? 'panel explanation report-explanation' : 'panel explanation'} aria-labelledby="explanation-title" aria-live="polite">
    <div className="section-title"><h2 id="explanation-title">{reportLayout ? <AnalysisIcon name="sparkle" /> : <span aria-hidden="true">✧</span>} {overview ? 'AI 종합 해설' : salesDetail ? 'AI 해설' : 'AI 상권 해설'}</h2><span className="badge">{result?.cache_hit ? '저장된 해설' : config.llm_enabled ? '근거 기반 해설' : '연결 준비'}</span></div>
    <div className="explanation-body">
      {config.llm_auth_required && !accessToken ? <p>상단의 서비스 접근 인증을 입력하면 해설을 볼 수 있습니다.</p> : error ? <p role="alert">{error}</p> : !result ? <p>이 페이지의 분석 근거를 확인하고 있습니다.</p> : result.content ? <>
        <p className="explanation-summary">{result.content.summary}</p>
        {result.content.blocks.map((block, i) => <div className="explanation-row" key={i}><span className="number">{i + 1}</span><strong>{block.title}</strong><p>{block.text}</p></div>)}
        {result.content.caveats.map(text => <p className="muted" key={text}>{text}</p>)}
      </> : <p>{result.message}</p>}
      {(error || result?.status === 'failed') && <button onClick={() => setRetry(v => v + 1)}>해설 다시 시도</button>}
      <details><summary>해설에 전달하는 근거 보기</summary><p className="muted">해설의 세부 내용은 추후 조정합니다. 현재는 이 페이지에 대응하는 지표와 선택 조건만 전달합니다.</p><pre>{displayedEvidence}</pre></details>
    </div>
  </section>;
}
