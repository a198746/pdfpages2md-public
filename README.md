# pdfpages2md

只读超大 PDF 的指定页码，并转换为便于大模型消费的 Markdown（也可输出纯文本或
JSON）。底层复用 PyMuPDF 与 pymupdf4llm 的按页懒加载能力，因此内存占用与
“你选了多少页”相关，而不是与“PDF 总共有多少页”相关。

## 项目结构

当前代码按前后端边界整理：

```text
backend/
  pdfpages2md/          # 后端核心库与 CLI 入口
    __init__.py         # 对外导出 convert / extract_pages / render 等
    cli.py              # 命令行入口与参数解析
    extract.py          # 按页提取管线（OCR / 视觉 / 翻译调度）
    models.py           # PageResult / ConvertResult 数据结构
    render.py           # Markdown / 文本 / JSON 渲染
    ranges.py           # 页码范围解析
    config.py           # 环境变量与 .env 的统一配置解析
    ocr.py              # OCR 后端与扫描页判定
    ocr_layout.py       # 扫描页排版还原（代码围栏）
    ocr_cleanup.py      # 代码块清洗与语言识别
    code.py             # 文字层代码页还原
    translate.py        # 英译中后端（DeepSeek）
    vision.py           # 视觉模型兜底（可选）
    web/                # 本地 HTTP 服务
      app.py            # 参数解析与服务启动
      handler.py        # 路由、静态资源与 JSON 响应
      service.py        # 转换编排与临时文件清理
      multipart.py      # multipart 上传解析
      config_store.py   # 本机 API Key 持久化
      paths.py          # frontend / 配置文件路径
  server.py             # 兼容入口，转发到 pdfpages2md.web
  tests/                # 后端单元测试与样例 PDF 生成器
frontend/
  index.html            # 单页转换界面
  app.js                # 前端入口，组合下列模块
  js/
    tooltip.js          # 共享提示气泡
    range-input.js      # 页码范围编辑器
    api-config.js       # API Key 保存与状态
    file-drop.js        # 文件选择 / 拖放
    converter.js        # 转换请求、下载与结果状态
  styles.css            # 前端样式
  README.md             # 前端说明
examples/               # 转换输出示例
.env.example            # DeepSeek / 视觉模型配置模板
```

- `backend/pdfpages2md/` 是当前已经完成的 Python 包，负责页码范围解析、按页
  提取、扫描页 OCR、代码页与扫描页排版还原、英译中、视觉模型兜底、
  Markdown/JSON 渲染和命令行入口。提取、渲染与 Web 服务按职责拆分，
  新增输出格式只需扩展 `render.py`，新增可选后端只需在 `extract.py` 的
  管线中加一个阶段。
- `backend/pdfpages2md/web/` 只使用 Python 标准库提供本地 HTTP 服务，不额外
  依赖 Flask/FastAPI；`backend/server.py` 保留为兼容启动入口。
- `frontend/app.js` 通过标准 ES 模块组合 `frontend/js/` 下的功能模块，只通过
  `/api/*` 调用后端，不直接访问后端内部实现。
- `.env.example` 提供 DeepSeek 与视觉模型配置模板；复制为 `.env` 后按需填写
  密钥即可，`.env` 已被 `.gitignore` 排除。

## 特性

- 精确到页的选择：`--pages "1-10,50,88-95"` 或 `--page-range "5-20"`。
- 每页保留原始 PDF 页码标记：`<!-- page 100 -->`，方便大模型追溯来源。
- 只加载所选页，不遍历整份 PDF，适合超大文件。
- 自动判定扫描页（无有效文本层），并自动对**目标扫描页**做 OCR（可用
  `--no-ocr` 关闭）。扫描页按首行缩进、行距和右边界还原原始段落，避免逐行
  断段，也避免把段首缩进的正文误判成标题；中文换行不会插入多余空格。
- 自动识别代码页：文字层 PDF 按等宽字体/坐标还原，扫描版 PDF 按 RapidOCR
  文本框坐标还原；去掉左侧行号、保留缩进，并输出为 Markdown 围栏代码块
  （如 ```c / ```shell），命令输出也会归入同一个代码块；翻译时不会改写代码
  内容。
- 英译中：`--translate` 把提取到的英文翻译成简体中文，保留标题、列表、表格
  与代码围栏，围栏代码块原样保留。
- 视觉模型兜底：仅对代码页、表格页、OCR 置信度低或明显漏行的扫描页调用视觉
  模型，普通正文仍走 RapidOCR + DeepSeek。
- 页面中的图片不参与 OCR，但会在输出里保留 `<!-- 此处为图片 -->` 占位（纯文本
  格式为 `[此处为图片]`），避免图片被静默丢弃。
- 输出 Markdown（默认）、纯文本或 JSON，并支持按字符/页边界分块。

## 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .
```

`pyproject.toml` 同时提供可选依赖组，可一次性安装，例如
`pip install -e ".[rapidocr]"`。可用组为 `ocr`、`rapidocr`。

核心依赖：

```text
pymupdf>=1.24
pymupdf4llm>=0.0.23
```

可选 OCR（二选一）：

```bash
pip install pytesseract            # 需要系统安装 Tesseract 并在 PATH 中
# 或
pip install rapidocr-onnxruntime   # 自带 ONNX 运行时，无需系统二进制
```

扫描版代码页的排版还原依赖 RapidOCR 的文本框坐标；如果使用 Tesseract，仍可
识别文字，但代码区域会退化为普通文本。

## 用法

```bash
# 只转换第 100–110 页，输出 Markdown 到文件
python -m pdfpages2md huge.pdf --pages "100-110" -o out.md

# 多段页码 + 显式保留页码标记（默认 comment 风格）
python -m pdfpages2md huge.pdf --pages "1-10,50,88-95"

# 输出 JSON，便于程序化消费
python -m pdfpages2md huge.pdf --pages "88-95" -f json -o out.json

# 扫描页会自动 OCR（需要 OCR 后端）；如不需要可加 --no-ocr
python -m pdfpages2md scan.pdf --pages "3,7" --ocr-lang chi_sim

# 每 3000 字符切分一个文件（按页边界，不切断单页）
python -m pdfpages2md huge.pdf --pages "1-50" --chunk-size 3000 -o part.md

# 只查看总页数
python -m pdfpages2md huge.pdf --info
```

`--pages` 支持 `5`、`5-20`、`5-`（到末尾）、`-10`（从第 1 页开始）、`all`
以及逗号组合 `1-10,50,88-95`。页码均为 1-based（PDF 实际页码）。

页码标记风格由 `--marker` 控制：`comment`（默认，`<!-- page N -->`）、
`heading`（`## Page N`）、`both` 或 `none`。

## 翻译（英译中）

在转换时加 `--translate`，即可把提取到的英文翻译成简体中文，并保留页面编号、
标题、列表、表格等 Markdown 结构后重新排版输出：

```bash
# 提取并翻译为中文 Markdown
python -m pdfpages2md huge.pdf --pages "100-110" --translate -o out.zh.md
```

翻译后端只保留 **DeepSeek**（OpenAI 兼容的 `chat/completions` 接口）。使用时
先在项目根目录创建一个 `.env` 文件（可复制 `.env.example`），填入你的密钥：

```text
DEEPSEEK_API_KEY=sk-你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TEMPERATURE=0.2
```

也可以不建文件，直接设置系统环境变量 `DEEPSEEK_API_KEY`（Windows PowerShell：
`$env:DEEPSEEK_API_KEY="sk-你的密钥"`，或持久化用
`setx DEEPSEEK_API_KEY "sk-你的密钥"`）。`.env` 文件已被加入 `.gitignore`，
不会误提交密钥。也可以在网页界面直接填写 DeepSeek API Key，前端会把它保存到
本机后端配置（`.pdfpages2md_config.json`，同样被 `.gitignore` 排除）。

未配置 `DEEPSEEK_API_KEY` 时，`--translate` 会在输出中保留原文并给出明确提示，
不会中断提取流程。翻译默认只做英文到简体中文（`en` → `zh`）；围栏代码块会原样
保留，不会被翻译或重排。

## 视觉模型兜底（可选）

普通正文继续使用 `RapidOCR + DeepSeek`。只有**代码页、表格页、OCR 置信度低或
明显漏行**的页面才调用视觉模型，避免全量走视觉模型带来的高成本。配置密钥后
默认开启，命令行可用 `--no-vision` 关闭。

在 `.env` 中填入视觉模型配置（默认使用智谱 GLM-4V-Flash）：

```text
VISION_API_KEY=你的视觉模型密钥
VISION_BASE_URL=https://open.bigmodel.cn/api/paas/v4
VISION_MODEL=glm-4v-flash
VISION_TIMEOUT=120
VISION_MAX_TOKENS=1024
```

也可以换成通义 Qwen-VL 等 OpenAI 兼容接口，例如：

```text
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_MODEL=qwen-vl-plus
```

视觉模型只负责把页面转写成 Markdown（保留代码块和表格，不翻译）；后续正文翻译仍
由 DeepSeek 完成。未配置 `VISION_API_KEY` 时该能力自动跳过。

## 本地 Web 界面

```bash
python backend/server.py --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000>，选择 PDF、填写页码范围并转换，转换结果会作为
文件直接下载。服务默认只监听本机地址；API 端点为 `POST /api/convert`、`GET
/api/config`、`POST /api/config` 和 `GET /api/health`。`POST /api/convert` 使用
`multipart/form-data` 接收 `file`、`pages`、`format`、`marker`、`ocr`、
`ocr_lang`、`min_chars`、`dpi`、`translate`、`vision`、`deepseek_api_key`、
`glm_api_key` 字段（`ocr` 默认开启，扫描页会自动识别；勾选“英译中”后会返回
翻译后的中文内容；勾选“视觉校正”后仅对代码、表格或低质量 OCR 页调用视觉模型）。
网页端可以填写 DeepSeek Key 与 GLM Key，输入后会自动保存到本机后端。
网页端页码范围支持多段输入：每个“部分”填写起始页和终止页，只填起始页表示
单页；可点击“添加范围”继续追加，最终会自动合并为 `1-10,50,88-95` 形式。

### 一键启动 / 停止（Windows）

后端同时提供前端静态文件，因此部署只需启动一个进程：

```powershell
# 双击 deploy.cmd，或在 PowerShell 中运行
powershell -ExecutionPolicy Bypass -File .\deploy.ps1

# 停止
.\stop.cmd
```

`deploy.ps1` 会按需安装依赖、在后台启动服务、等待 `/api/health` 通过，并把
进程号写入 `.server.pid`；运行日志写入 `.logs/`（两者均已加入 `.gitignore`）。
重复运行是安全的：服务已在运行时只会提示地址，不会重复启动。

默认监听 `127.0.0.1:8000`，仅本机可访问。需要让同一局域网的其他设备访问时：

```powershell
.\deploy.cmd -ListenHost 0.0.0.0 -Port 8000
```

注意：该服务没有登录鉴权，并会保存 API Key；只应在可信网络中开放，且不要
直接暴露到公网。

## 超大 PDF 下的内存策略

- 打开文档只读取 Header、xref/交叉引用流与页面树，不读取页面内容。
- 通过 `doc.load_page(n - 1)` 按需加载目标页，内容流按页解析后即可释放。
- OCR 只对“被判定为扫描页”的目标页渲染一次位图，绝不预跑整份 PDF。
- 分块输出按页边界累计字符数，避免把单个页面从中间切开。

实测（本机，520 页构造样本）：

```text
python -m pdfpages2md backend/tests/sample_520.pdf --pages "100-110" -o out.md
# 约 2.6 秒（含 Python 启动），内存与所选 11 页相关
```

## 与现有工具的差异

见 [RESEARCH.md](RESEARCH.md)。一句话概括：`pymupdf4llm` 是引擎、`llmPDF`
是功能接近但更重且许可证受限的同类 CLI；本项目把它们之间的空白（轻量、
AGPL-3.0 开源、严格“只碰所选页”、页码标记）补齐。

## 许可证说明

本项目整体以 **GNU Affero General Public License v3.0（AGPL-3.0）** 发布，
完整许可证文本见 [LICENSE](LICENSE)。

项目依赖的 PyMuPDF / pymupdf4llm 采用 AGPL-3.0 或 Artifex 商业许可双授权；
本项目按 AGPL-3.0 使用它们。若你希望在不遵守 AGPL 的条件下使用本项目，需要
自行向 Artifex 购买 PyMuPDF 商业许可，或替换掉 PyMuPDF/pymupdf4llm。

第三方依赖的许可证与版权声明见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 测试

```bash
python -m unittest discover -s backend/tests -t backend -v

# 构造 520 页样本并跑端到端示例
python backend/tests/make_sample_pdf.py
python -m pdfpages2md backend/tests/sample_520.pdf --pages "100-110" -o examples/pages_100_110.md
```

测试覆盖页码范围解析、按页提取、文字层代码页还原、扫描页 OCR 排版还原、
英译中以及视觉模型兜底；样例 PDF 由 `make_sample_pdf.py` 与
`make_code_sample.py` 生成。

