/**
 * Conversion flow: collect the form, call /api/convert, download the result and
 * report progress. All DOM lookups happen in app.js so this module stays a
 * plain controller.
 */
export function initConverter({ elements, getFile, getRangeSpec, saveConfig }) {
  const {
    formatInput,
    markerInput,
    ocrInput,
    ocrLangInput,
    translateInput,
    visionInput,
    deepseekApiKey,
    glmApiKey,
    minCharsInput,
    dpiInput,
    convertButton,
    buttonText,
    resultMeta,
    resultState,
    resultDetail,
    downloadButton,
  } = elements;

  let convertedText = "";
  let downloadName = "result.md";
  let convertedFormat = "markdown";

  function syncOcrState() {
    ocrLangInput.disabled = !ocrInput.checked;
  }

  ocrInput.addEventListener("change", syncOcrState);
  syncOcrState();

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
    const selectedFile = getFile();
    if (!selectedFile) {
      showError("请先选择 PDF 文件。");
      return;
    }

    const { spec: pagesSpec, error: rangeError } = getRangeSpec();
    if (rangeError) {
      showError(rangeError);
      return;
    }
    if (!pagesSpec) {
      showError("请至少填写一个有效的页码范围。");
      return;
    }

    await saveConfig();

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

  return { convertPdf, downloadFile };
}
