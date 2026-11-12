# Agnes2API 开发者指南

## 项目目的

Agnes2API 是一个 OpenAI/Gemini 兼容的 Agnes AI 中转服务。它在 AI 应用生态中担任 API 桥接角色，将标准接口转换为 Agnes 厂商格式。

**核心职责**:
- 接收 OpenAI/Gemini 格式请求
- 转换为 Agnes 格式并转发
- 管理多 Key 负载均衡与降级
- 记录用量与统计

**相关系统**:
- Agnes AI API - 上游模型服务
- MySQL - 持久化存储
- Redis - 缓存与统计

## 环境搭建

### 前置条件

- Python >= 3.11
- MySQL 8.0+
- Redis 7.0+

### 安装

```bash
# 克隆仓库
git clone <repo-url>
cd agnes2api

# 安装依赖
pip install -r requirements.txt

# 配置环境
cp .env.example .env
# 编辑 .env 填入你的值
```

### 环境变量

| 变量 | 必需 | 描述 | 示例 |
|------|------|------|------|
| `DATABASE_URL` | 是 | MySQL 连接串 | `mysql+aiomysql://user:pass@host:3306/db` |
| `REDIS_CONN_STRING` | 是 | Redis 连接串 | `redis://localhost:6379/0` |
| `JWT_SECRET` | 是 | JWT 签名秘钥（>=32 字符） | `your_super_secret...` |
| `AGNES_BASE_URL` | 是 | 上游 Agnes API 地址 | `https://apihub.agnes-ai.com` |
| `SERVER_API_KEY` | 否 | 服务器级 API Key（留空则仅用 DB 认证） | `secret-key` |
| `LLM_CONTENT_LOG_ENABLED` | 否 | LLM 内容日志开关 | `true` |

⚠️ **绝不提交密钥**。使用 `.env` 文件或密钥管理器。

### 运行

```bash
# 开发服务器（热重载）
DEV_MODE=true python main.py

# 或直接用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 生产模式
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# Docker 启动
docker-compose up -d
```

## 开发工作流

### 代码结构

```
project-root/
├── main.py              # 应用入口
├── config.py            # 配置管理
├── router/              # HTTP 路由
├── service/             # 业务逻辑
├── models/              # 数据模型
├── utils/               # 工具函数
└── frontend/            # Vue 前端
```

### 添加新 API 端点

**需修改的文件**:
1. `router/<domain>.py` - 添加路由处理器
2. `service/<domain>.py` - 添加业务逻辑
3. `models/database.py` - 如有新表

**步骤**:
1. 在 router 中定义路由
2. 实现 service 方法
3. 在 `main.py` 中注册路由
4. 更新 `INTERFACES.md`

### 添加新配置项

**需修改的文件**:
1. `.env.example` - 添加示例值
2. `config.py` - 添加 Settings 字段
3. `DEVELOPER_GUIDE.md` - 文档化

### 数据库变更

```bash
# 运行迁移（自动执行）
python main.py  # 启动时自动调用 init_db()
```

迁移由 `models/migrations.py` 的 `auto_migrate()` 处理，启动时自动检测表结构差异。

## 编码规范

### 文件命名

| 类型 | 约定 | 示例 |
|------|------|------|
| 文件 | snake_case | `chat_transformer.py` |
| 类 | PascalCase | `LlmContentLogger` |
| 函数 | snake_case | `call_agnes_chat` |
| 常量 | SCREAMING_SNAKE | `IDLE_SEGMENT` |

### 日志

```python
# 包含上下文
logger.info(f"Chat completion | model={model} tokens={tokens}")

# 使用适当级别
logger.debug()   # 开发详情
logger.info()    # 正常操作
logger.warning() # 可恢复问题
logger.error()   # 需要关注的故障
```

### 错误处理

```python
# 推荐：特定错误类型
raise UpstreamAPIError(status_code=502, detail="上游连接失败")

# 避免：通用错误
# raise Exception("Something went wrong")
```

## 测试

### 单元测试

```bash
# 运行测试
pytest tests/

# 运行特定测试
pytest tests/service/test_chat_transformer.py -v
```

### 验证脚本

```bash
# 语法检查
python -c "import router.chat; import service.chat_transformer"
```

## 部署

### Docker

```bash
# 构建镜像
docker build -t agnes2api .

# 运行容器
docker run -p 8000:8000 --env-file .env agnes2api
```

### Docker Compose

```bash
docker-compose up -d
```

## LLM 日志功能

LLM 请求内容日志通过 `service/llm_content_logger.py` 实现：

- 日志文件：`logs/llm/llm-YYYY-MM-DD.jsonl`
- 每条记录：JSON 对象，包含 input/output 完整内容
- 写入方式：异步后台任务，不阻塞主流程
- 开关配置：`LLM_CONTENT_LOG_ENABLED=true`

## 常见问题

### Q: 如何添加新的上游 Key？

A: 通过管理后台或调用 `/api/manage/upstream-keys` API。

### Q: Key 被自动禁用怎么办？

A: 检查上游返回的错误，修复后 Key 会在下次定时校验时恢复。

### Q: 如何查看 LLM 请求日志？

A: `cat logs/llm/llm-2026-08-14.jsonl | jq .`
