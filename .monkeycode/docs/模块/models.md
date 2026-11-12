# models/ 模块

## 概述

数据模型层，定义 SQLAlchemy 模型和数据库迁移。

## 结构

```
models/
├── database.py          # 引擎、会话、模型定义
├── migrations.py        # 自动迁移逻辑
├── openai.py            # OpenAI 响应模型
├── openai_chat.py       # Chat 请求/响应模型
├── agnes.py             # Agnes 原始模型
└── video.py             # 视频模型
```

## 关键表

### users
用户表，管理管理员用户。

### client_keys
客户端 Key 表，用于 API 认证和配额管理。

### upstream_keys
上游 Key 表，存储 Agnes API Key。

### usage_logs
用量日志表，记录每次请求的 token 消耗。

### system_configs
系统配置表，KV 存储。

### available_models
可用模型列表。

### announcements
公告表。

## 依赖

**本模块依赖**:
- SQLAlchemy async
- aiomysql
- config.py (database_url)

**依赖本模块的**:
- `service/key_stats.py`
- `service/auth.py`
- `router/management.py`

## 规范

### 模型定义

```python
class ClientKey(Base):
    __tablename__ = "client_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    key = Column(String(100), unique=True, index=True)
    status = Column(String(20), default="active")
```

### 迁移
启动时自动执行 `auto_migrate()`，无需手动迁移。
