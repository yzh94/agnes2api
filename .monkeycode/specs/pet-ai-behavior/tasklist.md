# 任务清单：AI 驱动桌面宠物行为系统

## 阶段一：后端接口

- [ ] 1.1 创建 `service/pet_act.py` - LLM 调用封装和 prompt 构建
- [ ] 1.2 在 `router/management.py` 新增 `POST /pet/act` 接口
- [ ] 1.3 后端单元测试验证 prompt 构建和 JSON 解析

## 阶段二：前端类型和工具

- [ ] 2.1 创建 `src/types/pet.ts` - 宠物行为类型定义
- [ ] 2.2 创建 `src/composables/usePetAct.ts` - 上下文收集和决策调度

## 阶段三：前端状态和 UI

- [ ] 2.3 改造 `petStore.ts` - 集成 AI 决策逻辑
- [ ] 2.4 改造 `MikuPet.vue` - 放大尺寸 + 新增动作 SVG 层
- [ ] 2.5 前端构建验证

## 阶段四：联调和优化

- [ ] 3.1 端到端测试（宠物行为随时间/状态变化）
- [ ] 3.2 性能优化（减少不必要的 LLM 调用）
