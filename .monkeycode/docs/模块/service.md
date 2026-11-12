# service/ 模块

## 概述

业务逻辑层，实现核心转换、认证、统计等功能。

## 结构

```
service/
├── auth.py                    # API Key 认证
├── chat_transformer.py        # Chat 请求/响应转换（核心）
├── llm_content_logger.py      # LLM 内容日志
├── upstream_client.py         # 上游 HTTP 客户端
├── key_stats.py               # Key 用量统计
├── redis_key_pool.py          # Redis Key 池管理
├── rate_limit.py              # 速率限制
├── model_guard.py             # 模型权限校验
├── pet_act.py                 # 宠物行为决策
├── cache.py                   # 请求缓存
├── transformer.py             # 图像生成转换
├── video.py                   # 视频生成服务
├── key_disable.py             # Key 自动禁用
├── key_validation.py          # Key 验证
├── key_validation_scheduler.py# Key 验证调度器
├── redis_stats.py             # Redis 统计
├── redis_reconcile.py         # Redis 对账
├── stats_scheduler.py         # 统计重置调度器
└── system_config.py           # 系统配置
```

## 关键文件

| 文件 | 目的 |
|------|------|
| `chat_transformer.py` | LLM 调用核心，所有路由复用 |
| `auth.py` | 认证中间件逻辑 |
| `redis_key_pool.py` | Key 池管理，负载均衡 |
| `key_stats.py` | 用量统计与数据库写入 |

## 依赖

**本模块依赖**:
- `models/database.py` - 数据模型
- `config.py` - 配置
- `utils/http_client.py` - HTTP 客户端
- Redis - 缓存与队列

**依赖本模块的**:
- `router/*.py` - 所有路由

## 规范

### 代码模式

```python
async def call_agnes_chat(req: ChatCompletionRequest, user_id: int = 0) -> dict:
    """调用 Agnes Chat API，返回 OpenAI 兼容响应。"""
    # 1. 预处理
    payload = _build_agnes_payload(req)
    
    # 2. 调用上游
    http_resp, full_key = await request_upstream_with_retry(...)
    
    # 3. 转换响应
    result = _response_to_openai_response(http_resp.json(), req.model)
    
    # 4. 统计与日志
    stats_manager.record_request(full_key, model_type, True, user_id=user_id)
    get_llm_content_logger().write_log({...})
    
    return result
```

### 错误处理
- 上游错误：抛 UpstreamAPIError
- 内部错误：记录日志后抛异常
