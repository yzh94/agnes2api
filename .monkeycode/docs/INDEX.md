# Agnes2API 文档

## 项目概述

Agnes2API 是一个 OpenAI/Gemini 兼容的 Agnes AI 中转服务，桥接标准 AI 接口与 Agnes 厂商模型。

**目标用户**: 需要使用 Agnes 模型但希望使用 OpenAI/Gemini 标准接口的开发者。

**核心价值**:
- 统一 OpenAI/Gemini 接口与 Agnes 模型的桥接
- 支持多 Key 负载均衡与自动降级
- 提供用量统计、速率限制、配额管理
- 集成桌面宠物 AI 行为决策

## 文档导航

- [架构设计](./ARCHITECTURE.md) - 系统架构和技术设计
- [接口定义](./INTERFACES.md) - 接口和交互规范
- [开发指南](./DEVELOPER_GUIDE.md) - 开发环境和规范

---

## 核心文档

### [架构设计](./ARCHITECTURE.md)
系统设计、技术栈、组件结构和数据流程。从这里开始了解系统如何运作。

### [接口定义](./INTERFACES.md)
公开 API、CLI 命令、事件和契约。集成或使用此系统的参考。

### [开发指南](./DEVELOPER_GUIDE.md)
环境搭建、开发工作流、编码规范和常见任务。贡献者必读。

---

## 模块

| 模块 | 描述 | README |
|------|------|--------|
| `router/` | HTTP 路由层，处理请求分发 | [README](../router/README.md) |
| `service/` | 业务逻辑层，核心转换与统计 | [README](../service/README.md) |
| `models/` | 数据模型和数据库 schema | [README](../models/README.md) |
| `utils/` | 共享工具和助手 | [README](../utils/README.md) |

---

## 核心概念

理解这些领域概念有助于导航代码库：

| 概念 | 描述 |
|------|------|
| [ClientKey](./专有概念/ClientKey.md) | 客户端 API Key，用于身份认证和配额管理 |
| [UpstreamKey](./专有概念/UpstreamKey.md) | 上游 Agnes API Key，用于转发请求 |
| [UsageLog](./专有概念/UsageLog.md) | 请求用量记录，存储每次调用的 token 消耗 |
| [KeyPool](./专有概念/KeyPool.md) | 上游 Key 池，实现负载均衡与自动降级 |
| [LLMContentLog](./专有概念/LLMContentLog.md) | LLM 请求内容日志，JSONL 格式持久化 |

---

## 快速开始

### 项目新人？

按此路径学习：
1. **[架构设计](./ARCHITECTURE.md)** - 了解全局
2. **[核心概念](#核心概念)** - 学习领域术语
3. **[开发指南](./DEVELOPER_GUIDE.md)** - 搭建环境
4. **[接口定义](./INTERFACES.md)** - 探索公开 API

### 需要集成？

1. **[接口定义](./INTERFACES.md)** - API 契约和认证
2. **[架构设计](./ARCHITECTURE.md)** - 系统边界和数据流

### 首次贡献？

1. **[开发指南](./DEVELOPER_GUIDE.md)** - 搭建和工作流
2. **[安全起步点](./DEVELOPER_GUIDE.md#添加新-api-端点)** - 低风险区域
3. **[常见任务](./DEVELOPER_GUIDE.md#常见任务)** - 分步指南

---

## 快速参考

### 命令

```bash
# 开发服务器
python main.py

# Docker 启动
docker-compose up -d

# 运行测试
pytest tests/
```

### 重要文件

| 文件 | 目的 |
|------|------|
| `main.py` | 应用入口，FastAPI 初始化 |
| `config.py` | 配置管理 |
| `service/chat_transformer.py` | LLM 请求转换核心 |
| `models/database.py` | 数据模型定义 |
| `.env.example` | 环境变量模板 |
