# Frontend

这是 `pdfpages2md` 的单页转换界面，由本地后端直接提供静态文件服务。启动方式
见根目录 `README.md` 的“本地 Web 界面”部分。

前端使用原生 ES 模块，不需要构建步骤：

```text
index.html      页面结构
app.js          入口：查询 DOM、初始化各模块、做健康检查
js/tooltip.js   共享提示气泡
js/range-input.js  页码范围编辑器与预览
js/api-config.js   DeepSeek / GLM Key 保存与可用状态
js/file-drop.js    文件选择与拖放
js/converter.js    转换请求、下载与结果状态
styles.css      样式
```

新增交互时优先在 `js/` 下增加独立模块，并在 `app.js` 中组合；不要把请求逻辑
写进页面结构或样式文件。

前端只通过以下 HTTP 端点与后端交互：

- `GET /api/health`：检查服务状态。
- `GET /api/config`：读取后端已保存的 DeepSeek / GLM Key 配置状态。
- `POST /api/config`：保存 DeepSeek / GLM Key 到本机后端。
- `POST /api/convert`：上传 PDF 并提交转换参数。

前端不直接导入 Python 包，也不直接访问 `pdfpages2md` 的内部模块，这样可以让
界面层与转换逻辑保持清晰边界。

界面中的 DeepSeek Key 与 GLM Key 输入框会在修改后自动保存到本机，密钥文件为
项目根目录的 `.pdfpages2md_config.json`，已被 `.gitignore` 排除。
