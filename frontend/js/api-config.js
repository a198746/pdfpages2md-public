/**
 * API-key management: debounced save to the local backend plus the derived
 * status labels and the availability of the vision switch.
 */
export function initApiConfig({
  deepseekInput,
  glmInput,
  configStatus,
  visionInput,
  visionSwitch,
}) {
  let deepseekDirty = false;
  let glmDirty = false;
  let configSaveTimer = null;
  let visionWasConfigured = false;
  const state = {
    deepseekConfigured: false,
    visionConfigured: false,
  };

  function updateConfigStatus() {
    const deepseek = state.deepseekConfigured ? "DeepSeek 已配置" : "DeepSeek 未配置";
    const vision = state.visionConfigured ? "GLM 已配置" : "GLM 未配置";
    configStatus.textContent = `${deepseek} · ${vision}`;
    configStatus.classList.remove("error");
    configStatus.classList.toggle(
      "configured",
      state.deepseekConfigured || state.visionConfigured
    );
  }

  function syncVisionFromConfig() {
    const available = state.visionConfigured;
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

  async function save() {
    const updates = {};
    if (deepseekDirty) {
      updates.deepseek_api_key = deepseekInput.value;
    }
    if (glmDirty) {
      updates.glm_api_key = glmInput.value;
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
      state.deepseekConfigured = Boolean(data.deepseek_configured);
      state.visionConfigured = Boolean(data.vision_configured);
      updateConfigStatus();
      syncVisionFromConfig();
      return true;
    } catch (error) {
      configStatus.textContent = error.message;
      configStatus.classList.add("error");
      return false;
    }
  }

  function scheduleSave() {
    clearTimeout(configSaveTimer);
    configSaveTimer = setTimeout(save, 600);
  }

  deepseekInput.addEventListener("input", () => {
    deepseekDirty = true;
    scheduleSave();
  });

  glmInput.addEventListener("input", () => {
    glmDirty = true;
    scheduleSave();
  });

  return {
    save,
    /** Apply the availability flags reported by /api/health. */
    applyAvailability(deepseekAvailable, visionAvailable) {
      state.deepseekConfigured = Boolean(deepseekAvailable);
      state.visionConfigured = Boolean(visionAvailable);
      updateConfigStatus();
      syncVisionFromConfig();
    },
  };
}
