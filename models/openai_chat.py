"""OpenAI Chat Completions API 兼容的请求 / 响应模型。

参考：https://platform.openai.com/docs/api-reference/chat
"""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class StreamOptions(BaseModel):
    """流式输出的持续选项。"""
    include_usage: bool = Field(default=False)


class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completions API 标准请求体。"""
    model: str = Field(default="agnes-2.0-flash")
    messages: List[Any] = Field(default_factory=list)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    max_completion_tokens: Optional[int] = Field(default=None, gt=0)
    stream: Optional[bool] = Field(default=False)
    stream_options: Optional[StreamOptions] = Field(default=None)
    tools: Optional[List[dict[str, Any]]] = Field(default=None)
    tool_choice: Optional[Any] = Field(default=None)
    user: Optional[str] = Field(default=None)

    # Thinking 模式参数
    thinking: Optional[dict[str, Any]] = Field(default=None)
    chat_template_kwargs: Optional[dict[str, Any]] = Field(default=None)

    model_config = {"extra": "allow"}


class ChoiceDeltaToolCallFunction(BaseModel):
    name: Optional[str] = Field(default=None)
    arguments: Optional[str] = Field(default=None)


class ChoiceDeltaToolCall(BaseModel):
    index: int = 0
    id: Optional[str] = Field(default=None)
    function: ChoiceDeltaToolCallFunction = Field(default_factory=ChoiceDeltaToolCallFunction)
    type: Optional[Literal["function"]] = Field(default=None)


class ChoiceDelta(BaseModel):
    role: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    reasoning_content: Optional[str] = Field(default=None)
    tool_calls: Optional[List[ChoiceDeltaToolCall]] = Field(default=None)


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Choice(BaseModel):
    index: int = 0
    message: Optional[Any] = Field(default=None)
    reasoning_content: Optional[str] = Field(default=None)
    finish_reason: Optional[str] = Field(default="stop")


class ChatCompletionResponse(BaseModel):
    """OpenAI Chat Completions API 标准响应体。"""
    id: str = Field(default="chatcmpl-default")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default=0)
    model: str = Field(default="agnes-2.0-flash")
    choices: List[Choice] = Field(default_factory=list)
    usage: Optional[Usage] = Field(default=None)


class DeltaChoice(BaseModel):
    """流式输出中的单个 chunk choice。"""
    index: int = 0
    delta: ChoiceDelta = Field(default_factory=ChoiceDelta)
    finish_reason: Optional[str] = Field(default=None)


class ChatCompletionChunkResponse(BaseModel):
    """OpenAI Chat Completions API 流式响应 chunk。"""
    id: str = Field(default="chatcmpl-default")
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default=0)
    model: str = Field(default="agnes-2.0-flash")
    choices: List[DeltaChoice] = Field(default_factory=list)
    usage: Optional[Usage] = Field(default=None)