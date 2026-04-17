async function loadEvalDashboard() {
  const cards = document.getElementById("cards");
  const details = document.getElementById("details");
  const subline = document.getElementById("subline");

  try {
    const res = await fetch("/eval/latest");
    if (!res.ok) {
      details.textContent = "No evaluation output found yet. Run offline evaluation first.";
      return;
    }

    const data = await res.json();
    const summary = data.summary || {};
    const metrics = Array.isArray(summary.metrics) ? summary.metrics : [];

    subline.textContent = `${summary.retrieval_mode || "-"} • matched queries: ${summary.matched_queries ?? "-"}`;

    cards.innerHTML = metrics.map((m) => {
      const raw = m.value;
      const value =
        (typeof raw === "number") ? raw.toFixed(4) :
        (raw === null || raw === undefined) ? "N/A" : String(raw);

      return `
        <div class="card">
          <div class="label">${m.name}</div>
          <div class="value">${value}</div>
        </div>
      `;
    }).join("");

    details.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    details.textContent = `Failed to load dashboard data: ${e}`;
  }
}

loadEvalDashboard();
