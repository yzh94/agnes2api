# UsageLog

## 概述

请求用量记录，存储每次调用的 token 消耗。

## 数据库表

`usage_logs` 表，对应模型 `models/database.py::UsageLog`

## 结构

```python
class UsageLog(Base):
    __tablename__ = "usage_logs"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    client_key_id = Column(Integer, ForeignKey("client_keys.id"))
    upstream_key = Column(String(100))
    model = Column(String(50))
    tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime)
```

## 写入时机

每次成功 LLM 请求后，通过 `service/key_stats.py::record_request()` 异步写入。

## 用途

- 用量统计与报表
- 配额扣减
- 费用计算
