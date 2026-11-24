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

export default function ExplanationPanel({ request, config, result, error, requestNeedsAuth, waitingMessage, onRetry }: {
  request: Record<string, unknown>;
  config: Config;
  result?: Explanation;
  error?: string;
  requestNeedsAuth: boolean;
  waitingMessage?: string;
  onRetry?: () => void;
}) {
  const overview = request.scope === 'comparison' && request.section === 'competition';
  const salesDetail = request.scope === 'detail' && request.section === 'profitability';
  const reportLayout = overview || salesDetail;
  const displayedEvidence = JSON.stringify(result?.evidence || request, (key, value) =>
    key === 'model_version' || key === 'interval_method' ? undefined : value, 2);
  return <section className={reportLayout ? 'panel explanation report-explanation' : 'panel explanation'} aria-labelledby="explanation-title" aria-live="polite">
    <div className="section-title"><h2 id="explanation-title">{reportLayout ? <AnalysisIcon name="sparkle" /> : <span aria-hidden="true">✧</span>} {overview ? 'AI 종합 해설' : salesDetail ? 'AI 해설' : 'AI 상권 해설'}</h2><span className="badge">{result?.cache_hit ? '저장된 해설' : config.llm_enabled ? '근거 기반 해설' : '연결 준비'}</span></div>
    <div className="explanation-body">
      {requestNeedsAuth ? <p>서비스 접근 인증을 입력하면 해설을 볼 수 있습니다.</p> : error ? <p role="alert">{error}</p> : !result ? <p>{waitingMessage || 'AI 해설을 불러오는 중입니다.'}</p> : result.content ? <>
        <p className="explanation-summary">{result.content.summary}</p>
        {result.content.blocks.map((block, i) => <div className="explanation-row" key={i}><span className="number">{i + 1}</span><strong>{block.title}</strong><p>{block.text}</p></div>)}
        {result.content.caveats.map(text => <p className="muted" key={text}>{text}</p>)}
      </> : <p>{result.message}</p>}
      {onRetry && (error || result?.status === 'failed') && <button onClick={onRetry}>해설 다시 시도</button>}
      {result && <details><summary>해설에 전달하는 근거 보기</summary><p className="muted">선택한 화면의 지표와 조건입니다.</p><pre>{displayedEvidence}</pre></details>}
    </div>
  </section>;
}
