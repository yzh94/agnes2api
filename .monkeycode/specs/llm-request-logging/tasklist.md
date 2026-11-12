# 需求实施计划

- [x] 1. 新增配置项 `llm_content_log_enabled`
   - 在 `config.py` 的 Settings 类中新增 `llm_content_log_enabled: bool = True` 配置项，置于 LLM 内容日志配置分组下
   - 在 `.env.example` 中补充对应环境变量说明
   - 参考 design.md "改造 config.py" 章节

- [x] 2. 实现 LLM 内容日志写入服务 `service/llm_content_logger.py`
  - [ ] 2.1 实现日志写入核心模块
    - 实现 `LlmContentLogger` 类，提供 `write_log(record: dict) -> None` 异步追加写入方法
    - 通过 `asyncio.create_task` 后台执行文件写入，不阻塞调用方
    - 文件路径 `logs/llm/llm-YYYY-MM-DD.jsonl`，按天分文件，跨天自动切换句柄
    - 使用 `asyncio.Lock` 保证并发写入时单行原子性，避免行交错
    - 目录 `logs/llm/` 不存在时通过 `os.makedirs(exist_ok=True)` 自动创建
    - 写入前检查 `settings.llm_content_log_enabled`，为 False 时直接 return
    - IO 异常时仅 stdout warning 日志，不抛异常
    - JSON 序列化用 `default=str` 兜底处理不可序列化对象
    - 实现模块级单例 `get_llm_content_logger()`
    - 参考 design.md "新增模块 service/llm_content_logger.py" 章节

  - [ ]* 2.2 为日志写入服务编写单元测试
    - 测试正常写入：断言文件创建、单行可 json.loads 解析、字段齐全
    - 测试并发写入：10 次并发 write_log 后断言文件 10 行且每行独立可解析
    - 测试开关关闭：llm_content_log_enabled=False 时不产生文件 IO
    - 测试跨天切换：mock 日期跨越后产生两个不同日期文件
    - 测试 IO 异常：mock 文件写入失败时仅 warning 不抛异常

- [x] 3. 改造 `call_agnes_chat` 非流式函数采集日志
   - 在 `service/chat_transformer.py` 的 `call_agnes_chat` 函数签名新增 `client_key_id: int | None = None` 与 `endpoint: str = "/v1/chat/completions"` 可选参数
   - 在成功返回 result 前（CHAT REQUEST END 日志之后）组装 LogRecord 并调用 `get_llm_content_logger().write_log`
   - LogRecord 字段：timestamp/request_id(user_id/client_key_id/endpoint/stream=False/model/input=_build_agnes_payload(req)/output=result/duration_ms/first_chunk_ms=None/upstream_key_prefix=full_key[:8]
   - 参考 design.md "非流式采集逻辑" 章节，对应 requirements.md 需求 1、2.1、4

- [ ] 4. 改造 `call_agnes_chat_stream` 流式函数采集日志
   - 在 `service/chat_transformer.py` 的 `call_agnes_chat_stream` 函数签名新增 `client_key_id: int | None = None` 与 `endpoint: str = "/v1/chat/completions"` 可选参数
   - 在流式生成器内部维护累积字段：accumulated_content、accumulated_reasoning、accumulated_tool_calls、finish_reason
   - 每个 chunk 解析时累加 delta.content / delta.reasoning_content / delta.tool_calls
   - 流正常结束（收到 [DONE] 或 aiter_lines 自然结束且有 chunk）后组装 LogRecord 并写入
   - 流式 output 结构：{"choices":[{"message":{"content":...,"reasoning_content":...,"tool_calls":...},"finish_reason":...}],"usage":accumulated_usage}
   - request_id 取 chunk_id，first_chunk_ms 取首 chunk 耗时
   - 参考 design.md "流式采集逻辑" 章节，对应 requirements.md 需求 2.2、2.3

- [ ] 5. 改造 4 个路由传入 client_key_id 与 endpoint
  - [ ] 5.1 改造 `router/chat.py`
    - 在调用 call_agnes_chat / call_agnes_chat_stream 时传入 `client_key_id=getattr(request.state, 'client_key_id', None)` 与 `endpoint="/v1/chat/completions"`
    - 参考 design.md "改造各路由层" 章节

  - [ ] 5.2 改造 `router/completions.py`
    - 在调用 call_agnes_chat / call_agnes_chat_stream（含 _stream_completions 内部）时传入 client_key_id 与 `endpoint="/v1/completions"`

  - [ ] 5.3 改造 `router/responses.py`
    - 在调用 call_agnes_chat / call_agnes_chat_stream（含 _responses_stream_generator 内部）时传入 client_key_id 与 `endpoint="/v1/responses"`

  - [ ] 5.4 改造 `router/gemini.py`
    - 在调用 call_agnes_chat / call_agnes_chat_stream（含流式 generateContent）时传入 client_key_id 与 `endpoint="/v1beta/models/{model}:generateContent"` 或对应 streamGenerateContent

- [ ] 6. 检查点 - 语法校验与启动验证
   - 运行 `python -c "import service.llm_content_logger; import service.chat_transformer; import router.chat; import router.completions; import router.responses; import router.gemini"` 确认无导入/语法错误
   - 验证配置项加载正确（python -c "from config import settings; print(settings.llm_content_log_enabled)"）
   - 如有疑问请询问用户

- [x] 7. 端到端验证日志写入
   - 编写临时验证脚本，直接调用 LlmContentLogger.write_log 写入测试记录，断言 logs/llm/ 下 JSONL 文件生成且内容可解析
   - 验证完整 input/output 内容保留、Key 脱敏、字段齐全
   - 参考 requirements.md 需求 3、4、5

- [x] 8. 提交代码并推送
   - git add 全部改动文件，编写规范的 commit message
   - push 到远程 main 分支
