import { useEffect, useState } from "react";
import { askQuestion, getExamples, getHealth, getQuestion } from "./api.js";
import HealthBanner from "./components/HealthBanner.jsx";
import QuestionBox from "./components/QuestionBox.jsx";
import Entry from "./components/Entry.jsx";
import PassagePanel from "./components/PassagePanel.jsx";

const POLL_MS = 3000;

// One "entry" per question asked in this browser tab. Nothing is saved:
// refreshing the page starts fresh (no saved history, by design).
export default function App() {
  const [health, setHealth] = useState(null);
  const [examples, setExamples] = useState([]);
  const [entries, setEntries] = useState([]);
  const [openSource, setOpenSource] = useState(null);   // a source object from an answer

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth({ unreachable: true }));
    getExamples().then(setExamples).catch(() => {});
  }, []);

  // While any question is still being answered, check on it every few seconds.
  const pending = entries.some((e) => e.status === "queued" || e.status === "running");
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => {
      entries
        .filter((e) => e.id && (e.status === "queued" || e.status === "running"))
        .forEach((e) =>
          getQuestion(e.id)
            .then((job) => update(e.key, job))
            .catch((err) => update(e.key, { status: "error", error: err.message }))
        );
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [pending, entries]);

  function update(key, changes) {
    setEntries((list) => list.map((e) => (e.key === key ? { ...e, ...changes } : e)));
  }

  async function ask(question) {
    const key = crypto.randomUUID();
    setEntries((list) => [{ key, question, status: "queued", seconds: 0, position: 0 }, ...list]);
    try {
      update(key, { id: await askQuestion(question) });
    } catch (err) {
      update(key, { status: "error", error: err.message });
    }
  }

  const busy = entries.some((e) => e.status === "queued" || e.status === "running");

  return (
    <div className={`layout ${openSource ? "with-panel" : ""}`}>
      <main>
        <header>
          <h1>FilingFinder</h1>
          <p className="subtitle">
            Ask about Apple, Amazon, Alphabet, Microsoft and NVIDIA 10-K filings (FY2021–2025).
            Every sentence is cited; click a citation to read the passage.
          </p>
        </header>

        <HealthBanner health={health} />
        <QuestionBox onAsk={ask} examples={examples} busy={busy} />

        <section className="entries">
          {entries.map((e) => (
            <Entry key={e.key} entry={e} onOpenSource={setOpenSource} openSource={openSource} />
          ))}
        </section>
      </main>

      {openSource && <PassagePanel source={openSource} onClose={() => setOpenSource(null)} />}
    </div>
  );
}
