/**
 * Tooltip helper: shows one shared tooltip for any element with `data-tip`.
 */
export function initTooltips() {
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
}
