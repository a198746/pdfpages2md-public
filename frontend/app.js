const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const rangeList = document.getElementById("rangeList");
const addRangeButton = document.getElementById("addRangeButton");
const rangePreview = document.getElementById("rangePreview");
const formatInput = document.getElementById("format");
const markerInput = document.getElementById("marker");
const ocrInput = document.getElementById("ocr");
const ocrLangInput = document.getElementById("ocrLang");
const translateInput = document.getElementById("translate");
const visionInput = document.getElementById("vision");
const deepseekApiKey = document.getElementById("deepseekApiKey");
const glmApiKey = document.getElementById("glmApiKey");
const configStatus = document.getElementById("configStatus");
const minCharsInput = document.getElementById("minChars");
const dpiInput = document.getElementById("dpi");
const convertButton = document.getElementById("convertButton");
const buttonText = document.getElementById("buttonText");
const resultMeta = document.getElementById("resultMeta");
const resultState = document.getElementById("resultState");
const resultDetail = document.getElementById("resultDetail");
const downloadButton = document.getElementById("downloadButton");
const serviceState = document.getElementById("serviceState");
const visionSwitch = visionInput.closest(".switch");

let selectedFile = null;
let convertedText = "";
let downloadName = "result.md";
let convertedFormat = "markdown";
let deepseekDirty = false;
let glmDirty = false;
let configSaveTimer = null;
let visionWasConfigured = false;
let configState = {
  deepseekConfigured: false,
  visionConfigured: false,
};

const tooltip = document.createElement("div");
tooltip.className = "tooltip";
tooltip.setAttribute("role", "tooltip");
document.body.appendChild(tooltip);

function showTooltip(target) {
  const text = target.dataset.tip;
  if (!text) {
    return;
  }
  tooltip.textContent = text;
  tooltip.classList.add("visible");

  const rect = target.getBoundingClientRect();
  const tipRect = tooltip.getBoundingClientRect();
  let top = rect.top - tipRect.height - 10;
  if (top < 8) {
    top = rect.bottom + 10;
  }
  let left = rect.left;
  if (left + tipRect.width > window.innerWidth - 8) {
    left = window.innerWidth - tipRect.width - 8;
  }
  tooltip.style.top = `${Math.max(8, top)}px`;
  tooltip.style.left = `${Math.max(8, left)}px`;
}

function hideTooltip() {
  tooltip.classList.remove("visible");
}

document.addEventListener("mouseover", (event) => {
  const target = event.target.closest?.("[data-tip]");
  if (target) {
    showTooltip(target);
  }
});

document.addEventListener("mouseout", (event) => {
  const target = event.target.closest?.("[data-tip]");
  if (target && !target.contains(event.relatedTarget)) {
    hideTooltip();
  }
});

document.addEventListener("focusin", (event) => {
  const target = event.target.closest?.("[data-tip]");
  if (target) {
    showTooltip(target);
  }
});

document.addEventListener("focusout", (event) => {
  const target = event.target.closest?.("[data-tip]");
  if (target && !target.contains(event.relatedTarget)) {
    hideTooltip();
  }
});

window.addEventListener("scroll", hideTooltip, true);
window.addEventListener("resize", hideTooltip);

function syncOcrState() {
  ocrLangInput.disabled = !ocrInput.checked;
}

ocrInput.addEventListener("change", syncOcrState);
syncOcrState();

function updateConfigStatus() {
  const deepseek = configState.deepseekConfigured
    ? "DeepSeek 已配置"
    : "DeepSeek 未配置";
  const vision = configState.visionConfigured ? "GLM 已配置" : "GLM 未配置";
  configStatus.textContent = `${deepseek} · ${vision}`;
  configStatus.classList.remove("error");
  configStatus.classList.toggle(
    "configured",
    configState.deepseekConfigured || configState.visionConfigured
  );
}

function syncVisionFromConfig() {
  const available = configState.visionConfigured;
  if (!available) {
    visionInput.checked = false;
  } else if (!visionWasConfigured) {
    visionInput.checked = true;
  }
  visionWasConfigured = available;
  visionInput.disabled = !available;
  if (visionSwitch) {
    visionSwitch.dataset.tip = available
      ? "仅对代码、表格或 OCR 质量较差的页面调用视觉模型校正版面；普通正文仍走 RapidOCR + DeepSeek。"
      : "未配置 GLM Key，视觉校正不可用。";
  }
}

async function saveApiConfig() {
  const updates = {};
  if (deepseekDirty) {
    updates.deepseek_api_key = deepseekApiKey.value;
  }
  if (glmDirty) {
    updates.glm_api_key = glmApiKey.value;
  }
  if (Object.keys(updates).length === 0) {
    return true;
  }

  try {
    const response = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "密钥保存失败");
    }
    deepseekDirty = false;
    glmDirty = false;
    configState.deepseekConfigured = Boolean(data.deepseek_configured);
    configState.visionConfigured = Boolean(data.vision_configured);
    updateConfigStatus();
    syncVisionFromConfig();
    return true;
  } catch (error) {
    configStatus.textContent = error.message;
    configStatus.classList.add("error");
    return false;
  }
}

function scheduleConfigSave() {
  clearTimeout(configSaveTimer);
  configSaveTimer = setTimeout(saveApiConfig, 600);
}

deepseekApiKey.addEventListener("input", () => {
  deepseekDirty = true;
  scheduleConfigSave();
});

glmApiKey.addEventListener("input", () => {
  glmDirty = true;
  scheduleConfigSave();
});

let rangeCounter = 0;
const MAX_RANGES = 20;

function createRangeRow(start = "", end = "") {
  const row = document.createElement("div");
  row.className = "range-row";
  row.dataset.rangeId = String(rangeCounter++);
  row.innerHTML = `
    <span class="range-label"></span>
    <input class="range-start" type="number" min="1" inputmode="numeric"
           placeholder="起始页" aria-label="起始页">
    <span class="range-sep">至</span>
    <input class="range-end" type="number" min="1" inputmode="numeric"
           placeholder="终止页" aria-label="终止页">
    <button class="range-remove" type="button" aria-label="删除此范围"
            data-tip="删除这一部分">
      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
        <path d="M6 6l12 12M18 6L6 18"></path>
      </svg>
    </button>
  `;
  row.querySelector(".range-start").value = start;
  row.querySelector(".range-end").value = end;
  row.querySelectorAll("input").forEach((input) => {
    input.addEventListener("input", () => {
      row.classList.remove("invalid");
      updateRangePreview();
    });
  });
  row.querySelector(".range-remove").addEventListener("click", () => {
    row.remove();
    renumberRanges();
    updateRangePreview();
  });
  rangeList.appendChild(row);
  renumberRanges();
  updateRangePreview();
  return row;
}

function renumberRanges() {
  const rows = Array.from(rangeList.querySelectorAll(".range-row"));
  rows.forEach((row, index) => {
    row.querySelector(".range-label").textContent = `部分 ${index + 1}`;
    const remove = row.querySelector(".range-remove");
    remove.disabled = rows.length <= 1;
  });
}

function buildRangeSpec() {
  const parts = [];
  let error = "";
  const rows = Array.from(rangeList.querySelectorAll(".range-row"));
  rows.forEach((row) => {
    const startText = row.querySelector(".range-start").value.trim();
    const endText = row.querySelector(".range-end").value.trim();
    row.classList.remove("invalid");
    if (!startText) {
      if (endText) {
        row.classList.add("invalid");
        error = "终止页不能单独填写。";
      }
      return;
    }
    const start = Number(startText);
    if (!Number.isInteger(start) || start < 1) {
      row.classList.add("invalid");
      error = "页码必须是大于 0 的整数。";
      return;
    }
    if (!endText) {
      parts.push(String(start));
      return;
    }
    const end = Number(endText);
    if (!Number.isInteger(end) || end < 1) {
      row.classList.add("invalid");
      error = "页码必须是大于 0 的整数。";
      return;
    }
    if (end < start) {
      row.classList.add("invalid");
      error = "终止页不能小于起始页。";
      return;
    }
    parts.push(start === end ? String(start) : `${start}-${end}`);
  });
  return { spec: parts.join(","), error };
}

function updateRangePreview() {
  const { spec, error } = buildRangeSpec();
  rangePreview.textContent = error || (spec ? `将读取：${spec}` : "请填写页码");
  rangePreview.classList.toggle("error", Boolean(error));
  return { spec, error };
}

addRangeButton.addEventListener("click", () => {
  if (rangeList.querySelectorAll(".range-row").length >= MAX_RANGES) {
    return;
  }
  const row = createRangeRow();
  row.querySelector(".range-start").focus();
});

createRangeRow("1", "10");
createRangeRow("50", "");

function setFile(file) {
  selectedFile = file;
  fileName.textContent = file ? file.name : "未选择文件";
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

fileInput.addEventListener("change", () => setFile(fileInput.files[0] || null));

["dragenter", "dragover"].forEach((name) => {
  dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((name) => {
  dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (file && file.type === "application/pdf") {
    setFile(file);
  }
});

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    if (response.ok && data.ok) {
      serviceState.textContent = "服务已连接";
      serviceState.className = "service-state connected";
      configState.deepseekConfigured = Boolean(data.deepseek_available);
      configState.visionConfigured = Boolean(data.vision_available);
      updateConfigStatus();
      syncVisionFromConfig();
      return;
    }
    throw new Error("service unavailable");
  } catch (error) {
    serviceState.textContent = "服务未连接";
    serviceState.className = "service-state error";
  }
}

function setLoading(loading) {
  convertButton.disabled = loading;
  convertButton.classList.toggle("loading", loading);
  buttonText.textContent = loading ? "正在转换" : "开始转换";
}

function setState(kind, message, detail = "") {
  resultState.className = `result-state ${kind}`;
  resultState.textContent = message;
  resultDetail.textContent = detail;
}

function showError(message) {
  setState("error", "转换失败", message);
  resultMeta.textContent = "转换失败";
  convertedText = "";
  downloadButton.disabled = true;
}

function downloadFile() {
  if (!convertedText) {
    return;
  }
  const mimeType = convertedFormat === "json" ? "application/json" : "text/plain";
  const blob = new Blob([convertedText], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = downloadName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function convertPdf() {
  if (!selectedFile) {
    showError("请先选择 PDF 文件。");
    return;
  }

  const { spec: pagesSpec, error: rangeError } = updateRangePreview();
  if (rangeError) {
    showError(rangeError);
    return;
  }
  if (!pagesSpec) {
    showError("请至少填写一个有效的页码范围。");
    return;
  }

  await saveApiConfig();

  const formData = new FormData();
  formData.append("file", selectedFile);
  formData.append("pages", pagesSpec);
  formData.append("format", formatInput.value);
  formData.append("marker", markerInput.value);
  formData.append("ocr", ocrInput.checked ? "true" : "false");
  formData.append("ocr_lang", ocrLangInput.value.trim() || "eng");
  formData.append("translate", translateInput.checked ? "true" : "false");
  formData.append("vision", visionInput.checked ? "true" : "false");
  formData.append("deepseek_api_key", deepseekApiKey.value);
  formData.append("glm_api_key", glmApiKey.value);
  formData.append("min_chars", minCharsInput.value);
  formData.append("dpi", dpiInput.value);

  setLoading(true);
  setState("working", "正在读取指定页面...", "");
  resultMeta.textContent = "正在转换";

  try {
    const response = await fetch("/api/convert", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "转换失败");
    }

    convertedText = data.output;
    downloadName = data.download_name;
    convertedFormat = data.format;

    downloadFile();

    const scannedNote = data.scanned_pages
      ? `，识别扫描页 ${data.ocr_pages}/${data.scanned_pages}`
      : "";
    const translateNote = data.translated_pages
      ? `，已翻译 ${data.translated_pages} 页`
      : "";
    const visionNote = data.vision_pages
      ? `，视觉校正 ${data.vision_pages} 页`
      : "";
    setState(
      "success",
      "转换完成，文件已开始下载",
      `${data.source} · 共 ${data.total_pages} 页 · 已提取 ${data.selected_pages.length} 页${scannedNote}${translateNote}${visionNote}`
    );
    resultMeta.textContent = `已生成 ${data.download_name}（${data.format}）`;
    downloadButton.disabled = false;
  } catch (error) {
    showError(error.message);
  } finally {
    setLoading(false);
  }
}

convertButton.addEventListener("click", convertPdf);

downloadButton.addEventListener("click", downloadFile);

checkHealth();
