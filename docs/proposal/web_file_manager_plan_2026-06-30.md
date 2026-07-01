# WebUI 文件管理页面设计方案

日期：2026-06-30

## 目标

在现有 WebUI 顶部菜单中新增一个“文件管理”页面，用纯 HTTP 能力提供容器内数据目录浏览与基础文件操作，重点解决两类场景：

- 上传数据集到容器内目录，并支持解压 tar 包、同目录重命名。
- 浏览并下载训练产物，尤其是训练好的 `.safetensors` 模型文件。

本方案明确不依赖 WebSocket。所有交互均使用普通 HTTP 请求、文件上传和状态轮询完成。

## 已确认需求

### 浏览与路径范围

- 页面名称：`文件管理`
- 浏览方式：只展示当前目录一层内容，逐层点击进入，不做整树递归。
- 支持面包屑返回上层目录。
- 支持手填路径跳转。
- 支持当前目录内搜索。

允许访问的根目录：

- `/home`
- 当前 WebUI 训练输出根目录

训练输出根目录不写死，必须按当前代码实际解析结果动态获取。现状如下：

- WebUI 全局设置默认 `output_root = "output/runs"`。
- WebUI 启动训练时，会在 `resolve_output_root()` 下创建独立运行目录。
- 每次运行的训练产物目录为 `<run_dir>/training_output/`。

因此文件管理页应把“训练输出根目录”作为一个固定入口，而不是直接暴露某个写死路径。

### 上传

- 支持两种上传目标指定方式：
  - 浏览到某目录后上传到当前目录。
  - 手填目标路径上传。
- 初版只做普通单次上传，不做分片、断点续传。
- 数据集压缩包规模上限按 `2GB` 设计，模型文件通常为几百 MB。
- 上传时显示浏览器原生进度条。
- 如果目标文件已存在，允许覆盖。

### 解压 tar

- 支持 `.tar`、`.tar.gz`、`.tgz`。
- 支持“上传完成后自动解压”，但默认关闭。
- 解压采用两步 HTTP：
  - 预检查冲突
  - 用户确认后执行
- 默认不覆盖已有文件；只有用户确认后才允许覆盖。

### 下载

- 初版只支持单文件下载。
- 核心目标是下载训练好的 `.safetensors` 模型。
- 不支持目录打包下载。

### 重命名

- 支持文件重命名。
- 支持目录重命名。
- 只允许同目录内改名，不支持跨目录移动。
- 名称冲突时报错，不自动覆盖。

### 符号链接

- 初版完全禁止跟随 symlink。
- 列表中可标记这是符号链接。
- 不允许进入符号链接目录。
- 不允许对符号链接执行上传目标、下载、解压、重命名等操作。

### 默认开放策略

- 文件管理页面默认开启。
- 不增加额外的后端开关作为第一版前提条件。

## 非目标

以下内容不在第一版范围内：

- 浏览整个容器文件系统。
- 修改 `/etc`、`/proc`、`/sys`、`/dev`、`/root` 等系统目录。
- 删除文件或目录。
- 目录打包下载。
- 分片上传、断点续传、秒传。
- 通过 WebSocket 推送上传或解压进度。
- 跨目录移动文件或目录。

## 现有代码库事实

### Web 结构

当前 WebUI 后端是 `aiohttp`，统一在 `web/server.py` 建应用和注册路由。前端是 ES module 模块化结构，顶层 tab 切换集中在 `web/static/js/features/app-shell/tabs.js`，新增一个菜单页签是现有扩展方式。

### 已有可复用能力

- HTTP 文件下载：`web/routes/preview.py` 已有 `web.FileResponse` 下载实现。
- HTTP 文件上传：`web/static/js/features/weight-analysis/api.js` 已有 `FormData` 上传先例。
- 轮询：训练状态已有定时 polling 先例，不依赖 WebSocket。
- 输出根目录边界：`web/services/settings_service.py::resolve_output_root()` 已是当前 WebUI 的统一根目录解析方式。

### 当前上传大小限制

`web/server.py` 目前 `client_max_size = 512 * 1024 * 1024`，只有 512MB，无法满足 2GB 数据集压缩包上传需求。第一版必须把这个限制提升到至少 3GB 以上，并同步检查部署侧 ingress / proxy 限制。

## 设计原则

- 只做数据目录管理，不做通用系统文件浏览器。
- HTTP first：上传用浏览器原生上传进度，长操作用任务轮询。
- 根目录显式白名单，所有路径都要收敛到允许根内。
- UI 初版简洁，以单层目录列表为主，不做复杂树视图。
- 先做稳定的文件操作，再考虑批量操作或高级能力。

## 信息架构

### 顶部菜单

在现有导航栏新增：

- `文件管理`

对应新增 tab：

- `#tab-file-manager`

### 页面布局

建议采用三段布局：

1. 顶部工具栏
- 根目录切换：`/home`、`训练输出`
- 路径面包屑
- 手填路径输入框 + 跳转按钮
- 当前目录刷新按钮

2. 左侧操作区
- 上传文件
- 上传目标路径输入
- “上传完成后自动解压”复选框
- 解压 tar 操作面板
- 重命名操作面板

3. 右侧列表区
- 当前目录文件/目录列表
- 当前目录搜索
- 每项操作按钮：进入、下载、重命名、解压

## 安全边界

### 允许根目录

文件管理后端只允许访问以下根：

- `home`: `/home`
- `training_output_root`: `resolve_output_root()`

后端对外不直接信任前端路径，而是：

- 先根据根目录 id 解析根路径
- 再将用户传入相对路径或绝对路径标准化
- 最终用 `Path.resolve()` 与 `relative_to()` 校验是否仍在允许根内

### 禁止事项

- 禁止 `..` 越界。
- 禁止跟随 symlink。
- 禁止将 symlink 作为任何操作目标。
- 禁止对根目录之外路径执行读写。
- 禁止把压缩包解压到允许根外。

### 操作白名单

第一版只允许：

- 列目录
- 单文件上传
- tar 解压
- 文件/目录同目录重命名
- 单文件下载

不提供删除，避免与现有用户数据保护原则冲突。

## 后端方案

### 新增路由

建议新增文件：

- `web/routes/file_manager.py`

并在 `web/routes/__init__.py` 中注册。

建议 HTTP API：

#### 1. 根目录列表

```text
GET /api/file-manager/roots
```

返回：

- `home`
- `training_output_root`

示例：

```json
{
  "ok": true,
  "roots": [
    { "id": "home", "label": "/home", "path": "/home" },
    { "id": "training_output", "label": "训练输出", "path": "output/runs" }
  ]
}
```

#### 2. 目录列表

```text
GET /api/file-manager/list?root=home&path=/home/foo
```

返回当前目录一层内容：

- `name`
- `path`
- `kind`
- `size`
- `mtime`
- `ext`
- `is_symlink`

#### 3. 上传文件

```text
POST /api/file-manager/upload
multipart/form-data
```

表单字段：

- `root`
- `target_path`
- `file`
- `extract_after_upload` 可选

行为：

- 流式写入目标目录下临时文件
- 写完后原子覆盖到最终文件
- 如果勾选自动解压，上传成功后返回解压预检查结果或创建解压任务

#### 4. 解压预检查

```text
POST /api/file-manager/extract/plan
```

请求：

```json
{
  "root": "home",
  "archive_path": "/home/datasets/foo.tar.gz",
  "target_dir": "/home/datasets",
  "overwrite": false
}
```

返回：

- tar 内文件总数
- 目标目录
- 冲突数量
- 冲突样例
- 是否允许执行

#### 5. 执行解压

```text
POST /api/file-manager/extract/run
```

返回：

- `job_id`

#### 6. 查询任务状态

```text
GET /api/file-manager/jobs/{job_id}
```

用于轮询解压状态：

- `queued`
- `running`
- `done`
- `error`

可返回：

- 已处理文件数
- 总文件数
- 当前阶段
- 错误信息

#### 7. 重命名

```text
POST /api/file-manager/rename
```

请求：

```json
{
  "root": "home",
  "path": "/home/datasets/foo",
  "new_name": "foo_v2"
}
```

限制：

- 只能同目录改名
- 不支持移动

#### 8. 下载单文件

```text
GET /api/file-manager/download?root=training_output&path=...
```

返回：

- `web.FileResponse`
- 带 `Content-Disposition`

### 新增服务

建议新增文件：

- `web/services/file_manager_service.py`

按职责划分函数：

- `list_roots()`
- `list_directory(root_id, path)`
- `upload_file(...)`
- `plan_extract(...)`
- `start_extract_job(...)`
- `get_job_status(job_id)`
- `rename_entry(...)`
- `resolve_download_file(...)`

内部辅助函数：

- `_allowed_roots()`
- `_resolve_root(root_id)`
- `_resolve_managed_path(root_id, raw_path)`
- `_reject_symlink(path)`
- `_path_is_relative_to(path, root)`
- `_safe_archive_members(...)`

### 解压实现

推荐使用 Python 标准库 `tarfile`，并显式防止 tar path traversal：

- 不允许成员路径为绝对路径
- 不允许成员路径包含 `..`
- 解压前逐个成员解析目标路径并校验仍在允许根内

### 任务模型

由于不能使用 WebSocket，解压任务使用内存态 job store 即可作为第一版：

- `app["file_manager_jobs"]`
- job 内容包含：
  - `id`
  - `kind`
  - `state`
  - `created_at`
  - `updated_at`
  - `current`
  - `total`
  - `message`
  - `error`

第一版只需要支持当前 Web 进程内的短生命周期任务，不要求跨重启恢复。

## 前端方案

### 模块结构

建议新增：

```text
web/static/js/features/file-manager/
  api.js
  index.js
  render.js
  state.js
```

如样式较多，再新增：

```text
web/static/css/file-manager.css
```

并从 `web/static/style.css` 引入。

### 交互模型

#### 目录浏览

- 进入 tab 后加载根目录和默认入口。
- 默认显示当前目录一层列表。
- 点击目录进入。
- 点击面包屑返回。
- 手填路径后跳转。

#### 上传

- 文件选择框
- 目标路径输入框
- “上传到当前目录”快捷选项
- tar 文件时显示“上传完成后自动解压”复选框
- 上传进度使用 `XMLHttpRequest.upload.onprogress`

#### 解压

- 用户可对已上传 tar 文件点击“解压”
- 第一步调用 `extract/plan`
- 弹出确认框显示冲突摘要
- 用户确认后调用 `extract/run`
- 前端开始轮询任务状态

#### 下载

- 单文件按钮直接跳转下载 URL

#### 重命名

- 每个文件/目录项提供“重命名”
- 弹出输入框
- 提交到 `rename`
- 成功后刷新当前目录

## 与现有代码的整合点

### 导航

修改：

- `web/static/index.html`
- `web/static/js/features/app-shell/tabs.js`

新增 `data-tab="file-manager"` 和对应 tab section。

### 页面初始化

可参考现有 feature 延迟加载模式，在 tab 激活时初始化文件管理模块。

### 上传大小

修改：

- `web/server.py`

将 `MAX_UPLOAD_BYTES` 从 512MB 提高到至少 3GB，建议值：

```python
MAX_UPLOAD_BYTES = 3 * 1024 * 1024 * 1024
```

同时应在文档中提醒部署方同步检查：

- ingress body size
- 反向代理上传限制
- 浏览器与 LB 超时

## API 错误语义

建议统一返回：

- `400`：参数非法
- `403`：越界路径、symlink、非法目标
- `404`：目标不存在
- `409`：重命名冲突、解压冲突
- `500`：未预期错误

前端统一把错误显示到页面状态栏或操作反馈区。

## 第一版验收标准

功能验收：

- 能在 `/home` 下逐层浏览目录
- 能进入“训练输出根目录”并下载单个模型文件
- 能上传几百 MB 模型文件
- 能上传 2GB 级 tar 数据集压缩包
- 能显示上传进度
- 能对 tar 进行预检查解压
- 能在用户确认后执行解压
- 能轮询解压状态
- 能对文件和目录做同目录重命名
- 不能越界到允许根目录之外
- 不能跟随 symlink

## 测试与验证建议

### 后端

建议新增：

- `tests/test_file_manager_service.py`
- `tests/test_file_manager_routes.py`

覆盖点：

- 根目录白名单解析
- 路径越界拦截
- symlink 拦截
- tar 成员路径安全检查
- 同目录重命名冲突
- 单文件下载
- 轮询任务状态

### 前端

建议在现有 Web 前端状态测试中补最小覆盖：

- tab 切换
- 列表刷新
- 上传表单基本事件
- 解压确认流程

## 分阶段实施建议

### 阶段 1

- 后端只做 `/home` 与训练输出根目录的只读浏览
- 单文件下载
- 基础前端页面与导航接入

### 阶段 2

- 文件上传
- 同目录重命名

### 阶段 3

- tar 解压预检查
- 解压任务轮询
- 上传后自动解压

## 最终建议

第一版应把“文件管理”明确定位为：

- 数据集导入辅助工具
- 训练产物下载入口

而不是通用 Linux 文件浏览器。

按这个边界实现，既能满足当前真实需求，又能复用现有 WebUI 的 HTTP、轮询和输出目录安全模型，避免把功能快速做成高风险的系统级文件管理器。
