import { useState } from "react";

export default function QuestionBox({ onAsk, examples, busy }) {
  const [text, setText] = useState("");

  function submit(e) {
    e.preventDefault();
    const question = text.trim();
    if (question.length < 3) return;
    onAsk(question);
    setText("");
  }

  return (
    <form className="question-box" onSubmit={submit}>
      <div className="input-row">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) submit(e);   // Shift+Enter for a new line
          }}
          placeholder="Ask a question about the filings…"
          rows={2}
          maxLength={500}
        />
        <button type="submit" disabled={text.trim().length < 3}>Ask</button>
      </div>
      {busy && (
        <p className="hint">
          Answers take a few minutes on this computer. New questions wait in line.
        </p>
      )}
      {examples.length > 0 && (
        <details className="examples">
          <summary>Example questions</summary>
          <ul>
            {examples.map((q) => (
              <li key={q}>
                <button type="button" className="link" onClick={() => setText(q)}>{q}</button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </form>
  );
}
