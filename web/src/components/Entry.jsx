// One question and its answer (or its progress while it's being answered).

function elapsed(seconds) {
  const m = Math.floor(seconds / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function Progress({ entry }) {
  if (entry.status === "queued") {
    return (
      <p className="progress">
        ⏳ Waiting in line{entry.position ? ` (${entry.position} question${entry.position > 1 ? "s" : ""} ahead)` : ""}…
      </p>
    );
  }
  return (
    <p className="progress">
      ⏳ Searching the filings and writing a cited answer… {elapsed(entry.seconds || 0)}
      <span className="muted"> (usually 3–8 minutes)</span>
    </p>
  );
}

function Citations({ numbers, sources, onOpenSource, openSource }) {
  // Kept in one non-wrapping group so "[1][2][3]" never splits across lines.
  return <span className="cites">{numbers.map((n) => {
    const source = sources.find((s) => s.number === n);
    const active = openSource && source && openSource === source;
    return (
      <button
        key={n}
        type="button"
        className={`cite ${active ? "active" : ""}`}
        title={source ? source.citation : ""}
        onClick={() => source && onOpenSource(source)}
      >
        {n}
      </button>
    );
  })}</span>;
}

function Answer({ answer, onOpenSource, openSource }) {
  if (answer.status === "refused") {
    return <p className="notice refused">{answer.message}</p>;
  }

  return (
    <>
      {answer.status === "answered" ? (
        <div className="answer-text">
          {answer.sentences.map((s, i) => (
            <p key={i}>
              {s.text}{" "}
              <Citations numbers={s.citations} sources={answer.sources}
                         onOpenSource={onOpenSource} openSource={openSource} />
            </p>
          ))}
        </div>
      ) : (
        <p className="notice not-found">{answer.message}</p>
      )}

      {answer.limitations && (
        <p className="limits">
          <strong>{answer.status === "answered" ? "Limits of the evidence: " : "Details: "}</strong>
          {answer.limitations}
        </p>
      )}

      {answer.missing.length > 0 && (
        <p className="limits">
          <strong>Not in the filings collection: </strong>
          {answer.missing.map((m) => `${m.ticker || "any company"} FY${m.fiscal_year || "any"}`).join(", ")}
        </p>
      )}

      {answer.sources.length > 0 && (
        <div className="sources">
          <h3>Sources</h3>
          <ol>
            {answer.sources.map((s) => (
              <li key={s.number}>
                <button type="button" className={`link ${openSource === s ? "active" : ""}`}
                        onClick={() => onOpenSource(s)}>
                  [{s.number}] {s.citation}
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}

      {answer.removed.length > 0 && (
        <details className="removed">
          <summary>
            {answer.removed.length} sentence{answer.removed.length > 1 ? "s" : ""} removed by the safety check
          </summary>
          <ul>
            {answer.removed.map((r, i) => (
              <li key={i}><em>{r.reason}</em><br />{r.text}</li>
            ))}
          </ul>
        </details>
      )}

      {answer.model && (
        <p className="meta">
          {answer.model} · search {answer.seconds_search}s · writing {answer.seconds_model}s
        </p>
      )}
    </>
  );
}

export default function Entry({ entry, onOpenSource, openSource }) {
  return (
    <article className="entry">
      <h2 className="question">{entry.question}</h2>
      {(entry.status === "queued" || entry.status === "running") && <Progress entry={entry} />}
      {entry.status === "error" && (
        <p className="notice error">Something went wrong: {entry.error}</p>
      )}
      {entry.status === "done" && entry.answer && (
        <Answer answer={entry.answer} onOpenSource={onOpenSource} openSource={openSource} />
      )}
    </article>
  );
}
