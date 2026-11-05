/**
 * Application entry point: wires the focused modules together and performs the
 * initial service health check.
 */
import { initApiConfig } from "./js/api-config.js";
import { initConverter } from "./js/converter.js";
import { initFileDrop } from "./js/file-drop.js";
import { initRangeInputs } from "./js/range-input.js";
import { initTooltips } from "./js/tooltip.js";

const el = (id) => document.getElementById(id);

initTooltips();

const rangeInputs = initRangeInputs({
  list: el("rangeList"),
  addButton: el("addRangeButton"),
  preview: el("rangePreview"),
});

const fileDrop = initFileDrop({
  dropzone: el("dropzone"),
  fileInput: el("fileInput"),
  fileName: el("fileName"),
});

const apiConfig = initApiConfig({
  deepseekInput: el("deepseekApiKey"),
  glmInput: el("glmApiKey"),
  configStatus: el("configStatus"),
  visionInput: el("vision"),
  visionSwitch: el("vision").closest(".switch"),
});

initConverter({
  elements: {
    formatInput: el("format"),
    markerInput: el("marker"),
    ocrInput: el("ocr"),
    ocrLangInput: el("ocrLang"),
    translateInput: el("translate"),
    visionInput: el("vision"),
    deepseekApiKey: el("deepseekApiKey"),
    glmApiKey: el("glmApiKey"),
    minCharsInput: el("minChars"),
    dpiInput: el("dpi"),
    convertButton: el("convertButton"),
    buttonText: el("buttonText"),
    resultMeta: el("resultMeta"),
    resultState: el("resultState"),
    resultDetail: el("resultDetail"),
    downloadButton: el("downloadButton"),
  },
  getFile: fileDrop.getFile,
  getRangeSpec: rangeInputs.getSpec,
  saveConfig: apiConfig.save,
});

const serviceState = el("serviceState");

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    if (response.ok && data.ok) {
      serviceState.textContent = "服务已连接";
      serviceState.className = "service-state connected";
      apiConfig.applyAvailability(data.deepseek_available, data.vision_available);
      return;
    }
    throw new Error("service unavailable");
  } catch (error) {
    serviceState.textContent = "服务未连接";
    serviceState.className = "service-state error";
  }
}

checkHealth();
