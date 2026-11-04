# 检索与评估报告：超大 PDF 部分页码识别与格式转换

本报告对应需求中的“强制工作流第 1 步”。在动手编码前，我在 PyPI 与 GitHub
上对候选工具做了检索，并核对了它们的版本、许可证、页码选择方式、OCR 能力与
对超大文件的处理策略。检索时间：2026-10-25。

## 1. 候选工具对比

| 工具 | 语言/生态 | 是否真正支持指定页码 | 扫描版 OCR | 输出格式 | 超大文件表现 | 许可证 |
| --- | --- | --- | --- | --- | --- | --- |
| **sahaf** (`arikusi/sahaf`, PyPI `sahaf` 0.2.3) | Python | 是，但通过 HTTP API 的 `page_from` / `page_to` 参数，而非独立 CLI | 是，Marker + Surya OCR（90+ 语言），自动数字/扫描检测 | Markdown + 图片 | 重：加载 Marker/Surya 模型，偏“整书”处理，内存开销大 | GPL-3.0-or-later |
| **swiper** (`onedusk/swiper`) | Go / GitHub | 是，CLI `-pages 1-10,50` | 否（底层 poppler-utils，只抽文本层） | Markdown + 图片 | 并行友好，但作为 Go 二进制不便嵌入 Python 流程 | 仓库未标注主流许可证（Go 生态） |
| **llmPDF** (`yechenyan/llmPDF`, PyPI `llmpdf` 0.7.1) | Python | 是，CLI `--pages "1,3,8-12"`，并保留原始页码 | 是，继承 Docling 的 OCR 选项 | Markdown（保留页码） | 中偏重：Docling 驱动，会渲染“覆盖所选页的最小连续物理页范围”（例如 `1,3,8-12` 实际处理 1–12），内存并非严格与单页成正比 | llmPDF Limited Use License 1.0（受限使用许可证） |
| **pymupdf4llm** (`pymupdf/RAG`, PyPI `pymupdf4llm` 2.0) | Python | 是，库 API `to_markdown(doc, pages=[...])`，PyMuPDF 按页懒加载 | 可选 RapidOCR | Markdown / JSON / 分块 / 文本 | 轻：内存与所选页数相关，而非总页数 | AGPL-3.0（或 Artifex 商业许可） |
| **pdf-mcp** (`jztan/pdf-mcp`, PyPI `pdf-mcp` 3.5.0) | Python / MCP server | 是，但以“语义/关键词检索驱动”的选择性页面读取为主，不是 `--pages` 风格 CLI | 是，Tesseract（并行） | Markdown / 表格 / 图片 / TOC | 良好：SQLite 缓存 + 按需解析 | MIT |
| **markitdown** (`microsoft/markitdown`, PyPI `markitdown` 0.1.9) | Python | 部分：以整文档转换为主，PDF 页码选择是次要参数 | 否（pdfminer.six 文本抽取） | Markdown | 整文档加载（pdfminer） | MIT |

说明：`swiper` 与 `markitdown` 的仓库细节在检索时受 GitHub API 限流影响，未能
逐行核对当前源码；表中结论依据其公开描述与既有实现方式，供选型参考。

## 2. 判断

**结论：采用“封装/组合现有工具”的方案，而非从零实现 PDF 底层解析器。**

理由与缺口：

1. `pymupdf4llm` 已经提供了正确且经过验证的底层能力：`pages=[...]` 精确选页、
   Markdown 输出、可选 OCR、以及基于 PyMuPDF 的按页懒加载（内存与所选页数相关）。
   这正是需求中“只读指定页、不加载全文”的核心引擎。

2. 但 `pymupdf4llm` 是一个**库**，缺少面向大模型的直接交付形态：
   没有 `--pages "1-10,50,88-95"` 风格的 CLI，也没有在输出里显式保留
   “原始 PDF 页码标记”的约定。它还是 AGPL-3.0。

3. `llmPDF` 在“CLI + 页码保留”上与需求最接近，但有两个关键缺口：
   一是它基于 Docling，模型/依赖重，且会处理覆盖选择的最小连续物理页范围，
   超大文件下并非严格“只碰所选页”；二是其受限使用许可证限制修改与再分发，
   不利于通用落地。

4. 其余候选各有明显不匹配：`sahaf` 是重模型服务 + GPL；`swiper` 是非 Python
   二进制；`pdf-mcp` 是检索型 MCP 服务而非简单页码 CLI；`markitdown` 偏整文档。

因此，本项目实现一个**轻量、AGPL-3.0 的 CLI/库**，底层复用 PyMuPDF + pymupdf4llm
（不重写 xref/页面树解析），只补齐四个真实缺口：

- 精确到页的 `--pages` 页码范围 CLI；
- 每页保留 `<!-- page N -->` 原始页码标记；
- 扫描页检测 + 按需（且仅对目标扫描页）执行的可插拔 OCR；
- 面向 LLM 上下文窗口的按字符/页边界分块输出。

## 3. 与现有工具的关系

| 工具 | 本项目相对它的关系 |
| --- | --- |
| pymupdf4llm | 直接复用为提取引擎，向上补齐 CLI 与页码标记 |
| llmPDF | 功能对齐，但更轻量、许可证更宽松、严格“只碰所选页” |
| sahaf / swiper | 作为“重量级 OCR / 高性能 Go CLI”的互补替代 |
| pdf-mcp | 面向 Agent 的检索型读取，与本项目的“显式页码精确抽取”互补 |
| markitdown | 整文档通用转换器，与“部分页码抽取”定位不同 |

