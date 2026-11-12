# router/ 模块

## 概述

HTTP 路由层，负责接收请求、调用服务层、返回响应。

## 结构

```
router/
├── chat.py              # OpenAI Chat Completions
├── completions.py       # OpenAI Completions
├── images.py            # OpenAI Images
├── responses.py         # OpenAI Responses API
├── gemini.py            # Google Gemini 兼容
├── video.py             # 视频生成
├── key_pool.py          # Key 池管理
├── management.py        # 管理后台 API
├── system.py            # 系统状态
├── models.py            # 模型列表
├── proxy.py             # 图片代理
├── frontend.py          # 前端静态文件
└── discord_auth.py      # Discord OAuth
```

## 关键文件

| 文件 | 目的 |
|------|------|
| `chat.py` | Chat Completions 路由，核心入口 |
| `completions.py` | 文本补全路由 |
| `gemini.py` | Gemini 协议转换 |
| `management.py` | 管理后台 CRUD |

## 依赖

**本模块依赖**:
- `service/auth.py` - 认证
- `service/chat_transformer.py` - LLM 调用
- `service/key_stats.py` - 用量统计
- `models/database.py` - 数据模型

**依赖本模块的**:
- `main.py` - 注册路由

## 规范

### 文件命名
- 模块名：snake_case
- 路由前缀：与 OpenAI/Gemini 规范一致

### 代码模式

```python
@router.post("/completions", response_model=None)
async def create_chat_completion(request: Request):
    try:
        body = await request.json()
        # ... 处理逻辑
        return response
    except UpstreamAPIError as e:
        return create_error_response(e.detail, e.status_code)
    except Exception:
        logger.exception("Unhandled error")
        return create_error_response("Internal server error", 500)
```

### 错误处理
- 上游错误：转换为 OpenAI 兼容错误格式
- 认证错误：401 + 标准错误体
- 未知错误：500 + 日志记录
