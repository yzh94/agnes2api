# User Instruction Memory

This file records user instructions, preferences, and teachings for reference in future interactions.

## Format

### User Instruction Entry
User instruction entries should follow this format:

[User Instruction Summary]
- Date: [YYYY-MM-DD]
- Context: [Mentioned scenario or time]
- Instructions:
  - [Content of user teaching or instruction, described line by line]

### Project Knowledge Entry
Entries discovered by the Agent during task execution should follow this format:

[Project Knowledge Summary]
- Date: [YYYY-MM-DD]
- Context: Discovered by Agent while performing [specific task description]
- Category: [Operations & Deployment|Build Methods|Testing Methods|Troubleshooting & Debugging|Workflow & Collaboration|Environment Configuration]
- Instructions:
  - [Specific knowledge points, described line by line]

## Deduplication Strategy
- Before adding a new entry, check for similar or identical instructions.
- If a duplicate is found, skip the new entry or merge it with the existing one.
- When merging, update the context or date information.
- This helps avoid redundant entries and keeps the memory file tidy.

## Entries

[Project Knowledge Summary]
- Date: 2026-08-10
- Context: 排查并修复 MySQL 兼容性问题时发现
- Category: Environment Configuration
- Instructions:
  - 本项目使用 MySQL 数据库，所有 SQLAlchemy 查询必须兼容 MySQL 语法
  - 禁止使用 PostgreSQL 特有的 FILTER (WHERE ...) 语法，改用 .where() 子句
  - 标准 SQL 函数（count, sum, case, distinct）和 SQLAlchemy ORM 语法均兼容 MySQL
  - 数据库 URL 通过 config.py 的 database_url 配置，必须使用 mysql+aiomysql:// 协议，非 MySQL 格式启动时会报错

[Project Knowledge Summary]
- Date: 2026-08-11
- Context: Discovered by Agent while performing Agnes 文本/图片/视频模型适配与本地启动验证
- Category: Build Methods / Environment Configuration
- Instructions:
  - 环境实际 Python 版本为 3.11（无 python3.12），命令统一用 python3
  - 依赖安装：python3 -m pip install --break-system-packages -r requirements.txt
  - 本地启动验证需先安装并启动 Redis：apt-get install -y redis-server；redis-server --daemonize yes
  - 数据库必须使用 MySQL，连接格式 mysql+aiomysql://user:pass@host:3306/dbname，启动时非 MySQL 协议会直接报错
  - 服务启动验证：python3 -m uvicorn main:app --host 127.0.0.1 --port 8000；健康检查 curl /health
  - 本仓库新增 API 需在 main.py include_router 注册；路由验证可通过 app.openapi() 列全端点

[Project Knowledge Summary]
- Date: 2026-08-12
- Context: 实现 Discord OAuth 第三方登录功能时发现
- Category: Environment Configuration
- Instructions:
  - Discord OAuth 配置项在 config.py 中：discord_client_id, discord_client_secret, discord_redirect_uri
  - 路由注册在 router/discord_auth.py，通过 GET /api/manage/discord/authorize 和 GET /api/manage/discord/callback 工作
  - 新增字段需手动迁移（MySQL）：ALTER TABLE users ADD COLUMN discord_id VARCHAR(30) UNIQUE; ALTER TABLE users ADD COLUMN discord_username VARCHAR(100); 迁移脚本见根目录 MIGRATION_DISCORD_OAUTH.sql
  - 前端 OAuth 回调通过弹窗窗口（window.open）+ postMessage 通信传递 token，无需 URL query param
   - 用户首次 Discord 登录自动注册，用户名冲突时在后缀加数字（最大 999）

[Project Knowledge Summary]
- Date: 2026-08-12
- Context: 排查登录 500 错误时发现问题
- Category: Troubleshooting & Debugging
- Instructions:
  - models/database.py 的 init_db() 迁移失败不再吞异常，改为 raise；create_all 改用显式闭包传给 run_sync 避免 await 列表错误
  - models/migrations.py 的 auto_migrate() 内部移除 try/catch warning 吞错逻辑，迁移失败直接上抛
  - router/management.py 登录接口捕获 OperationalError，列不存在时返回 503 + 迁移 SQL 提示，不再裸 500
  - 若部署后登录 500 且日志含 "Schema migration failed"，需检查 MySQL users 表是否已执行 MIGRATION_DISCORD_OAUTH.sql 中的 ALTER TABLE
  - 异步 SQLAlchemy 中 `await conn.execute()` 返回同步 Result，`fetchall()`/`scalars()` 等均为同步方法，禁止再 await（会报 "object list can't be used in 'await' expression"）
  - auto_migrate 的 MySQL 索引检测必须从 information_schema.STATISTICS 读取真实索引名；只查 COLUMNS 会误判所有索引缺失并重复 ADD INDEX 触发 1061
   - 迁移执行阶段对已存在对象（MySQL 错误码 1060/1061/1091）幂等跳过并告警，避免单条失败中断启动
    - Discord OAuth postMessage handler 必须同步调用 authStore.setToken / authStore.setRole，仅更新 localStorage 不够：authStore 的 token ref 在模块顶层一次性初始化，localStorage 变更后不自动响应，路由守卫 isLoggedIn 仍为 false 会拦截跳转回 /login
     - 全站 UI 已升级为 Linear/Vercel 简约科技风格（2026-08-12）：主色调 Indigo #6366f1，背景纯黑灰 #08090a；移除扫描线/光晕/脉冲等动态装饰；卡片采用 hairline 边框 rgba(255,255,255,0.06) + backdrop-filter blur；按钮直角圆角 6px，hover 柔和过渡；Element Plus 全局覆盖，语义化配色（success=#34d399 / danger=#f87171 / warning=#fb923c / info=#60a5fa）；字号行高加大增加呼吸感
     - 注册机制已改为仅允许 Discord OAuth 注册（2026-08-13）：POST /api/manage/register 返回 403；前端 /register 路由、RegisterView.vue、registerAction/register() 均已移除；普通用户密码登录（POST /login）和 Discord 登录均正常保留
      - 退出登录循环刷新 Bug（2026-08-12）：http.ts 拦截器检测到 401 时会调用 window.location.href = '/login'，若此时有 pending 请求再次触发 401，会无限循环；修复方案：添加 isRedirecting 标志位防止重复重定向
      - 桌面宠物功能已整体移除（2026-09-18）：删除 MikuPet.vue、petStore.ts、usePet.ts、usePetAct.ts、types/pet.ts、service/pet_act.py，以及 management.py 的 /pet/act、/pet/idle、/pet/chat 三个端点；前端 App.vue 不再有宠物挂载点，相关 localStorage 键残留无害
      - LLM 请求内容日志功能（2026-08-14）：service/llm_content_logger.py 实现 JSONL 日志写入，service/chat_transformer.py 在 call_agnes_chat 和 call_agnes_chat_stream 中采集；日志按天滚动到 logs/llm/YYYYMMDD.jsonl；并发安全使用 asyncio.Lock；stream 场景 tool_calls 累积必须深度合并（dict 递归 update、str 拼接、其他覆盖），禁止直接 .update()

[User Instruction Summary]
- Date: 2026-09-16
- Context: 多 URL 容灾调度、看板 URL 成功率面板、北京时间显示等功能开发过程中，用户在每个功能完成后均明确要求提交
- Instructions:
  - 每个功能开发完成并验证通过后，主动询问或直接执行 git commit 并 push 到远程 main 分支（用户在本会话中连续 4 次要求此操作）
  - 提交前先 git status / git diff --stat 确认改动范围，只 add 本次功能相关文件
  - 前端改动验证方式：npm run build（vue-tsc 1.8 与环境 Node/TS 版本不兼容无法运行，属项目原有问题）；后端验证方式：python3 -m py_compile + 带测试环境变量（DATABASE_URL/JWT_SECRET）的单脚本功能验证

[Project Knowledge Summary]
- Date: 2026-10-10
- Context: 部署后容器启动报 ImportError: No module named 'greenlet' 排查时发现
- Category: Environment Configuration / Troubleshooting & Debugging
- Instructions:
  - 生产部署：push 到远程 main 后，服务器会 docker compose up -d --build 重建容器，每次 push 都会按 requirements.txt 全新重装依赖（非增量）
  - requirements.txt 中 sqlalchemy 必须带 [asyncio] extra 或显式声明 greenlet；普通 sqlalchemy>=2.0.0 因 platform_machine 条件标记可能不安装 greenlet，重建后容器在 models/database.py 导入 sqlalchemy.ext.asyncio 时直接 ImportError 崩溃
  - 排查特征：启动即崩且栈顶为 sqlalchemy/util/concurrency.py 中 `from greenlet import getcurrent` 失败，基本即为 greenlet 缺失

[Project Knowledge Summary]
- Date: 2026-10-19
- Context: LRU+二态 Key 池重构的本地回归验证
- Category: Testing Methods / Environment Configuration
- Instructions:
  - 当前沙箱默认无 redis-server、无 fakeredis、无 pytest/pydantic/fastapi 依赖：Python 侧验证用 python3 -m py_compile 全量编译 + sys.modules 注入 stub（redis/sqlalchemy/config/models.database/service.*）+ FakeRedis 模拟跑业务断言
  - FakeRedis 需实现 pipeline 语义（hgetall/hset/hincrby/lpush/ltrim/lrange/delete 按操作顺序执行并返回结果列表）与 eval（按 Lua 逻辑用 Python 模拟）；asyncio.create_task 调度的后台协程需 await asyncio.sleep(0) 让其落地后再断言
  - 前端 node_modules 未提交：验证需先 npm install（devDependencies 含 vite/typescript/vue-tsc），再 npm run build（vite build 约 30s；vue-tsc 与环境 Node/TS 版本不兼容无法运行，属项目原有问题）
