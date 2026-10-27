// Small helpers for talking to the Python server (src/api/app.py).

async function request(path, options) {
  const res = await fetch(path, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? "Please type a question (3–500 characters)." : body.detail;
    throw new Error(detail || `Server error ${res.status}`);
  }
  return body;
}

export const getHealth = () => request("/api/health");

export const getExamples = () => request("/api/examples");

// Returns a ticket id straight away; the answer is fetched with getQuestion.
export const askQuestion = (question) =>
  request("/api/questions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  }).then((body) => body.id);

export const getQuestion = (id) => request(`/api/questions/${id}`);
