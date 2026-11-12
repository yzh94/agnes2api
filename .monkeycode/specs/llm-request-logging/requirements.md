# Requirements Document

## Introduction

本功能为 Agnes2API 中转服务增加 LLM 请求内容日志能力。当前服务仅记录请求元信息（model、messages 数量、耗时）和聚合用量（UsageLog 表的 tokens/cost），不记录用户发送给 LLM 的实际输入内容与 LLM 返回的实际输出内容。新增功能将完整记录每个用户每次成功 LLM 调用的输入与输出内容，并以 JSONL 文件形式持久化保存，用于问题排查、行为审计与对话回溯。

## Glossary

- **LLM 调用**：通过 `service/chat_transformer.py` 的 `call_agnes_chat`（非流式）或 `call_agnes_chat_stream`（流式）向上游 Agnes 模型发起的一次请求-响应过程。
- **输入内容**：用户在请求中发送给 LLM 的完整 messages 数组（含 system/user/assistant 各角色消息的原始文本或多模态内容），以及 model、temperature、max_tokens 等请求参数。
- **输出内容**：LLM 返回的完整响应文本。非流式为 `choices[0].message.content`；流式为所有 SSE chunk 中 `delta.content` 拼接后的完整文本。
- **JSONL**：JSON Lines 格式，每行一个独立 JSON 对象，便于流式追加写入与按行解析。
- **成功请求**：上游返回 HTTP 2xx 且响应体被正常解析/消费完成的 LLM 调用。鉴权失败、上游 4xx/5xx、连接超时、解析异常等均不计入。
- **request_id**：单次 LLM 调用的唯一标识，取上游响应 `id` 字段（如 `chatcmpl-xxx`），流式场景取本地生成的 chunk_id。

## Requirements

### Requirement 1: LLM 调用输入内容记录

**User Story:** AS 运维人员，I want 查看每个用户发送给 LLM 的完整输入内容，so that 排查对话异常或审计用户行为时有据可查。

#### Acceptance Criteria

1. WHEN 一次 LLM 调用在上游成功返回响应，THE 系统 SHALL 将该次调用的完整输入内容写入 JSONL 日志文件，输入内容包含 model 名称、完整 messages 数组、stream 标志、temperature、max_tokens、top_p、tools、thinking 等所有请求参数。
2. WHEN messages 数组中存在多模态内容（如 image_url），THE 系统 SHALL 原样保留该结构写入日志，不丢弃任何字段。
3. WHEN 一次 LLM 调用因上游错误、超时、鉴权失败或解析异常而未成功完成，THE 系统 SHALL 跳过该次调用的日志写入。

### Requirement 2: LLM 调用输出内容记录

**User Story:** AS 运维人员，I want 查看每个用户从 LLM 收到的完整输出内容，so that 验证模型回答质量并追溯具体对话内容。

#### Acceptance Criteria

1. WHEN 一次非流式 LLM 调用成功完成，THE 系统 SHALL 将上游返回的完整响应（含 choices 中所有 message 的 content、reasoning_content、tool_calls，以及 usage 统计）写入 JSONL 日志文件。
2. WHEN 一次流式 LLM 调用成功完成，THE 系统 SHALL 将所有 SSE chunk 的 delta.content 拼接为完整文本，连同 reasoning_content、tool_calls、finish_reason、usage 统计一并写入 JSONL 日志文件。
3. WHEN 上游响应中包含 reasoning_content（思考链），THE 系统 SHALL 将 reasoning_content 与正式 content 分开记录为独立字段。

### Requirement 3: JSONL 文件持久化

**User Story:** AS 运维人员，I want LLM 请求日志以文件形式持久化保存，so that 日志不随服务重启丢失且可独立归档分析。

#### Acceptance Criteria

1. THE 系统 SHALL 将 LLM 调用日志写入 `logs/llm/` 目录下的 JSONL 文件。
2. WHEN 系统运行中产生 LLM 调用日志，THE 系统 SHALL 按天分文件存储，文件名格式为 `llm-YYYY-MM-DD.jsonl`。
3. WHEN 跨天运行时（本地时间 00:00:00），THE 系统 SHALL 自动切换到新的日期文件继续写入。
4. THE 系统 SHALL 对每条日志记录以追加方式写入对应日期文件，不覆盖已有内容。
5. WHEN 日志目录 `logs/llm/` 不存在时，THE 系统 SHALL 在首次写入前自动创建该目录。

### Requirement 4: 日志记录字段规范

**User Story:** AS 运维人员，I want 每条 LLM 日志包含完整的上下文字段，so that 能定位是哪个用户在什么时间用什么参数调用了哪个模型并得到什么结果。

#### Acceptance Criteria

1. THE 系统 SHALL 在每条 JSONL 日志记录中包含以下字段：`timestamp`（ISO8601 本地时间）、`request_id`、`user_id`、`client_key_id`（可为 null）、`endpoint`（调用入口路由，如 `/v1/chat/completions`）、`stream`（bool）、`model`、`input`（完整请求参数对象）、`output`（完整响应对象）、`duration_ms`（总耗时）、`upstream_key_prefix`（上游 Key 前缀脱敏值）。
2. WHEN 某字段在特定调用中不存在（如非流式无 first_chunk_ms），THE 系统 SHALL 将该字段置为 null 或省略，并保证其余字段完整。
3. THE 系统 SHALL 对上游 API Key 仅记录前 8 字符的脱敏前缀，不记录完整 Key 值。

### Requirement 5: 日志写入可靠性

**User Story:** AS 运维人员，I want 日志写入失败不影响 LLM 请求的正常处理，so that 日志功能不会成为业务可用性的单点故障。

#### Acceptance Criteria

1. WHEN 日志文件写入发生 IO 异常，THE 系统 SHALL 在 stdout 输出一条 warning 日志记录失败原因，并继续正常返回 LLM 响应给用户。
2. THE 系统 SHALL 以异步方式执行文件写入，不阻塞 LLM 响应返回主流程。
3. WHEN 同一日期文件出现并发写入，THE 系统 SHALL 通过线程锁或异步锁保证每条记录作为完整单行写入，不出现行交错。

### Requirement 6: 日志开关控制

**User Story:** AS 运维人员，I want 通过配置开关控制 LLM 内容日志的启用与关闭，so that 在不需要时节省磁盘 IO 并保护隐私。

#### Acceptance Criteria

1. THE 系统 SHALL 提供配置项 `llm_content_log_enabled`（默认 true）控制 LLM 内容日志功能的启用与关闭。
2. WHEN `llm_content_log_enabled` 配置为 false 时，THE 系统 SHALL 跳过所有输入输出内容的采集与文件写入逻辑。
3. WHEN 配置从 false 切换为 true 并重启服务后，THE 系统 SHALL 恢复日志写入功能，无需手动创建日志目录。
