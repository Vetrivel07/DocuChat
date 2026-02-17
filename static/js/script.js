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
    // restore last workspace
    activeCollection.textContent = remembered;
    await renderDocs(remembered);
    showMode("chat");
  } else {
    showMode("upload");
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
      // ignore network failures; UI already reset
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
    let out = answer;

    if (sources.length) {
      out += "\n\nSources:";
      sources.forEach((s, i) => {
        const name = s.source_name || s.doc_id || "unknown";
        const page = (s.page_num !== undefined && s.page_num !== null) ? ` p.${s.page_num}` : "";
        const score = (typeof s.score === "number") ? ` score=${s.score.toFixed(3)}` : "";
        out += `\n${i + 1}. ${name}${page}${score}`;
      });
    }

    botDiv.textContent = out;
  }


  chatLog.appendChild(botDiv);
  chatLog.scrollTop = chatLog.scrollHeight;
});

