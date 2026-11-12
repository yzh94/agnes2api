# Agnes2API

OpenAI / Gemini 兼容的 **Agnes** AI 中转服务。

支持：
- **Agnes Image 2.1 Flash** - 图像生成（文生图 / 图生图）
- **Agnes 2.5 Flash** - 文本聊天（流式 / 非流式、工具调用、图像理解、Thinking 模式）
- **Agnes Video** - 视频生成（文生视频 / 图生视频）
- **Gemini 兼容接口** - Google Gemini 原生格式文本对话

将标准的 OpenAI / Gemini API 请求转换为 Agnes 厂商格式并转发，让用户可通过 OpenAI SDK、Gemini SDK 或兼容客户端直接调用 Agnes 服务。

---

## 目录

- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [项目结构](#项目结构)
- [API 接口文档](#api-接口文档)
  - [聊天完成 (Chat)](#1-聊天完成-chat)
  - [图像生成 (Images)](#2-图像生成-images)
  - [视频生成 (Video)](#3-视频生成-video)
  - [Gemini 兼容接口](#4-gemini-兼容接口)
  - [Responses API](#41-responses-api)
  - [图片代理 (Proxy)](#5-图片代理-proxy)
  - [系统接口 (System)](#6-系统接口-system)
  - [模型列表 (Models)](#7-模型列表-models)
  - [管理后台 API (Management)](#8-管理后台-api-management)
- [性能优化](#性能优化)
- [API Key 智能降级机制](#api-key-智能降级机制)
- [反向代理部署](#反向代理部署)
- [健康检查](#健康检查)
- [License](#license)

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env`，填入必要的配置项：

```env
# ============================================
# 上游 Agnes API 配置
# ============================================
AGNES_BASE_URL=https://apihub.agnes-ai.com

# ============================================
# 服务配置
# ============================================
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# 本服务 API Key 认证（留空则不启用认证）
# 启用后客户端需在请求头携带: Authorization: Bearer <SERVER_API_KEY>
SERVER_API_KEY=

# ============================================
# 数据库配置（必需）
# MySQL 示例: mysql+aiomysql://user:pass@host:3306/dbname
DATABASE_URL=mysql+aiomysql://root:password@localhost:3306/agnes2api

# ============================================
# Redis 配置（必需）
# ============================================
# 用于 Key Pool 管理、统计、速率限制、认证缓存
REDIS_CONN_STRING=redis://localhost:6379/0

# ============================================
# 管理后台 JWT 签名秘钥（必需，至少 32 字符）
# ============================================
JWT_SECRET=your_super_secret_jwt_key_here_at_least_32_chars

# ============================================
# 请求超时（秒）
# ============================================
REQUEST_TIMEOUT=300

# ============================================
# 性能优化配置
# ============================================
ENABLE_PARALLEL_CALLS=true
ENABLE_CACHE=false
CACHE_MAX_SIZE=1000
CACHE_TTL=3600
CACHE_KEY_PREFIX=agnes2api

# ============================================
# Docker 部署配置
# ============================================
DEV_MODE=false
UVICORN_WORKERS=4
```

### 3. 启动服务

```bash
python main.py
```

或使用 uvicorn：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

服务启动后访问以下地址：
- **API 文档**: http://localhost:8000/docs （FastAPI Swagger UI）
- **管理后台**: http://localhost:8000/ （前端面板，需登录）

首次部署且数据库中尚无 `admin` 用户时，使用以下默认账号登录即可自动创建管理员：

| 项目 | 值 |
|---|---|
| 账号 | `admin` |
| 密码 | `admin123` |

登录成功后请立即修改密码。该引导仅在 `admin` 用户不存在时生效。

### 4. 调用示例

#### 聊天完成（非流式）

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.5-flash",
    "messages": [
      {"role": "user", "content": "Explain how autonomous agents use tools."}
    ]
  }'
```

> 如果启用了 `SERVER_API_KEY`，需添加 `-H "Authorization: Bearer your-service-api-key"`。

#### 聊天完成（流式输出）

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.5-flash",
    "messages": [{"role": "user", "content": "Write a poem"}],
    "stream": true
  }'
```

#### 图像生成

```bash
curl http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "A cute cat on a cloud at sunset",
    "size": "1024x768",
    "n": 1
  }'
```

#### 文本补全（Completions）

```bash
curl http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.5-flash",
    "prompt": "Write a short poem about the sea",
    "max_tokens": 256
  }'
```

`prompt` 支持字符串或字符串数组；`stream: true` 时返回 OpenAI 补全格式的 SSE 流。

#### 图像编辑（Edits，multipart）

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Content-Type: multipart/form-data" \
  -F "model=agnes-image-2.1-flash" \
  -F "image=@photo.png" \
  -F "prompt=make it a cartoon" \
  -F "size=1024x1024" \
  -F "n=1"
```

#### 视频生成（创建任务）

```bash
curl http://localhost:8000/v1/video/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "A serene lake at dawn with mist",
    "duration": 5,
    "width": 1152,
    "height": 768
  }'
```

返回 `task_id`，然后通过以下接口轮询状态：

```bash
curl http://localhost:8000/v1/video/generations/<task_id>
```

`POST /v1/video/generations` 使用 New API 通用格式，创建返回 `{task_id, status}`，
查询返回 `{task_id, status, url, format, metadata, error}`；`POST /v1/videos`
（Sora 格式）与 `GET /v1/videos/{task_id}/content`（流式回传）保持兼容。

#### Gemini 兼容接口（非流式）

```bash
curl http://localhost:8000/v1beta/models/agnes-2.5-flash:generateContent \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {"role": "user", "parts": [{"text": "Hello!"}]}
    ]
  }'
```

#### 使用 OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",  # 若启用 SERVER_API_KEY，此处填写该 Key
)

# 聊天完成
response = client.chat.completions.create(
    model="agnes-2.5-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)

# 图像生成
image_response = client.images.generate(
    model="agnes-image-2.1-flash",
    prompt="A beautiful sunset",
    size="1024x768",
)
print(image_response.data[0].url)
```

#### Responses API（非流式）

```bash
curl http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.5-flash",
    "input": "Explain how autonomous agents use tools.",
    "max_output_tokens": 1024
  }'
```

流式：

```bash
curl http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.5-flash",
    "input": [{"role": "user", "content": "Write a poem"}],
    "stream": true
  }'
```

---

## 环境变量

| 变量 | 说明 | 默认值 | 必需 |
|---|---|---|---|
| `AGNES_BASE_URL` | Agnes API 基地址 | `https://apihub.agnes-ai.com` | 否 |
| `SERVER_HOST` | 服务监听地址 | `0.0.0.0` | 否 |
| `SERVER_PORT` | 服务监听端口 | `8000` | 否 |
| `SERVER_API_KEY` | 本服务 API Key 认证（留空则不启用） | 空 | 否 |
| `DATABASE_URL` | 数据库连接字符串（MySQL） | — | **是** |
| `REDIS_CONN_STRING` | Redis 连接字符串（Key Pool / 统计 / 限流） | — | **是** |
| `JWT_SECRET` | 管理后台 JWT 签名秘钥（≥32 字符） | — | **是** |
| `REQUEST_TIMEOUT` | 上游请求超时（秒） | `300` | 否 |
| `ENABLE_PARALLEL_CALLS` | 并行调用开关（图片模型 n>1 时生效） | `true` | 否 |
| `ENABLE_CACHE` | 请求缓存开关 | `false` | 否 |
| `CACHE_MAX_SIZE` | 缓存最大条目数（LRU 淘汰） | `1000` | 否 |
| `CACHE_TTL` | 缓存过期时间（秒） | `3600` | 否 |
| `CACHE_KEY_PREFIX` | 缓存键前缀 | `agnes2api` | 否 |
| `DEV_MODE` | 开发模式（启用热重载） | `false` | 否 |
| `UVICORN_WORKERS` | 生产模式 Worker 数 | `1` | 否 |
| `VIDEO_DEFAULT_MODEL` | 默认视频模型 | `agnes-video-v2.0` | 否 |
| `VIDEO_DEFAULT_DURATION` | 默认视频时长（秒） | `5.0` | 否 |
| `VIDEO_DEFAULT_WIDTH` | 默认视频宽度 | `1152` | 否 |
| `VIDEO_DEFAULT_HEIGHT` | 默认视频高度 | `768` | 否 |
| `VIDEO_DEFAULT_FPS` | 默认视频帧率 | `24` | 否 |
| `VIDEO_TASK_EXPIRE_SECONDS` | 视频任务缓存过期时间（秒） | `3600` | 否 |
| `STATS_DAILY_RESET_ENABLED` | 是否启用每日统计重置 | `true` | 否 |
| `STATS_DAILY_RESET_TIME` | 每日重置时刻（本地时区 HH:MM） | `00:00` | 否 |

---

## 项目结构

```
agnes2api/
├── main.py                    # FastAPI 入口（生命周期管理、中间件、路由注册）
├── config.py                  # 配置管理（Pydantic Settings，从 .env / 环境变量加载）
├── requirements.txt           # Python 依赖
├── .env.example               # 环境变量模板
├── Dockerfile                 # 多阶段 Docker 构建（前端 + 后端）
├── docker-compose.yml         # Docker Compose 部署配置
├── alembic.ini                # Alembic 迁移配置
│
├── models/                    # 数据模型
│   ├── database.py            # SQLAlchemy ORM 模型（User, ClientKey, UpstreamKey, UsageLog 等）
│   ├── openai.py              # OpenAI Images API 请求/响应模型
│   ├── openai_chat.py         # OpenAI Chat Completions API 请求/响应模型
│   ├── agnes.py               # Agnes Image API 请求/响应模型
│   └── video.py               # 视频模型请求/响应模型
│
├── service/                   # 业务逻辑层
│   ├── auth.py                # API Key 认证（支持配置匹配 + DB/Redis 查询）
│   ├── cache.py               # 请求缓存（LRU + TTL，内存实现）
│   ├── transformer.py         # 图像请求/响应转换 & 上游调用
│   ├── chat_transformer.py    # 聊天请求/响应转换 & 流式转发
│   ├── video.py               # 视频服务（任务创建、状态查询、帧数调整）
│   ├── upstream_client.py     # 上游 HTTP 客户端（自动换 Key / 重试 / 失败统计）
│   ├── redis_key_pool.py      # Redis 分布式 Key Pool 管理器（轮询 / 降级 / 健康检查）
│   ├── redis_stats.py         # Redis 分布式统计管理器
│   ├── key_stats.py           # API Key 请求统计（按模型类型分类）
│   ├── key_disable.py         # 上游 Key 自动禁用（401 检测）
│   ├── rate_limit.py          # 用户速率限制（RPM，Redis 固定窗口）
│   ├── redis_reconcile.py     # Redis / DB 对账（清理孤儿数据）
│   ├── stats_scheduler.py     # 每日统计重置调度器
│   └── errors.py              # 公共错误处理工具
│
├── router/                    # API 路由
│   ├── chat.py                # POST /v1/chat/completions
│   ├── images.py              # POST /v1/images/generations
│   ├── video.py               # POST/GET /v1/video/generations + /v1/videos
│   ├── gemini.py              # POST /v1beta/models/{model}:generateContent
│   ├── proxy.py               # GET /proxy/image（CORS 代理）
│   ├── system.py              # GET /health, /api/stats, /api/announcements
│   ├── models.py              # GET /v1/models, /v1beta/models
│   ├── key_pool.py            # GET/POST /api/keys/*（Key 池管理）
│   ├── management.py          # CRUD /api/manage/*（用户/密钥/模型/公告/配置）
│   └── frontend.py            # SPA 前端静态文件服务
│
├── utils/
│   └── http_client.py         # 全局 HTTP 客户端（连接池复用）
│
├── frontend/                  # Vue 3 管理后台前端
│   ├── src/
│   │   ├── views/             # 页面组件（Dashboard, Keys, Upstream, Users 等）
│   │   ├── components/        # 通用组件
│   │   ├── stores/            # Pinia 状态管理
│   │   ├── services/          # API 请求封装
│   │   └── router/            # Vue Router 配置
│   └── dist/                  # 构建产物（Docker 多阶段构建）
│
└── migrations/                # Alembic 数据库迁移脚本
```

---

## API 接口文档

### 认证说明

所有需要认证的接口通过 `Authorization: Bearer <key>` 传递 API Key。Key 来源：
- 若配置了 `SERVER_API_KEY`，使用该值即可通过认证
- 若配置了数据库，可使用管理后台创建的客户端 Key（`sk-agnes-...` 格式）

---

### 1. 聊天完成 (Chat)

#### `POST /v1/chat/completions`

将 OpenAI Chat Completions 格式请求转换为 Agnes 格式并转发。

**请求体：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `model` | string | 模型名称，默认 `agnes-2.5-flash` |
| `messages` | array | 消息列表，格式同 OpenAI |
| `temperature` | float | 采样温度 (0.0~2.0) |
| `top_p` | float | 核采样 (0.0~1.0) |
| `max_tokens` | int | 最大输出 token 数 |
| `max_completion_tokens` | int | 同 `max_tokens`（OpenAI 新规范兼容） |
| `stream` | bool | 是否启用流式输出 |
| `tools` | array | 工具定义列表 |
| `tool_choice` | any | 工具选择策略 |
| `thinking` | object | Anthropic 兼容 Thinking 模式配置 |
| `chat_template_kwargs` | object | Agnes Thinking 模式配置 |

**Thinking 模式示例：**

```json
// OpenAI 兼容格式
{
  "chat_template_kwargs": { "enable_thinking": true }
}

// Anthropic 兼容格式
{
  "thinking": { "type": "enabled", "budget_tokens": 2048 }
}

// 模型名后缀触发
{ "model": "agnes-2.5-flash-thinking" }
```

**非流式响应：**

```json
{
  "id": "chatcmpl-xxxxx",
  "object": "chat.completion",
  "created": 1720000000,
  "model": "agnes-2.5-flash",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello!",
      "reasoning_content": "..." // Thinking 模式时存在
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 50,
    "total_tokens": 70
  }
}
```

**流式响应：** `text/event-stream` 格式，每个 chunk 为：

```json
{
  "id": "chatcmpl-xxxxx",
  "object": "chat.completion.chunk",
  "created": 1720000000,
  "model": "agnes-2.5-flash",
  "choices": [{
    "index": 0,
    "delta": { "role": "assistant" },
    "finish_reason": null
  }]
}
```

最后一个 chunk 包含 `"finish_reason": "stop"`，可选包含 `usage` 字段。

#### `POST /v1/completions`

OpenAI 兼容的文本补全接口，复用 Agnes 文本模型（`agnes-2.5-flash` 等）。

**请求体：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `model` | string | 模型名称 |
| `prompt` | string 或 string[] | 补全提示词（数组会被拼接为多行） |
| `max_tokens` | int | 最大生成 token 数 |
| `temperature` | float | 采样温度 |
| `top_p` | float | 核采样 |
| `n` | int | 生成数量，仅支持 1 |
| `stream` | bool | 是否流式返回 |
| `stop` | string[] | 停止词 |
| `suffix` | string | 文本后缀（忽略） |

**响应** `object: "text_completion"`，`choices[].text` 为生成文本，
支持 `usage`。`stream: true` 时返回 OpenAI 补全格式 SSE 流（以 `data: [DONE]` 结束）。

```json
{
  "id": "cmpl-xxxxx",
  "object": "text_completion",
  "created": 1720000000,
  "model": "agnes-2.5-flash",
  "choices": [{"text": "...", "index": 0, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
}
```

---

### 2. 图像生成 (Images)

#### `POST /v1/images/generations`

将 OpenAI Images API 格式请求转换为 Agnes 图像生成接口。

**请求体：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `model` | string | 模型名称，如 `agnes-image-2.1-flash` |
| `prompt` | string | 图像描述提示词 |
| `size` | string | 输出尺寸，如 `1024x768` |
| `n` | int | 生成数量 (1~10) |
| `response_format` | string | `url` 或 `b64_json` |
| `image` | string[] | 图生图输入图像 URL/Base64 数组 |
| `return_base64` | bool | 文生图 Base64 输出 |
| `extra_body` | object | 高级参数，支持直接透传原生 `extra_body`（详见下文） |

#### 图片模型高级中转与优化特性

本项目对 **Agnes Image 2.1 Flash** 进行了专属深度调优，使得其在完全兼容标准 OpenAI 客户端的同时，也具备了更卓越的生成表现：

1. **精确像素自适应重映射**
   - 针对传入 `1024x768`、`1920x1080`、`1280x720` 等传统像素尺寸的传统客户端，中转层会自动根据**面积接近原则**和**比例最接近原则**，智能将其重新映射为上游推荐的 `1K`/`2K`/`3K`/`4K` 高信息密度尺寸档位及对应的宽高比 `ratio`（例如 `1920x1080` 自动映射为 `size: "2K", ratio: "16:9"`），避免上游拉伸，大幅提升生成画质与构图精度！
   - 对于已规范传入原生 `1K`/`2K` 档位或显式传入 `ratio` 的新请求，重映射器会自动跳过，保证原汁原味透传。

2. **原生 `extra_body` 多端合流**
   - 支持客户端在请求体中直接携带官方原生的 `"extra_body": {"response_format": "url"}` 或输入图像 `image` 字段。中转层会自动将其与顶层参数进行智能高优先级合并（顶层优先），保证原生调用格式 100% 正确适配。

3. **异步 `task_id` 与原始响应透传**
   - 最终返回的 `ImageResponse` 模型和 JSON 响应中会透传上游的异步 `task_id`（如 `"task_id": "task_xxxxx"`），并在后台中以 `[Agnes Image Response Detail]` 日志格式打印原始上游 JSON 结构（对超长 Base64 自动截短进行控制台保护），便于排查。

**响应：**

```json
{
  "created": 1720000000,
  "data": [
    {
      "url": "http://your-server:8000/proxy/image?url=...",
      "revised_prompt": "..."
    }
  ]
}
```

> 注：返回的 CDN 图片 URL 会自动改写为代理服务地址以解决跨域问题。

#### `POST /v1/images/edits`

OpenAI 兼容的图像编辑接口（`multipart/form-data`）。上传图像文件转为
Data URI Base64 后，通过 Agnes 图生图能力实现编辑。

**表单字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `image` | file | 输入图像（必填，最大 20 MB） |
| `prompt` | string | 编辑指令（必填） |
| `model` | string | 模型名称，默认 `agnes-image-2.1-flash` |
| `size` | string | 输出尺寸，如 `1024x1024` |
| `n` | int | 生成数量 (1~10) |
| `response_format` | string | `url` 或 `b64_json` |

响应结构与 `/v1/images/generations` 一致。

---

### 3. 视频生成 (Video)

#### `POST /v1/video/generations`（New API 通用格式）

创建视频生成任务（异步）。**响应为 `{task_id, status}`**，任务结果通过
`GET /v1/video/generations/{task_id}` 查询。

**请求体：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `model` | string | 模型名称，默认 `agnes-video-v2.0` |
| `prompt` | string | 视频内容描述 |
| `image` | string | 图生视频输入图片 URL |
| `duration` | float | 视频时长（秒），默认 5 |
| `width` | int | 视频宽度，默认 1152 |
| `height` | int | 视频高度，默认 768 |
| `fps` | int | 视频帧率，默认 24 |
| `num_inference_steps` | int | 推理步数 |
| `seed` | int | 随机种子 |
| `n` | int | 生成数量，默认 1 |
| `negative_prompt` | string | 反向提示词 |
| `mode` | string | `ti2vid`（文生视频）或 `keyframes`（关键帧） |
| `metadata` | object | 扩展参数（兼容 new-api 格式） |
| `extra_body` | object | 扩展参数（如关键帧图片数组） |

**响应：**

```json
{
  "task_id": "video_xxxxx",
  "status": "queued"
}
```

#### `POST /v1/videos`（Sora 格式）

创建视频任务，请求体同上方。**响应为 Sora Video 对象**（`object: "video"`），
视频内容通过 `GET /v1/videos/{task_id}/content` 流式获取。

```json
{
  "id": "video_xxxxx",
  "object": "video",
  "model": "agnes-video-v2.0",
  "status": "queued"
}
```

#### `GET /v1/video/generations/{task_id}`（New API 通用格式）

查询视频任务状态。**响应为 `{task_id, status, url, format, metadata, error}`**，
`url` 仅在任务完成后存在，取自上游 `metadata.url`。

```json
{
  "task_id": "video_xxxxx",
  "status": "completed",
  "url": "https://cdn.example.com/video.mp4",
  "format": "mp4",
  "metadata": {
    "duration": 5.0,
    "fps": 24,
    "width": 1152,
    "height": 768,
    "seed": 42,
    "model": "agnes-video-v2.0"
  },
  "error": null
}
```

#### `GET /v1/videos/{task_id}`（Sora 格式）

查询视频任务状态，返回 Sora Video 对象（不含 url，通过 `/content` 获取）。

**状态值：** `queued` → `in_progress` → `completed` / `failed`

#### `GET /v1/videos/{task_id}/content`

获取视频结果并重定向（兼容 new-api 下载链路）。

---

### 4. Gemini 兼容接口

#### `POST /v1beta/models/{model}:generateContent`

将 Gemini 格式请求转换为 Agnes 聊天接口，返回 Gemini 格式响应。

**请求体：**

```json
{
  "contents": [
    {"role": "user", "parts": [{"text": "Hello!"}]}
  ],
  "generationConfig": {
    "temperature": 0.7,
    "maxOutputTokens": 1024,
    "topP": 0.9
  }
}
```

**响应：**

```json
{
  "candidates": [{
    "index": 0,
    "content": {"role": "assistant", "parts": [{"text": "Hello!"}]},
    "finishReason": "stop"
  }],
  "usageMetadata": {
    "promptTokenCount": 10,
    "candidatesTokenCount": 20,
    "totalTokenCount": 30
  }
}
```

#### `POST /v1beta/models/{model}:streamGenerateContent`

流式版本，返回 Gemini SSE 格式。

---

### 4.1 Responses API

#### `POST /v1/responses`

Agnes 2.5 Flash 支持的 OpenAI Responses API 兼容端点（流式 / 非流式）。

**请求体：**

```json
{
  "model": "agnes-2.5-flash",
  "input": "Explain how autonomous agents use tools.",
  "max_output_tokens": 1024
}
```

`input` 支持纯文本字符串或结构化消息数组；`stream: true` 时返回 SSE 事件流（`response.created` / `response.output_text.delta` / `response.completed`）。

**响应：**

```json
{
  "id": "resp_xxx",
  "object": "response",
  "status": "completed",
  "model": "agnes-2.5-flash",
  "output": [
    {"type": "message", "role": "assistant", "status": "completed",
     "content": [{"type": "output_text", "text": "..."}]}
  ],
  "usage": {"input_tokens": 35, "output_tokens": 58, "total_tokens": 93}
}
```

---

### 5. 图片代理 (Proxy)

#### `GET /proxy/image?url=<URL>`

代理获取外部 CDN 图片，解决 CORS 跨域问题。

**安全限制：**
- 仅允许域名 `platform-outputs.agnes-ai.space`
- 仅允许图片/视频格式：`.png` `.jpg` `.jpeg` `.gif` `.webp` `.bmp` `.svg` `.mp4` `.webm` `.mov`

**响应：** 原始二进制文件，带 CORS 头和 `Cache-Control: public, max-age=86400`。

---

### 6. 系统接口 (System)

| 端点 | 方法 | 认证 | 说明 |
|---|---|---|---|
| `/health` | GET | 否 | 健康检查，返回 `{"status": "ok"}` |
| `/health/keys` | GET | 否 | 所有 API Key 状态（脱敏） |
| `/api/stats` | GET | 是 | 所有 Key 的请求统计（按模型分类） |
| `/api/stats/public` | GET | 否 | 公开统计信息（前端加载用） |
| `/api/announcements` | GET | 否 | 所有启用的公告（前端首页展示） |

---

### 7. 模型列表 (Models)

| 端点 | 方法 | 认证 | 说明 |
|---|---|---|---|
| `/v1/models` | GET | 是 | 模型列表，按请求头自适应格式 |
| `/v1beta/models` | GET | 是 | Gemini 兼容模型列表 |

`GET /v1/models` 按请求头自适应返回三种原生格式：

| 请求头 | 返回格式 |
|---|---|
| `x-goog-api-key: <key>` | Gemini 格式（`{"models": [...]}`） |
| `x-api-key: <key>` + `anthropic-version: 2023-06-01` | Anthropic 格式（`{"data": [{"type": "model", ...}]}`） |
| `Authorization: Bearer <key>` | OpenAI 格式（`{"object": "list", ...}`） |

认证方面，除 `Authorization: Bearer` 外，`x-goog-api-key` 与 `x-api-key` 请求头
均可作为 ClientKey 的来源参与全部接口的鉴权。

**响应（OpenAI 格式）：**

```json
{
  "object": "list",
  "data": [
    {
      "id": "agnes-2.5-flash",
      "object": "model",
      "created": 1720000000,
      "owned_by": "openai"
    }
  ]
}
```

---

### 8. 管理后台 API (Management)

所有管理接口前缀 `/api/manage`，除特殊说明外均需 JWT 认证。

**默认管理员账号**（仅首次、且库中不存在 `admin` 用户时生效）：账号 `admin`，密码 `admin123`。登录后请立即修改密码。

#### 认证

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/login` | POST | - | 登录，返回 JWT Token |
| `/api/manage/register` | POST | - | 自助注册已关闭，仅允许 Discord 注册 |
| `/api/manage/me` | GET | 登录 | 当前用户信息 |

#### 授权密钥 (ClientKey)

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/keys` | GET | 登录 | 获取当前用户的授权密钥 |
| `/api/manage/keys` | POST | 登录 | 创建授权密钥（每用户 1 把） |
| `/api/manage/keys/reset` | POST | 登录 | 重置授权密钥（删旧建新） |
| `/api/manage/keys/{id}/status` | PUT | 登录 | 启用/停用密钥 |
| `/api/manage/keys/{id}` | DELETE | 登录 | 删除密钥 |

#### 上游通道 (UpstreamKey)

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/upstream-keys` | GET | 登录 | 获取上游 Key（admin 查看全部） |
| `/api/manage/upstream-keys` | POST | 登录 | 创建上游 Key |
| `/api/manage/upstream-keys/{id}/weight` | PUT | admin | 调整权重 |
| `/api/manage/upstream-keys/{id}/status` | PUT | admin | 启用/禁用 |
| `/api/manage/upstream-keys/{id}` | DELETE | 登录/admin | 删除上游 Key |

#### 看板统计

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/dashboard` | GET | 登录 | 全局模型成功率 |
| `/api/manage/dashboard/timeline` | GET | 登录 | 24 小时成功率趋势 |
| `/api/manage/model-stats` | GET | admin | 三种模型类别汇总统计 |
| `/api/manage/upstream-stats` | GET | admin | 上游渠道健康度统计 |

#### 用户管理

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/users` | GET | admin | 所有用户列表及统计 |
| `/api/manage/users` | POST | admin | 创建用户 |
| `/api/manage/users/{id}/password` | PUT | admin | 重置用户密码 |
| `/api/manage/users/{id}` | DELETE | admin | 删除用户 |

#### 模型配置

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/models` | GET | admin | 可用模型列表 |
| `/api/manage/models` | POST | admin | 创建模型配置 |
| `/api/manage/models/{id}` | PUT | admin | 更新模型配置 |
| `/api/manage/models/{id}` | DELETE | admin | 删除模型配置 |

#### 公告管理

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/announcements` | GET | 登录 | 启用的公告列表 |
| `/api/manage/announcements` | POST | admin | 创建公告 |
| `/api/manage/announcements/{id}` | PUT | admin | 更新公告 |
| `/api/manage/announcements/{id}` | DELETE | admin | 删除公告 |

#### 系统配置

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/system-config` | GET | admin | 系统配置列表 |
| `/api/manage/system-config/{key}` | PUT | admin | 更新系统配置 |

#### 密码修改

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/password` | PUT | 登录 | 修改当前用户密码 |

---

## 性能优化

### 并行调用

图片模型支持并行生成多张图片，大幅减少等待时间：

| n 值 | 串行模式 | 并行模式 |
|---|---|---|
| 1 | ~10s | ~10s |
| 4 | ~40s | ~10s |
| 8 | ~80s | ~15s |

```env
ENABLE_PARALLEL_CALLS=true   # 并行模式（默认）
ENABLE_PARALLEL_CALLS=false  # 串行模式
```

### 请求缓存

相同请求直接返回缓存结果：

- **文本模型**：缓存 `model + 最后一条消息 + temperature + max_tokens`
- **图片模型**：缓存 `model + prompt + size + n + return_base64`
- 流式请求和并行请求不缓存

```env
ENABLE_CACHE=true
CACHE_TTL=3600
CACHE_MAX_SIZE=1000
```

---

## API Key 智能降级机制

| 功能 | 说明 |
|---|---|
| **轮询负载均衡** | 多个 Key 按权重顺序轮流使用 |
| **自动降级** | Key 连续失败 3 次后自动降级，暂停使用 1 分钟 |
| **定时健康检测** | 冷却结束后每分钟自动检测 Key 是否恢复 |
| **自动恢复** | 健康检测通过后自动重新加入轮询队列 |
| **401 自动禁用** | 上游返回 401 或错误消息含"该令牌状态不可用"时永久禁用 |

---

## 反向代理部署

如果部署在 Nginx/Traefik 后面，需转发 `X-Forwarded-Proto` 头：

**Nginx 示例：**

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

启动 uvicorn 时需加 `--proxy-headers`：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers
```

---

## 健康检查

```bash
curl http://localhost:8000/health
# {"status": "ok"}

curl http://localhost:8000/health/keys
# 返回所有 API Key 的状态信息
```

---

## License

MIT
