/**
 * PDF selection: click-to-browse plus drag-and-drop on the dropzone.
 */
export function initFileDrop({ dropzone, fileInput, fileName }) {
  let selectedFile = null;

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

  return { getFile: () => selectedFile };
}
