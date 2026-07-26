# Agnes2API

OpenAI / Gemini 兼容的 **Agnes** AI 中转服务。

支持：
- **Agnes Image 2.1 Flash** - 图像生成（文生图 / 图生图）
- **Agnes 2.0 Flash** - 文本聊天（流式 / 非流式、工具调用、图像理解、Thinking 模式）
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
  - [图片代理 (Proxy)](#5-图片代理-proxy)
  - [系统接口 (System)](#6-系统接口-system)
  - [模型列表 (Models)](#7-模型列表-models)
  - [管理后台 API (Management)](#8-管理后台-api-management)
- [反向代理部署](#反向代理部署)
- [健康检查](#健康检查)
- [License](#license)

---

## 快速开始

### Docker Compose 部署（推荐）

#### 1. 克隆项目

```bash
git clone https://github.com/yzh94/agnes2api.git
cd agnes2api
```

#### 2. 配置环境变量

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
# JWT 签名秘钥（必需，至少 32 字符）
# ============================================
JWT_SECRET=your_super_secret_jwt_key_here_at_least_32_chars
```

#### 3. 启动服务

```bash
docker compose up -d
```

等待构建完成即可访问：

- **API 文档**: http://localhost:8000/docs （FastAPI Swagger UI）
- **管理后台**: http://localhost:8000/ （前端面板，需登录）

首次启动时会自动创建 admin 用户（密码 `admin123`），请在登录后及时修改密码。

可用模型默认已预置：
- `agnes-2.0-flash` (text)
- `agnes-image-2.1-flash` (image)
- `agnes-video-v2.0` (video)

#### 4. 常用命令

```bash
# 查看日志
docker compose logs -f agnes2api

# 重启服务
docker compose restart

# 停止服务
docker compose down

# 重新构建并启动
docker compose up -d --build

# 删除数据（含 SQLite 数据库）
docker compose down -v
```

### 直接运行

<details>
<summary>如果没有 Docker 环境，也可以直接运行：</summary>

#### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

#### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env`，设置 `JWT_SECRET` 为至少 32 个字符的随机字符串。

#### 3. 启动服务

```bash
python main.py
```

或使用 uvicorn：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

</details>

---

### 调用示例

#### 聊天完成（非流式）

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.0-flash",
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
    "model": "agnes-2.0-flash",
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

#### Gemini 兼容接口（非流式）

```bash
curl http://localhost:8000/v1beta/models/agnes-2.0-flash:generateContent \
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
    model="agnes-2.0-flash",
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

---

## 环境变量

| 变量 | 说明 | 默认值 | 必需 |
|---|---|---|---|
| `AGNES_BASE_URL` | Agnes API 基地址 | `https://apihub.agnes-ai.com` | 否 |
| `SERVER_HOST` | 服务监听地址 | `0.0.0.0` | 否 |
| `SERVER_PORT` | 服务监听端口 | `8000` | 否 |
| `SERVER_API_KEY` | 本服务 API Key 认证（留空则不启用） | 空 | 否 |
| `JWT_SECRET` | 管理后台 JWT 签名秘钥（≥32 字符） | — | **是** |
| `REQUEST_TIMEOUT` | 上游请求超时（秒） | `300` | 否 |
| `ENABLE_PARALLEL_CALLS` | 并行调用开关（图片模型 n>1 时生效） | `true` | 否 |
| `DEV_MODE` | 开发模式（启用热重载） | `false` | 否 |
| `UVICORN_WORKERS` | 生产模式 Worker 数 | `1` | 否 |
| `VIDEO_DEFAULT_MODEL` | 默认视频模型 | `agnes-video-v2.0` | 否 |
| `VIDEO_DEFAULT_DURATION` | 默认视频时长（秒） | `5.0` | 否 |
| `VIDEO_DEFAULT_WIDTH` | 默认视频宽度 | `1152` | 否 |
| `VIDEO_DEFAULT_HEIGHT` | 默认视频高度 | `768` | 否 |
| `VIDEO_DEFAULT_FPS` | 默认视频帧率 | `24` | 否 |
| `VIDEO_TASK_EXPIRE_SECONDS` | 视频任务缓存过期时间（秒） | `3600` | 否 |

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
│
├── models/                    # 数据模型
│   ├── database.py            # SQLAlchemy ORM 模型（User, ClientKey, UpstreamKey 等）
│   ├── openai.py              # OpenAI Images API 请求/响应模型
│   ├── openai_chat.py         # OpenAI Chat Completions API 请求/响应模型
│   ├── agnes.py               # Agnes Image API 请求/响应模型
│   └── video.py               # 视频模型请求/响应模型
│
├── service/                   # 业务逻辑层
│   ├── auth.py                # API Key 认证
│   ├── transformer.py         # 图像请求/响应转换 & 上游调用
│   ├── chat_transformer.py    # 聊天请求/响应转换 & 流式转发
│   ├── video.py               # 视频服务（任务创建、状态查询）
│   ├── upstream_client.py     # 上游 HTTP 客户端（自动换 Key / 重试 / 失败统计）
│   ├── simple_key_pool.py     # 轻量级 Key Pool 管理器（内存加权轮询）
│   ├── key_stats.py           # API Key 请求统计（按模型类型分类，内存）
│   ├── key_disable.py         # 上游 Key 自动禁用（401 检测）
│   ├── key_validator.py       # 上游 Key 健康检验
│   └── errors.py              # 公共错误处理工具
│
├── router/                    # API 路由
│   ├── chat.py                # POST /v1/chat/completions
│   ├── images.py              # POST /v1/images/generations
│   ├── video.py               # POST/GET /v1/video/generations + /v1/videos
│   ├── gemini.py              # POST /v1beta/models/{model}:generateContent
│   ├── proxy.py               # GET /proxy/image（CORS 代理）
│   ├── system.py              # GET /health, /api/stats
│   ├── models.py              # GET /v1/models, /v1beta/models
│   ├── key_pool.py            # GET /api/keys/pool（Key 池状态）
│   ├── management.py          # CRUD /api/manage/*（认证/密钥/通道/看板）
│   └── frontend.py            # SPA 前端静态文件服务
│
├── utils/
│   └── http_client.py         # 全局 HTTP 客户端（连接池复用）
│
├── frontend/                  # Vue 3 管理后台前端
│   ├── src/
│   │   ├── views/             # 页面组件（Dashboard, Keys, Upstream）
│   │   ├── components/        # 通用组件
│   │   ├── stores/            # Pinia 状态管理
│   │   ├── services/          # API 请求封装
│   │   └── router/            # Vue Router 配置
│   └── dist/                  # 构建产物（Docker 多阶段构建）
└── data/                      # SQLite 数据库文件（运行时创建）
```

---

## API 接口文档

### 认证说明

所有需要认证的接口通过 `Authorization: Bearer <key>` 传递 API Key。Key 来源：
- 管理后台 → 授权密钥页面创建的 `sk-agnes-...` 格式的密钥
- 若配置了 `SERVER_API_KEY`，使用该值也可作为 master key 通过认证

---

### 1. 聊天完成 (Chat)

#### `POST /v1/chat/completions`

将 OpenAI Chat Completions 格式请求转换为 Agnes 格式并转发。

**请求体：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `model` | string | 模型名称，默认 `agnes-2.0-flash` |
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
{ "model": "agnes-2.0-flash-thinking" }
```

**非流式响应：**

```json
{
  "id": "chatcmpl-xxxxx",
  "object": "chat.completion",
  "created": 1720000000,
  "model": "agnes-2.0-flash",
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
  "model": "agnes-2.0-flash",
  "choices": [{
    "index": 0,
    "delta": { "role": "assistant" },
    "finish_reason": null
  }]
}
```

最后一个 chunk 包含 `"finish_reason": "stop"`，可选包含 `usage` 字段。

---

### 2. 图像生成 (Images)

#### `POST /v1/images/generations`

将 OpenAI Images API 格式请求转换为 Agnes 图像生成接口。

**请求体：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `model` | string | 模型名称，如 `agnes-image-2.1-flash` |
| `prompt` | string | 图像描述 |
| `size` | string | 输出尺寸，如 `1024x1024` |
| `n` | int | 生成数量 (1-10)，默认 1 |
| `response_format` | string | 返回格式：`url` 或 `b64_json` |

---

### 3. 视频生成 (Video)

#### `POST /v1/videos` (Sora 兼容主路径)
#### `POST /v1/video/generations` (兼容别名)

创建视频生成任务。

**请求体：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `model` | string | 模型名称，如 `agnes-video-v2.0` |
| `prompt` | string | 视频内容描述 |
| `size` | string | 尺寸枚举，如 `1920x1080` |
| `seconds` | string | 时长枚举："4"/"8"/"12" |
| `input` | array | 图生视频输入 `[{"type":"image","url":"..."}]` |

**响应：**

```json
{
  "id": "video_xxxxx",
  "object": "video",
  "model": "agnes-video-v2.0",
  "status": "queued",
  "seconds": "4",
  "size": "1920x1080",
  "created_at": 1720000000,
  "error": null
}
```

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
| `/health` | GET | 否 | 健康检查 |
| `/health/keys` | GET | 否 | 所有 API Key 状态 |
| `/api/stats` | GET | 是 | 所有 Key 的请求统计 |
| `/api/stats/public` | GET | 否 | 公开统计信息 |

---

### 7. 模型列表 (Models)

| 端点 | 方法 | 认证 | 说明 |
|---|---|---|---|
| `/v1/models` | GET | 是 | OpenAI 兼容模型列表 |
| `/v1beta/models` | GET | 是 | Gemini 兼容模型列表 |

---

### 8. 管理后台 API (Management)

所有管理接口前缀 `/api/manage`，需 JWT Token 认证。

默认管理员账号：`admin` / `admin123`（首次登录后请及时修改密码）

#### 认证

| 端点 | 方法 | 角色 | 说明 |
|---|---|---|---|
| `/api/manage/login` | POST | - | 登录，返回 JWT Token |
| `/api/manage/me` | GET | 登录 | 当前用户信息 |
| `/api/manage/password` | PUT | 登录 | 修改密码 |

#### 授权密钥 (ClientKey)

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/manage/keys` | GET | 获取授权密钥 |
| `/api/manage/keys` | POST | 创建授权密钥 |
| `/api/manage/keys/reset` | POST | 重置授权密钥 |
| `/api/manage/keys/{id}/status` | PUT | 启用/停用密钥 |
| `/api/manage/keys/{id}` | DELETE | 删除密钥 |

#### 上游通道 (UpstreamKey)

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/manage/upstream-keys` | GET | 获取上游 Key |
| `/api/manage/upstream-keys` | POST | 创建上游 Key（自动检验） |
| `/api/manage/upstream-keys/{id}/weight` | PUT | 调整权重 |
| `/api/manage/upstream-keys/{id}/status` | PUT | 启用/禁用 |
| `/api/manage/upstream-keys/{id}` | DELETE | 删除上游 Key |
| `/api/manage/upstream-keys/clean-disabled` | DELETE | 清理禁用的 Key |
| `/api/manage/upstream-keys/{id}/validate` | POST | 手动检验 Key |
| `/api/manage/upstream-keys/validate-all` | POST | 全量检验 Key |

#### 看板统计

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/manage/dashboard` | GET | 全局模型成功率 |
| `/api/manage/dashboard/timeline` | GET | 24 小时成功率趋势 |
| `/api/manage/upstream-stats` | GET | 上游渠道健康度统计 |

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
