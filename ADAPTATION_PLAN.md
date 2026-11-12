# Agnes2API 适配方案

## 概述

本项目作为 Agnes 中转服务，支持将 New API、OpenAI、Gemini 的模型请求格式适配到 Agnes 上游。

---

## 一、已适配接口

### 1.1 文本聊天接口

| 请求格式 | 端点 | 状态 | 说明 |
|---------|------|------|------|
| OpenAI | `POST /v1/chat/completions` | 已实现 | chat.py + chat_transformer.py |
| Gemini | `POST /v1beta/models/{model}:generateContent` | 已实现（文本） | gemini.py，支持多模态输入 |
| Anthropic | `POST /v1/messages` | 已实现 | 通过 messages 转换 |

**已适配功能：**
- [x] 文本对话
- [x] 多模态输入（image_url 公网 URL）
- [x] 系统消息（system_instruction）
- [x] 流式响应（SSE）
- [x] 非流式响应
- [x] 模型类型校验（ensure_text_model）
- [x] Thinking 模式（-thinking 后缀）
- [x] 参数透传（temperature, top_p, max_tokens, tools, tool_choice）

**未实现：**
- [ ] Gemini 图像生成（responseModalities 含 IMAGE）→ 见第三部分

---

### 1.2 图像生成接口

| 请求格式 | 端点 | 状态 | 说明 |
|---------|------|------|------|
| OpenAI | `POST /v1/images/generations` | 已实现 | images.py + transformer.py |
| OpenAI | `POST /v1/images/edits` | 已实现 | images.py edits 端点 |

**已适配功能：**
- [x] 文生图
- [x] 图生图（image 数组）
- [x] 尺寸参数（size: 1K/2K/3K/4K，ratio）
- [x] 输出格式（url / b64_json）
- [x] Base64 抓取转码（b64_json 格式）
- [x] CDN URL 代理重写
- [x] 并行调用（n>1）

---

### 1.3 视频生成接口

| 请求格式 | 端点 | 状态 | 说明 |
|---------|------|------|------|
| Sora/OpenAI | `POST /v1/videos` | 已实现 | video.py |
| New API | `POST /v1/video/generations` | 已实现 | video.py 通用格式 |
| Sora/OpenAI | `GET /v1/videos/{id}` | 已实现 | 查询状态 |
| New API | `GET /v1/video/generations/{id}` | 已实现 | 查询状态 |

**New API 视频格式：**
- 创建响应：`{task_id, status}`
- 查询响应：`{task_id, status, url, format, metadata, error}`

---

### 1.4 文本补全接口

| 请求格式 | 端点 | 状态 | 说明 |
|---------|------|------|------|
| OpenAI | `POST /v1/completions` | 已实现 | completions.py |

**已适配功能：**
- [x] prompt → messages 转换
- [x] text_completion 响应格式
- [x] 流式 SSE

---

### 1.5 模型列表接口

| 请求格式 | 端点 | 状态 | 说明 |
|---------|------|------|------|
| OpenAI | `GET /v1/models` | 已实现 | models.py |
| Gemini | `GET /v1beta/models` | 已实现 | models.py |

**已实现头自适应：**
- [x] 含 x-goog-api-key → Gemini 格式
- [x] 含 x-api-key + anthropic-version → Anthropic 格式
- [x] 其余 → OpenAI 格式

---

## 二、未实现接口（按用户需求）

### 2.1 B 类：无能力接口（保持 404）

用户选择不处理以下接口，返回 404：

| 接口类型 | 端点 | 状态 |
|---------|------|------|
| Embeddings | `POST /v1/embeddings` | 404 |
| Rerank | `POST /v1/rerank` | 404 |
| Moderation | `POST /v1/moderations` | 404 |
| Audio | `POST /v1/audio/transcriptions` | 404 |
| Realtime | `POST /v1/realtime` | 404 |

**理由：** Agnes 不提供这些能力。

---

### 2.2 Gemini 图像生成 ✅ 已实现

**实现方案：**

```python
# router/gemini.py
def _parse_gemini_request(body: dict, model: str) -> GeminiRequestInfo:
    """返回 (openai_req, is_image_gen, prompt, size, ratio)"""
    generation_config = body.get("generationConfig", {})
    response_modalities = generation_config.get("responseModalities", [])
    is_image_gen = any("IMAGE" in str(m).upper() for m in response_modalities)
    
    # 提取 prompt
    prompt = ""
    for content_item in body.get("contents", []):
        for p in content_item.get("parts", []):
            if isinstance(p, dict) and p.get("text"):
                prompt = p["text"]
                break
    
    return GeminiRequestInfo(
        openai_req=ChatCompletionRequest(...),
        is_image_gen=is_image_gen,
        prompt=prompt,
        size="1024x1024",
    )

# 路由分发
if info.is_image_gen:
    image_req = ImageRequest(model="agnes-image-2.1-flash", prompt=info.prompt, size=info.size)
    agnes_resp = await call_agnes_generate(image_req)
    return _agnes_image_to_gemini_response(agnes_resp)
else:
    agnes_resp = await call_agnes_chat(info.openai_req)
    return _agnes_to_gemini_response(agnes_resp)
```

**响应格式转换：** Agnes `{data: [{url, b64_json}]}` → Gemini `{candidates: [{content: {parts: [{inlineData: {...}}]}}]}`

**请求体示例：**
```json
{
  "model": "gemini-2.0-flash-exp",
  "contents": [{"role": "user", "parts": [{"text": "a white ceramic cup"}]}],
  "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
}
```

**响应格式：**
```json
{
  "candidates": [{
    "content": {
      "role": "model",
      "parts": [{"inlineData": {"mimeType": "image/png", "data": "iVBORw0KGgo..."}}]
    },
    "finishReason": "stop"
  }]
}
```

---

## 三、待实现接口清单

### 3.1 P0：Gemini 图像生成

**端点：** `POST /v1beta/models/{model}:generateContent`

**触发条件：**
- `generationConfig.responseModalities` 包含 `"IMAGE"`

**请求体示例：**
```json
{
  "model": "gemini-2.0-flash-exp",
  "contents": [{
    "role": "user",
    "parts": [{"text": "a white ceramic cup"}]
  }],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"],
    "temperature": 1,
    "topP": 0.95,
    "maxOutputTokens": 8192,
    "imageConfig": {"quality": "compression_medium"}
  }
}
```

**响应格式：**
```json
{
  "candidates": [{
    "content": {
      "role": "model",
      "parts": [
        {"inlineData": {"mimeType": "image/png", "data": "iVBORw0KGgo..."}}
      ]
    },
    "finishReason": "stop"
  }]
}
```

---

## 四、实现步骤

### 步骤 1：修改 `_parse_gemini_request`

返回 `(ChatCompletionRequest, bool)` 元组，第二个值表示是否为图像生成。

### 步骤 2：新增图像生成检测函数

```python
def _is_image_generation(body: dict) -> bool:
    """检测请求是否为 Gemini 图像生成模式"""
    gen_config = body.get("generationConfig", {})
    modalities = gen_config.get("responseModalities", [])
    return any("IMAGE" in str(m).upper() for m in modalities)
```

### 步骤 3：实现图像请求解析

从 `contents` 中提取 prompt，创建 `ImageRequest`。

### 步骤 4：实现图像响应转换

将 Agnes 图像响应转为 Gemini `inlineData` 格式。

### 步骤 5：路由分发

在端点中根据 `is_image_gen` 选择调用 `call_agnes_generate` 或 `call_agnes_chat`。

---

## 五、测试用例

```python
# test_gemini_image.py
async def test_gemini_image_generation():
    """测试 Gemini 图像生成请求"""
    body = {
        "contents": [{"role": "user", "parts": [{"text": "a white ceramic cup"}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "temperature": 1,
            "topP": 0.95,
            "maxOutputTokens": 8192,
        }
    }
    
    # 应该触发图像生成路径
    assert _is_image_generation(body) is True
    
    # 应该解析出 prompt
    image_req, prompt = _parse_image_request(body, "gemini-2.0-flash-exp")
    assert image_req.prompt == "a white ceramic cup"
    assert image_req.model == "agnes-image-2.1-flash"
```

---

## 六、相关文件

| 文件 | 修改内容 |
|------|---------|
| `router/gemini.py` | 图像生成检测、路由分发、响应转换 |
| `service/transformer.py` | 已有，无需修改 |
| `models/openai.py` | 已有 ImageRequest，无需修改 |

---

## 七、后续可扩展方向

### 7.1 Anthropic 图像生成

当前 Anthropic 接口（`POST /v1/messages`）仅支持文本。如需支持图像生成，需：

1. 检测 `response_format: {"type": "base64_image"}` 等参数
2. 路由到 `call_agnes_generate`
3. 响应中返回 `image` part

### 7.2 OpenAI Realtime 会话

如需支持 Realtime 会话，需：
1. 实现 WebSocket 端点 `/v1/realtime`
2. 将 Realtime 协议转换为 Agnes 支持的格式
3. 目前 Agnes 暂无 Realtime 接口

---

## 八、总结

| 分类 | 接口 | 状态 |
|------|------|------|
| 文本聊天 | OpenAI / Gemini / Anthropic | 已实现 |
| 图像生成 | OpenAI / Gemini | 已实现 ✅ |
| 视频生成 | Sora / New API | 已实现 |
| 文本补全 | OpenAI Completions | 已实现 |
| 模型列表 | OpenAI / Gemini / Anthropic | 已实现 |
| Embeddings | - | 404（Agnes 无此能力） |
| Rerank | - | 404（Agnes 无此能力） |
| Moderation | - | 404（Agnes 无此能力） |
| Audio | - | 404（Agnes 无此能力） |
| Realtime | - | 404（Agnes 无此能力） |

---

## 九、实现状态（更新）

### 已完成

1. **Gemini 图像生成适配** ✅
   - 文件：`router/gemini.py`
   - 提交：`f6da092`
   - 功能：
     - `_parse_gemini_request` 返回 `GeminiRequestInfo` 元组，包含 `is_image_gen` 字段
     - 检测 `generationConfig.responseModalities` 含 `"IMAGE"` 时触发图像生成路由
     - 新增 `_handle_image_generation` 和 `_handle_text_generation` 路由分发函数
     - 新增 `_agnes_image_to_gemini_response` 响应转换（Base64 → inlineData）
     - 保持 `inline_data`/`fileData` 拒绝逻辑（Agnes 仅支持公网 URL）

### 待实现

1. **流式图像生成** - Gemini 图像生成不支持 SSE 流式响应，暂不实现
2. **Anthropic 图像生成** - 需检测 `response_format: {"type": "base64_image"}`
3. **OpenAI Realtime 会话** - 需 WebSocket，Agnes 暂无此接口
