export default function AreaDetailButton({ areaName, onClick }: { areaName: string; onClick: () => void }) {
  return <button type="button" className="text-link" aria-label={`이 상권 상세분석 (${areaName})`} onClick={onClick}>
    이 상권 상세분석 <span aria-hidden="true">→</span>
  </button>;
}
