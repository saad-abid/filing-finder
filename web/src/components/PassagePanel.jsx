// Side panel with the exact passage a citation points to.
export default function PassagePanel({ source, onClose }) {
  const page = source.printed_page ? `page ${source.printed_page}` : `HTML page ${source.page}`;

  return (
    <aside className="panel" aria-label="Source passage">
      <div className="panel-head">
        <div>
          <p className="panel-kicker">Source [{source.number}]</p>
          <h3>{source.company} 10-K · FY{source.fiscal_year}</h3>
          <p className="muted">{source.section} · {page}</p>
        </div>
        <button type="button" className="close" onClick={onClose} aria-label="Close">×</button>
      </div>

      <pre className="passage">{source.passage}</pre>

      <p className="muted small">
        This is the text the answer was written from (trimmed to the relevant part).
      </p>
      <a href={source.source_url} target="_blank" rel="noreferrer">
        Open the full filing on SEC EDGAR ↗
      </a>
    </aside>
  );
}
