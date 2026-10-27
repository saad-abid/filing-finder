// Shows a warning with the fix when something the app needs isn't running.
export default function HealthBanner({ health }) {
  if (!health || health.ready) return null;

  const problems = [];
  if (health.unreachable) {
    problems.push("The Python server isn't running. Start it with: .venv\\Scripts\\python.exe -m uvicorn src.api.app:app --reload");
  } else {
    if (!health.database) problems.push("The database isn't reachable. Open Docker Desktop and wait for \"Engine running\".");
    else if (!health.passages) problems.push("The database is empty. Run: python -m src.indexing.build_index");
    if (!health.ollama) problems.push("Ollama isn't running. Start the Ollama app.");
    else if (!health.model_installed) problems.push(`The model isn't downloaded. Run: ollama pull ${health.model}`);
  }

  return (
    <div className="banner warning" role="alert">
      <strong>Not ready yet</strong>
      <ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul>
    </div>
  );
}
