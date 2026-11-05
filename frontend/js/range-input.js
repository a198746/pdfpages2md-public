/**
 * Page-range editor: builds the `1-10,50,88-95` spec sent to the backend and
 * keeps the live preview in sync with the inputs.
 */
const MAX_RANGES = 20;

export function initRangeInputs({ list, addButton, preview }) {
  let counter = 0;

  function createRow(start = "", end = "") {
    const row = document.createElement("div");
    row.className = "range-row";
    row.dataset.rangeId = String(counter++);
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
        updatePreview();
      });
    });
    row.querySelector(".range-remove").addEventListener("click", () => {
      row.remove();
      renumber();
      updatePreview();
    });
    list.appendChild(row);
    renumber();
    updatePreview();
    return row;
  }

  function renumber() {
    const rows = Array.from(list.querySelectorAll(".range-row"));
    rows.forEach((row, index) => {
      row.querySelector(".range-label").textContent = `部分 ${index + 1}`;
      const remove = row.querySelector(".range-remove");
      remove.disabled = rows.length <= 1;
    });
  }

  function buildSpec() {
    const parts = [];
    let error = "";
    const rows = Array.from(list.querySelectorAll(".range-row"));
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

  function updatePreview() {
    const { spec, error } = buildSpec();
    preview.textContent = error || (spec ? `将读取：${spec}` : "请填写页码");
    preview.classList.toggle("error", Boolean(error));
    return { spec, error };
  }

  addButton.addEventListener("click", () => {
    if (list.querySelectorAll(".range-row").length >= MAX_RANGES) {
      return;
    }
    const row = createRow();
    row.querySelector(".range-start").focus();
  });

  createRow("1", "10");
  createRow("50", "");

  return { getSpec: updatePreview };
}
