export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div aria-label="正在加载" className="loading-block" role="status">
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} style={{ width: `${92 - index * 7}%` }} />
      ))}
    </div>
  );
}
