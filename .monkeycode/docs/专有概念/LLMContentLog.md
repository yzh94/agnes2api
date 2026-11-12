# LLMContentLog

## 概述

LLM 请求内容日志，JSONL 格式持久化到文件。

## 实现

`service/llm_content_logger.py::LlmContentLogger`

## 文件位置

`logs/llm/llm-YYYY-MM-DD.jsonl`

## 记录结构

```json
{
  "timestamp": "2026-08-14T15:30:00+08:00",
  "request_id": "chatcmpl-xxx",
  "user_id": 12,
  "client_key_id": 34,
  "endpoint": "/v1/chat/completions",
  "stream": false,
  "model": "agnes-2.5-flash",
  "input": {"model": "...", "messages": [...], ...},
  "output": {"id": "...", "choices": [...], ...},
  "duration_ms": 1234.5,
  "first_chunk_ms": null,
  "upstream_key_prefix": "sk-xxxxxx"
}
```

## 写入规则

- 仅记录成功请求
- 异步写入，不阻塞主流程
- 按天分文件
- 并发写入时行原子性保证

## 开关配置

`config.py::Settings.llm_content_log_enabled`
`.env` 中配置 `LLM_CONTENT_LOG_ENABLED=true`
