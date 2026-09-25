/* Barcode Reader frontend — upload / live camera / results / history / catalog / analytics */
const $ = (id) => document.getElementById(id);
const drop = $("drop"), fileInput = $("fileInput"), preview = $("preview"),
  cam = $("cam"), scanBtn = $("scanBtn"), snapBtn = $("snapBtn"),
  statusPill = $("statusPill"), statusText = $("statusText"),
  footText = $("footText"), resList = $("resList"), resCount = $("resCount"),
  summaryBox = $("summaryBox"), summaryText = $("summaryText"),
  emptyMsg = $("emptyMsg");

let currentFile = null, lastDetections = [], stream = null, mode = "upload";

function setStatus(t, busy = false) {
  statusText.textContent = t;
  statusPill.classList.toggle("busy", busy);
}

/* ---------- view switching ---------- */
document.querySelectorAll(".nav-btn").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    const v = b.dataset.view;
    document.querySelectorAll(".view").forEach((s) => s.classList.remove("active"));
    $("view-" + v).classList.add("active");
    if (v === "history") loadHistory();
    if (v === "catalog") loadCatalog();
    if (v === "analytics") loadAnalytics();
  });
});

/* ---------- tabs ---------- */
$("tabUpload").addEventListener("click", () => setMode("upload"));
$("tabLive").addEventListener("click", () => setMode("live"));
async function setMode(m) {
  mode = m;
  $("tabUpload").classList.toggle("active", m === "upload");
  $("tabLive").classList.toggle("active", m === "live");
  drop.classList.toggle("live", m === "live");
  snapBtn.style.display = m === "live" ? "" : "none";
  if (m === "live") {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      cam.srcObject = stream;
      await cam.play();
      footText.textContent = "Live camera on — frame the code and Capture";
    } catch (e) {
      footText.textContent = "Camera blocked: " + e.message;
    }
  } else {
    if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
    cam.srcObject = null;
  }
}

/* ---------- file handling ---------- */
drop.addEventListener("click", (e) => { if (mode === "upload") fileInput.click(); });
$("changeBtn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) setFile(fileInput.files[0]);
});
["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); }));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  if (mode !== "upload") return;
  const f = e.dataTransfer.files[0];
  if (f) setFile(f);
});
function setFile(f) {
  currentFile = f;
  preview.src = URL.createObjectURL(f);
  preview.style.display = "block";
  drop.classList.add("has-file");
  footText.textContent = f.name + " — ready. Press Scan now.";
  setStatus("Ready to scan");
}
snapBtn.addEventListener("click", async () => {
  if (!cam.videoWidth) return;
  const c = document.createElement("canvas");
  c.width = cam.videoWidth; c.height = cam.videoHeight;
  c.getContext("2d").drawImage(cam, 0, 0);
  const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.92));
  setFile(new File([blob], "camera-frame.jpg", { type: "image/jpeg" }));
  setMode("upload");
  $("tabUpload").classList.add("active"); $("tabLive").classList.remove("active");
};

/* ---------- scan ---------- */
scanBtn.addEventListener("click", async () => {
  if (!currentFile) { footText.textContent = "Choose an image first."; return; }
  scanBtn.disabled = true;
  setStatus("Scanning…", true);
  footText.textContent = "Uploading → Roboflow YOLO → ZXing-Java decode…";
  const fd = new FormData();
  fd.append("image", currentFile);
  try {
    const r = await fetch("/api/scan", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Scan failed");
    lastDetections = j.detections || [];
    preview.src = j.annotated_image;
    preview.style.display = "block";
    drop.classList.add("has-file");
    renderResults(j);
    setStatus(`Done — ${j.summary}`);
    footText.textContent = j.summary;
  } catch (e) {
    setStatus("Scan failed");
    footText.textContent = "Error: " + e.message;
  } finally { scanBtn.disabled = false; }
});

function badge(i, type) {
  const cls = type === "QR" ? "blue" : "green";
  return `<span class="idx ${cls}">#${i}</span>`;
}
function renderResults(j) {
  const dets = j.detections || [];
  resCount.textContent = dets.length;
  summaryBox.style.display = dets.length ? "" : "none";
  emptyMsg.style.display = dets.length ? "none" : "";
  const bc = dets.filter((d) => d.type === "BARCODE").length;
  const qr = dets.filter((d) => d.type === "QR").length;
  summaryText.textContent = `${dets.length} code(s) detected simultaneously (${bc} barcode(s), ${qr} QR)`;
  resList.innerHTML = dets.map((d, k) => `
    <div class="res">
      <div class="res-top">
        ${badge(d.id, d.type)}
        <span class="fmt">${escapeHtml(d.format)}</span>
        <span class="tag ${d.type === "QR" ? "qr" : ""}">${d.type === "QR" ? "▦ QR Code" : "📦 Barcode"}</span>
        <span class="st ${d.valid ? "" : "bad"}">${d.valid ? (d.type === "QR" ? "Decoded" : "✓ Valid") : "✕ Invalid"}</span>
      </div>
      <div class="data">${escapeHtml(d.data)}</div>
      <div class="note">${escapeHtml(d.note || "")}</div>
      <div class="note">Read with ${d.source === "ml" ? "Roboflow YOLO + enhanced crop" : "Original Image"} · conf ${d.confidence}</div>
      <div class="actions">
        <button onclick="copyOne(${k})">Copy data</button>
        <button onclick="findProduct('${escapeHtml(d.data)}')">Find product ↗</button>
      </div>
    </div>`).join("");
}
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
window.copyOne = async (k) => {
  const d = lastDetections[k];
  if (d) await navigator.clipboard.writeText(d.data);
};
window.findProduct = (code) => {
  document.querySelector('[data-view="catalog"]').click();
  $("catSearch").value = code;
  loadCatalog(code);
};
$("copyAllBtn").addEventListener("click", async () => {
  await navigator.clipboard.writeText(lastDetections.map((d) => d.data).join("\n"));
});
$("clearBtn").addEventListener("click", () => {
  lastDetections = []; resList.innerHTML = "";
  resCount.textContent = "0"; summaryBox.style.display = "none"; emptyMsg.style.display = "";
  setStatus("Ready to scan");
});

/* ---------- history / catalog / analytics ---------- */
async function loadHistory() {
  const r = await fetch("/api/history?limit=100");
  const rows = await r.json();
  $("historyBody").innerHTML = rows.length ? rows.map((s) =>
    `<tr><td>${s.id}</td><td>${escapeHtml(s.filename)}</td><td>${s.codes_found}</td><td>${s.barcodes}</td><td>${s.qr_codes}</td><td>${(s.created_at || "").slice(0, 19).replace("T", " ")}</td></tr>`).join("")
    : `<tr><td colspan="6">No scans yet.</td></tr>`;
}
$("clearHistoryBtn").addEventListener("click", async () => {
  await fetch("/api/history", { method: "DELETE" });
  loadHistory();
});
async function loadCatalog(q = $("catSearch").value.trim()) {
  const r = await fetch("/api/catalog?q=" + encodeURIComponent(q || ""));
  const rows = await r.json();
  $("catalogBody").innerHTML = rows.length ? rows.map((p) =>
    `<tr><td>${escapeHtml(p.code)}</td><td>${escapeHtml(p.name)}</td><td>${escapeHtml(p.brand)}</td><td>${escapeHtml(p.category)}</td></tr>`).join("")
    : `<tr><td colspan="4">No products. Add the decoded value above.</td></tr>`;
}
$("catSearch").addEventListener("input", () => loadCatalog());
$("addProductBtn").addEventListener("click", async () => {
  const body = { code: $("pCode").value.trim(), name: $("pName").value.trim(), brand: $("pBrand").value.trim(), category: $("pCat").value.trim() };
  if (!body.code) return alert("Code is required");
  const r = await fetch("/api/catalog", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) { const j = await r.json(); return alert(j.error || "Failed"); }
  $("pCode").value = $("pName").value = $("pBrand").value = $("pCat").value = "";
  loadCatalog("");
});
async function loadAnalytics() {
  const r = await fetch("/api/analytics");
  const a = await r.json();
  $("stScans").textContent = a.total_scans;
  $("stCodes").textContent = a.total_codes;
  $("stMix").textContent = `${a.barcodes} / ${a.qr_codes}`;
  $("stRate").textContent = a.success_rate + "%";
  $("analyticsBody").innerHTML = (a.recent || []).map((s) =>
    `<tr><td>${s.id}</td><td>${escapeHtml(s.filename)}</td><td>${s.codes_found}</td><td>${(s.created_at || "").slice(0, 19).replace("T", " ")}</td></tr>`).join("")
    || `<tr><td colspan="4">No data.</td></tr>`;
}
fetch("/health").then((r) => r.json()).then((j) => { $("engineLabel").textContent = j.engine || "ZXing-Java engine"; }).catch(() => {});
