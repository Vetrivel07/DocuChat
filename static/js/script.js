let panelPollTimer = null;
let panelPollCollectionId = null;

(() => {
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.getElementById("backdrop");
  const openBtn = document.getElementById("openSidebarBtn");
  const closeBtn = document.getElementById("closeSidebarBtn");

  if (!sidebar || !backdrop || !openBtn || !closeBtn) return;

  function openSidebar() {
    sidebar.classList.add("open");
    sidebar.setAttribute("aria-hidden", "false");
    backdrop.hidden = false;
    requestAnimationFrame(() => backdrop.classList.add("show"));
  }

  function closeSidebar() {
    sidebar.classList.remove("open");
    sidebar.setAttribute("aria-hidden", "true");
    backdrop.classList.remove("show");
    setTimeout(() => { backdrop.hidden = true; }, 150);
  }

  openBtn.addEventListener("click", openSidebar);
  closeBtn.addEventListener("click", closeSidebar);
  backdrop.addEventListener("click", closeSidebar);

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeSidebar();
  });
})();

// Persist last active collection across refresh
const LS_ACTIVE_COLLECTION_KEY = "docuchat_active_collection";

function saveActiveCollectionId(collectionId){
  try { localStorage.setItem(LS_ACTIVE_COLLECTION_KEY, collectionId); } catch(e) {}
}

function loadActiveCollectionId(){
  try { return (localStorage.getItem(LS_ACTIVE_COLLECTION_KEY) || "").trim(); } catch(e) { return ""; }
}

function clearActiveCollectionId(){
  try { localStorage.removeItem(LS_ACTIVE_COLLECTION_KEY); } catch(e) {}
}


function escapeHtml(s) {
  return (s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// ===== Citation tooltip portal (prevents clipping inside overflow containers) =====
let citeTipEl = null;

function ensureCiteTooltipEl() {
  if (citeTipEl) return citeTipEl;
  citeTipEl = document.createElement("div");
  citeTipEl.className = "cite-tooltip-portal";
  citeTipEl.setAttribute("role", "tooltip");
  document.body.appendChild(citeTipEl);
  return citeTipEl;
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function showCiteTooltip(anchorEl) {
  const tip = (anchorEl?.getAttribute("data-tip") || "").trim();
  if (!tip) return;

  const el = ensureCiteTooltipEl();
  el.textContent = tip;
  el.classList.add("show");

  const r = anchorEl.getBoundingClientRect();
  const pad = 8;

  el.style.left = "0px";
  el.style.top = "0px";

  const tw = el.offsetWidth;
  const th = el.offsetHeight;

  const spaceBelow = window.innerHeight - r.bottom;
  const placeBelow = spaceBelow >= (th + 12);

  const left = clamp(r.left, pad, window.innerWidth - tw - pad);
  const top = placeBelow
    ? clamp(r.bottom + 10, pad, window.innerHeight - th - pad)
    : clamp(r.top - th - 10, pad, window.innerHeight - th - pad);

  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
}

function hideCiteTooltip() {
  if (!citeTipEl) return;
  citeTipEl.classList.remove("show");
}

// Delegate tooltip behavior from chatLog (works for dynamically injected messages)
const chatLogElForTips = document.getElementById("chatLog");
if (chatLogElForTips) {
  chatLogElForTips.addEventListener("mouseenter", (e) => {
    const cite = e.target.closest?.(".cite");
    if (!cite) return;
    showCiteTooltip(cite);
  }, true);

  chatLogElForTips.addEventListener("mousemove", (e) => {
    const cite = e.target.closest?.(".cite");
    if (!cite) return;
    showCiteTooltip(cite);
  }, true);

  chatLogElForTips.addEventListener("mouseleave", (e) => {
    const cite = e.target.closest?.(".cite");
    if (!cite) return;
    hideCiteTooltip();
  }, true);

  chatLogElForTips.addEventListener("focusin", (e) => {
    const cite = e.target.closest?.(".cite");
    if (!cite) return;
    showCiteTooltip(cite);
  });

  chatLogElForTips.addEventListener("focusout", (e) => {
    const cite = e.target.closest?.(".cite");
    if (!cite) return;
    hideCiteTooltip();
  });
}

window.addEventListener("scroll", hideCiteTooltip, true);
window.addEventListener("resize", hideCiteTooltip);

function buildCitationMap(sources) {
  const map = {};
  (sources || []).forEach((s) => {
    if (typeof s.source_idx === "number") {
      map[String(s.source_idx)] = s;
    }
  });
  return map;
}

function renderAnswerWithCitations(answer, sources) {
  const srcMap = buildCitationMap(sources);

  // escape first to avoid XSS
  let html = escapeHtml(answer || "");

  // replace [1] [2] with spans
  html = html.replace(/\[(\d{1,3})\]/g, (m, n) => {
    const s = srcMap[n];
    if (!s) return m;

    const label = escapeHtml(s.source_name || s.doc_id || "source");
    const page = (s.page_num !== undefined && s.page_num !== null) ? ` p.${s.page_num}` : "";
    const tipText = (s.text || "").trim();
    const tip = escapeHtml(tipText.length > 700 ? (tipText.slice(0, 700) + "…") : tipText);

    // title attribute = simplest hover tooltip
    return `<span class="cite" tabindex="0" data-tip="${label}${page}\n\n${tip}">[${n}]</span>`;
  });

  // preserve newlines as <br>
  html = html.replaceAll("\n", "<br>");

  return html;
}

// Job + polling UI
const STAGE_LABELS = {
  ingestion: "Ingestion",
  extraction: "Text Extraction",
  cleaning: "Cleaning",
  chunking: "Chunking",
  embeddings: "Embeddings + Vector Store",
  ready: "Ready for Querying",
};


const uploadPanel = document.getElementById("uploadPanel");
const processingPanel = document.getElementById("processingPanel");
const chatPanel = document.getElementById("chatPanel");

const jobIdOut = document.getElementById("jobIdOut");
const collectionIdOut = document.getElementById("collectionIdOut");
const errorOut = document.getElementById("errorOut");
const retryBtn = document.getElementById("retryBtn");
const sourceNamesOut = document.getElementById("sourceNamesOut");
const sourceNamesChat = document.getElementById("sourceNamesChat");


const activeCollection = document.getElementById("activeCollection");
const chatLog = document.getElementById("chatLog");
const stageLine = document.getElementById("stageLine");
const heroSection = document.getElementById("heroSection");

const stageStack = document.getElementById("stageStack");

let pageEl = null;

let currentCardEl = null;
let currentStageKey = null;


let lastUploadFormData = null;

const docsList = document.getElementById("docsList");

async function renderDocs(collectionId){
  if (!docsList) return;
  docsList.innerHTML = "";

  const res = await fetch(`/collections/${encodeURIComponent(collectionId)}/files`);
  if (!res.ok) {
    docsList.textContent = "-";
    return;
  }

  const data = await res.json();
  const files = Array.isArray(data.files) ? data.files : [];

  if (!files.length) {
    docsList.textContent = "-";
    return;
  }

  for (const f of files){
    const a = document.createElement("a");
    a.className = "doc-pill";
    a.href = f.download_url;
    a.textContent = f.original_filename || f.file_id;
    a.target = "_blank";
    docsList.appendChild(a);
  }
}

// Force initial UI state
document.addEventListener("DOMContentLoaded", async () => {
  pageEl = document.querySelector(".page");

  const remembered = loadActiveCollectionId();
  if (remembered && remembered !== "-") {
    activeCollection.textContent = remembered;
    await renderDocs(remembered);
    showMode("chat");
    startPanelPolling(remembered);   
  } else {
    showMode("upload");
    stopPanelPolling();             
  }
});


// add '+ file' logic
const addFilesBtn = document.getElementById("addFilesBtn");
const addFilesInput = document.getElementById("addFilesInput");

if (addFilesBtn && addFilesInput) {
  addFilesBtn.addEventListener("click", () => addFilesInput.click());

  addFilesInput.addEventListener("change", async () => {
    const files = Array.from(addFilesInput.files || []);
    if (!files.length) return;

    const collectionId = (activeCollection?.textContent || "").trim();
    if (!collectionId || collectionId === "-") return;

    const fd = new FormData();
    fd.append("collection_id", collectionId);
    for (const f of files) fd.append("files", f);

    // start a new job, same collection
    await startJob(fd); // uses /uploads; server will keep same collection_id

    // reset picker so selecting same file again triggers change
    addFilesInput.value = "";
  });
}

function iconFor(state){
  if (state === "running") return "⏳";
  if (state === "done") return "✅";
  if (state === "failed") return "❌";
  return "•";
}

function makeStageCard(stage, stage_state, message=""){
  const card = document.createElement("div");
  card.className = "stage-card";

  const ico = document.createElement("span");
  ico.className = "stage-ico";
  ico.textContent = iconFor(stage_state);

  const wrap = document.createElement("div");

  const label = document.createElement("span");
  label.className = "stage-text";
  label.textContent = STAGE_LABELS[stage] || stage || "Processing";
  wrap.appendChild(label);

  if (message){
    const sub = document.createElement("span");
    sub.className = "stage-sub";
    sub.textContent = `— ${message}`;
    wrap.appendChild(sub);
  }

  card.appendChild(ico);
  card.appendChild(wrap);
  return card;
}

function showStage(stage, stage_state, message=""){
  if (!stageStack) return;

  // if same stage, just update the current card text/icon
  if (currentCardEl && currentStageKey === stage){
    const ico = currentCardEl.querySelector(".stage-ico");
    if (ico) ico.textContent = iconFor(stage_state);

    const text = currentCardEl.querySelector(".stage-text");
    if (text) text.textContent = STAGE_LABELS[stage] || stage;

    const sub = currentCardEl.querySelector(".stage-sub");
    if (message){
      if (sub) sub.textContent = `— ${message}`;
      else{
        const newSub = document.createElement("span");
        newSub.className = "stage-sub";
        newSub.textContent = `— ${message}`;
        currentCardEl.querySelector("div")?.appendChild(newSub);
      }
    } else if (sub){
      sub.remove();
    }
    return;
  }

  // new stage: animate old out, new in
  const newCard = makeStageCard(stage, stage_state, message);
  stageStack.appendChild(newCard);
  requestAnimationFrame(() => newCard.classList.add("show"));

  if (currentCardEl){
    currentCardEl.classList.remove("show");
    currentCardEl.classList.add("leaving");
    setTimeout(() => currentCardEl?.remove(), 220);
  }

  currentCardEl = newCard;
  currentStageKey = stage;
}

async function doneAndHide(){
  if (!currentCardEl) return;

  // show ✅ briefly
  const ico = currentCardEl.querySelector(".stage-ico");
  if (ico) ico.textContent = "✅";

  await sleep(450);

  // fade/slide out
  currentCardEl.classList.remove("show");
  currentCardEl.classList.add("leaving");
  await sleep(220);

  currentCardEl?.remove();
  currentCardEl = null;
  currentStageKey = null;
}


function showMode(mode) {
  uploadPanel.hidden = (mode !== "upload");
  processingPanel.hidden = (mode !== "processing");
  chatPanel.hidden = (mode !== "chat");


  if (heroSection) {
    heroSection.style.display = (mode === "chat") ? "none" : "";
  }
  
  const pageElNow = document.querySelector(".page");
  if (pageElNow) pageElNow.classList.toggle("chat-mode", mode === "chat");
  document.body.classList.toggle("chat-lock", mode === "chat");

}

// Vanish button: delete current collection on server + clear browser state
const vanishBtn = document.getElementById("vanishBtn");

if (vanishBtn) {
  vanishBtn.addEventListener("click", async () => {
    const collectionId = (activeCollection?.textContent || "").trim() || loadActiveCollectionId();

    // Always clear client state first (UI reset is guaranteed)
    clearActiveCollectionId();
    stopPanelPolling();

    const panelEl = document.getElementById("side-panel");
    if (panelEl) panelEl.innerHTML = `<div>No collection loaded. Upload documents to start.</div>`;

    // Reset UI to upload mode
    if (chatLog) chatLog.innerHTML = "";
    if (docsList) docsList.innerHTML = "";
    if (activeCollection) activeCollection.textContent = "-";
    showMode("upload");

    // If we have a collection id, ask server to delete that workspace
    if (!collectionId || collectionId === "-") return;

    try {
      await fetch(`/collections/${encodeURIComponent(collectionId)}`, { method: "DELETE" });
    } catch (e) {
      
    }
  });
}


function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}
function stageText(stage){
  return `⏳ ${STAGE_LABELS[stage] || stage}...`;
}

async function swapStageLine(stage){
  if (!stageLine) return;

  // fade out
  stageLine.classList.remove("fade-in");
  stageLine.classList.add("fade-out");
  await sleep(450);

  // change text
  stageLine.textContent = stageText(stage);

  // fade in
  stageLine.classList.remove("fade-out");
  stageLine.classList.add("fade-in");
}


async function startJob(fd) {
  errorOut.textContent = "";
  retryBtn.hidden = true;

  const res = await fetch("/uploads", { method: "POST", body: fd });
  if (!res.ok) {
    errorOut.textContent = `Upload failed (HTTP ${res.status})`;
    showMode("upload");
    return;
  }

  const data = await res.json();
  const { job_id, collection_id } = data;

  jobIdOut.textContent = job_id;
  collectionIdOut.textContent = collection_id;

  if (stageLine) {
    stageLine.textContent = "⏳ Starting...";
    stageLine.classList.remove("fade-out");
    stageLine.classList.add("fade-in");
  }


  if (stageStack) stageStack.innerHTML = "";
  currentCardEl = null;
  currentStageKey = null;

  showMode("processing");
  await pollJob(job_id, collection_id);
}

async function pollJob(jobId, collectionId) {
  let pollMs = 1000;
  const started = Date.now();
  let lastStage = null;
  let lastStageState = null;

  while (true) {
    const res = await fetch(`/jobs/${encodeURIComponent(jobId)}/status`);
    if (!res.ok) {
      showStage("ingestion", "failed", `Status HTTP ${res.status}`);

      retryBtn.hidden = false;
      return;
    }

    const st = await res.json();
    if (sourceNamesOut) {
      const names = Array.isArray(st.source_names) ? st.source_names : [];
      const namesText = names.length ? names.join(", ") : "-";

      if (sourceNamesOut) sourceNamesOut.textContent = namesText;
      if (sourceNamesChat) sourceNamesChat.textContent = namesText;

    }

    // st: {state, current_stage, stage_state, message, done_stages, collection_id, ...}
    const stage = st.current_stage || "ingestion";
    const stageState = st.stage_state || "running";
    const msg = st.message || "";

    if (stage !== lastStage) {
      await swapStageLine(stage);
      lastStage = stage;
    }

    if (st.state === "failed" || stageState === "failed") {
      errorOut.textContent = st.message || "Job failed";
      if (stageLine) stageLine.textContent = "❌ Failed";
      retryBtn.hidden = false;
      return;
    }


   if (st.state === "ready" || stage === "ready") {
    activeCollection.textContent = collectionId;
    saveActiveCollectionId(collectionId);
    await renderDocs(collectionId);
    showMode("chat");
    startPanelPolling(collectionId);   
    return;
  }


    // backoff after 10s
    if (Date.now() - started > 10000) pollMs = 2000;
    await sleep(pollMs);
  }
}

retryBtn.addEventListener("click", () => {
  if (!lastUploadFormData) return;
  showMode("upload");
});

document.getElementById("uploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);
  lastUploadFormData = fd;

  // reset outputs
  jobIdOut.textContent = "-";
  collectionIdOut.textContent = "-";
  errorOut.textContent = "";

  await startJob(fd);
});

// Chat (stub endpoint; implement /query later)
document.getElementById("chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = document.getElementById("chatInput").value.trim();
  if (!q) return;

  // render user bubble
  const userDiv = document.createElement("div");
  userDiv.className = "chat-msg user";
  userDiv.textContent = q;
  chatLog.appendChild(userDiv);

  document.getElementById("chatInput").value = "";

  const col = activeCollection.textContent;

  const res = await fetch("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ collection_id: col, question: q }),
  });

  const botDiv = document.createElement("div");
  botDiv.className = "chat-msg bot";

  if (!res.ok) {
    botDiv.textContent = `Error (HTTP ${res.status})`;
    } else {
    const data = await res.json();

    const answer = (data.answer || "").trim() || "(no answer)";
    const sources = Array.isArray(data.sources) ? data.sources : [];

    // build a small readable response
    // let out = answer;

    // if (sources.length) {
    //   out += "\n\nSources:";
    //   sources.forEach((s, i) => {
    //     const name = s.source_name || s.doc_id || "unknown";
    //     const page = (s.page_num !== undefined && s.page_num !== null) ? ` p.${s.page_num}` : "";
    //     const score = (typeof s.score === "number") ? ` score=${s.score.toFixed(3)}` : "";
    //     out += `\n${i + 1}. ${name}${page}${score}`;
    //   });
    // }

    // botDiv.textContent = out;
    
    const html = renderAnswerWithCitations(answer, sources);
    botDiv.innerHTML = html;
  }


  chatLog.appendChild(botDiv);
  chatLog.scrollTop = chatLog.scrollHeight;
});

// side panel:

async function fetchPanel(collectionId) {
  const cid = encodeURIComponent((collectionId || "").trim());
  const res = await fetch(`/collections/${cid}/panel`);
  if (!res.ok) return null;
  return await res.json();
}

function bytesToMB(n) {
  if (!n || n <= 0) return "0 MB";
  return (n / (1024 * 1024)).toFixed(2) + " MB";
}



function stopPanelPolling() {
  if (panelPollTimer) {
    clearInterval(panelPollTimer);
    panelPollTimer = null;
  }
  panelPollCollectionId = null;
}

function startPanelPolling(collectionId) {
  const panelEl = document.getElementById("side-panel");
  if (!panelEl) return;

  const cid = (collectionId || "").trim();
  if (!cid || cid === "-") {
    stopPanelPolling();
    panelEl.innerHTML = `<div>No collection loaded. Upload documents to start.</div>`;
    return;
  }

  // avoid creating multiple intervals for same collection
  if (panelPollTimer && panelPollCollectionId === cid) return;

  // switching collections: stop previous polling
  stopPanelPolling();
  panelPollCollectionId = cid;

  async function tick() {
    const data = await fetchPanel(cid);
    if (!data) {
      panelEl.innerHTML = `<div>Panel endpoint not available yet (check /collections/${cid}/panel)</div>`;
      return;
    }

    if (data.state === "no_collection") {
      panelEl.innerHTML = `<div>No collection loaded. Upload documents to start.</div>`;
      return;
    }

    const p = data.processing || {};
    const e = data.embedding || {};
    const i = data.index || {};
    const h = data.health || {};

    const stage = (p.current_stage || "-").toString();
const status = (p.job_status || "-").toString();

const statusClass =
  status === "done" || status === "ready" ? "ok" :
  status === "running" || status === "processing" ? "run" :
  status === "failed" ? "bad" : "";

const avoidance = (e.embedding_avoidance_rate_pct ?? "-");
const embedded = (e.chunks_embedded ?? "-");
const skipped = (e.chunks_skipped ?? "-");

const barPct = (typeof avoidance === "number")
  ? Math.max(0, Math.min(100, avoidance))
  : 0;

panelEl.innerHTML = `
    <div class="sp-head">
      <div class="sp-title">Workspace Metrics</div>
      <div class="sp-pill ${statusClass}">
        <span class="dot"></span>
        <span>${status.toUpperCase()}</span>
      </div>
    </div>

    <div class="sp-grid">

      <div class="sp-card">
        <div class="sp-card-h">
          <div class="sp-card-title">Processing</div>
          <div class="sp-mini">Stage</div>
        </div>

        <div class="sp-rows">
          <div class="sp-row"><div class="sp-k">Stage</div><div class="sp-v">${stage}</div></div>
          <div class="sp-row"><div class="sp-k">Total Docs</div><div class="sp-v">${p.total_docs ?? "-"}</div></div>
        </div>
      </div>

      <div class="sp-card">
        <div class="sp-card-h">
          <div class="sp-card-title">Embedding</div>
          <div class="sp-mini">Cache impact</div>
        </div>

        <div class="sp-rows">
          <div class="sp-row"><div class="sp-k">Avoidance</div><div class="sp-v">${avoidance}%</div></div>
          <div class="sp-bar"><span style="width:${barPct}%"></span></div>
          <div class="sp-row"><div class="sp-k">SQLite Hits</div><div class="sp-v">${e.sqlite_hits ?? "-"}</div></div>
          <div class="sp-row"><div class="sp-k">Embedded / Skipped</div><div class="sp-v">${embedded} / ${skipped}</div></div>
          <div class="sp-row"><div class="sp-k">Wall Time</div><div class="sp-v">${e.rerun_wall_time_s ?? "-"} s</div></div>
          <div class="sp-row"><div class="sp-k">Time Saved (est)</div><div class="sp-v">${e.embedding_time_saved_s_est ?? "-"} s</div></div>
        </div>
      </div>

      <div class="sp-card">
        <div class="sp-card-h">
          <div class="sp-card-title">Index</div>
          <div class="sp-mini">Vector store</div>
        </div>

        <div class="sp-rows">
          <div class="sp-row"><div class="sp-k">Total Vectors</div><div class="sp-v">${i.total_vectors ?? "-"}</div></div>
          <div class="sp-row"><div class="sp-k">Dim</div><div class="sp-v">${i.vector_dimension ?? "-"}</div></div>
          <div class="sp-row"><div class="sp-k">Metric</div><div class="sp-v">${i.metric_type ?? "-"}</div></div>
          <div class="sp-row"><div class="sp-k">Indexed Docs</div><div class="sp-v">${i.indexed_docs_count ?? "-"}</div></div>
        </div>
      </div>

      <div class="sp-card">
        <div class="sp-card-h">
          <div class="sp-card-title">System</div>
          <div class="sp-mini">Storage</div>
        </div>

        <div class="sp-rows">
          <div class="sp-row"><div class="sp-k">Cache DB</div><div class="sp-v">${bytesToMB(h.cache_db_size_bytes)}</div></div>
          <div class="sp-row"><div class="sp-k">Vector File</div><div class="sp-v">${bytesToMB(h.vector_file_size_bytes)}</div></div>
          <div class="sp-row"><div class="sp-k">Total Storage</div><div class="sp-v">${bytesToMB(h.collection_storage_bytes)}</div></div>
        </div>
      </div>

    </div>
  `;
  }

  tick();
  panelPollTimer = setInterval(tick, 2000);
}