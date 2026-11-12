# UpstreamKey

## 概述

上游 Agnes API Key，用于转发请求到 Agnes 模型。

## 数据库表

`upstream_keys` 表，对应模型 `models/database.py::UpstreamKey`

## 结构

```python
class UpstreamKey(Base):
    __tablename__ = "upstream_keys"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    key = Column(String(100), unique=True)
    name = Column(String(100))
    weight = Column(Integer, default=1)
    status = Column(String(20), default="active")
    disabled_reason = Column(Text)
    disabled_at = Column(DateTime)
    created_at = Column(DateTime)
```

## 负载均衡

通过 `service/redis_key_pool.py::KeyPoolManager` 实现加权轮询。

## 自动降级

- Key 失败（超时、5xx）自动标记失败
- 连续失败后禁用 Key
- 定时校验恢复成功 Key
