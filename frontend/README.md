# Frontend

这是 `pdfpages2md` 的单页转换界面，由 `backend/server.py` 直接提供静态文件
服务。启动方式见根目录 `README.md` 的“本地 Web 界面”部分。

前端只通过以下 HTTP 端点与后端交互：

- `GET /api/health`：检查服务状态。
- `GET /api/config`：读取后端已保存的 DeepSeek / GLM Key 配置状态。
- `POST /api/config`：保存 DeepSeek / GLM Key 到本机后端。
- `POST /api/convert`：上传 PDF 并提交转换参数。

前端不直接导入 Python 包，也不直接访问 `pdfpages2md` 的内部模块，这样可以让
界面层与转换逻辑保持清晰边界。

界面中的 DeepSeek Key 与 GLM Key 输入框会在修改后自动保存到本机，密钥文件为
项目根目录的 `.pdfpages2md_config.json`，已被 `.gitignore` 排除。
