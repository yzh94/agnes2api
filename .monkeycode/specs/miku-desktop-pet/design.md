# Miku Desktop Pet

Feature Name: miku-desktop-pet
Updated: 2026-08-12

## Description

在 agnes2api 管理后台中集成初音未来桌面宠物组件，采用去毒化的陪伴式设计，替代原病毒概念的侵蚀行为。宠物以轻量级 Vue 组件形式存在，可拖拽定位、实时展示系统状态、支持与用户互动。

## Architecture

```mermaid
graph TB
    subgraph "Frontend Layer"
        App[App.vue]
        MikuPet[MikuPet Component]
        PetStore[petStore Pinia Store]
        PetComposable[usePet composable]
    end
    
    subgraph "Backend Layer"
        API[Management API]
        Stats[/api/management/stats]
    end
    
    subgraph "Storage"
        LocalStorage[localStorage]
    end
    
    App --> MikuPet
    MikuPet --> PetStore
    PetStore --> PetComposable
    PetComposable --> API
    API --> Stats
    PetComposable --> LocalStorage
    
    style MikuPet fill:#6366f1,stroke:#4f46e5,color:#fff
    style PetStore fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style PetComposable fill:#a78bfa,stroke:#8b5cf6,color:#fff
```

## Components and Interfaces

### 1. MikuPet.vue (桌面宠物组件)

```
src/components/miku-pet/MikuPet.vue
```

**Props:**
- `enabled: boolean` - 是否启用宠物
- `position: { x: number, y: number }` - 宠物位置
- `mode: 'accompany' | 'monitor'` - 运行模式

**Emits:**
- `update:position` - 位置变更
- `click` - 点击事件
- `hide` - 隐藏请求
- `config-change` - 配置变更

**Template Structure:**
```vue
<template>
  <Teleport to="body">
    <div class="miku-pet" :style="{ left, top, zIndex }">
      <div class="miku-body">
        <!-- 像素/矢量初音未来形象 -->
        <svg class="miku-svg" ... />
      </div>
      <div class="miku-bubble" v-if="showBubble">
        {{ bubbleText }}
      </div>
    </div>
  </Teleport>
</template>
```

**CSS Strategy:**
- 使用 CSS 变量控制配色
- 采用 pixel-art 风格或 SVG 矢量图
- 动画使用 CSS keyframes + requestAnimationFrame

### 2. petStore (Pinia Store)

```
src/stores/petStore.ts
```

**State:**
```typescript
interface PetState {
  enabled: boolean
  position: { x: number, y: number }
  mode: 'accompany' | 'monitor'
  systemState: SystemState | null
  lastUpdate: number
  isDragging: boolean
  mood: 'happy' | 'surprised' | 'shy' | 'thinking' | 'sleeping' | 'worried' | 'panic'
  showBubble: boolean
  bubbleText: string
}
```

**Actions:**
- `fetchSystemState()` - 获取系统状态
- `updatePosition(x, y)` - 更新位置
- `setMood(mood)` - 设置心情
- `showBubble(text, duration?)` - 显示气泡
- `toggleEnabled()` - 切换启用状态

### 3. usePet (Composable)

```
src/composables/usePet.ts
```

**Responsibilities:**
- 管理宠物生命周期
- 处理拖拽逻辑
- 监听系统状态变化
- 自动表情切换

## Data Models

### SystemState

```typescript
interface SystemState {
  total_requests: number
  success_rate: number
  cpu_usage: number
  memory_usage: number
  error_count_24h: number
  uptime: number
  status: 'healthy' | 'warning' | 'critical'
  last_update: string
}
```

### PetConfig

```typescript
interface PetConfig {
  enabled: boolean
  position: { x: number, y: number }
  mode: 'accompany' | 'monitor'
  refresh_interval: number  // 秒
  auto_hide: boolean
}
```

## Correctness Properties

1. **位置持久化**: 宠物位置变更 MUST 立即保存到 localStorage，刷新后恢复
2. **状态同步**: 系统状态数据与 API 响应 MUST 保持一致，延迟不超过 1s
3. **内存安全**: 宠物组件销毁时 MUST 清除所有定时器和事件监听
4. **无障碍**: 宠物 MUST 提供 aria-label 和 tabindex 属性
5. **性能**: 宠物动画 MUST 使用 transform 和 opacity 属性以保证 GPU 加速

## Error Handling

| Scenario | Handling Strategy |
|----------|------------------|
| API 请求失败 | 显示离线表情，10s 后重试，最多 3 次 |
| 网络超时 | 显示警告表情，使用缓存数据 |
| localStorage 不可用 | 降级到内存存储，记录警告日志 |
| 宠物位置越界 | 自动吸附到视口边缘 |
| 用户快速多次点击 | 防抖处理，间隔 200ms |

## Test Strategy

### Unit Tests
- `petStore.test.ts` - Store 状态管理测试
- `usePet.test.ts` - Composable 逻辑测试
- `MikuPet.test.ts` - 组件交互测试

### Integration Tests
- 宠物与系统状态联动测试
- 拖拽定位持久化测试
- 配置变更应用测试

### E2E Tests
- 宠物显示/隐藏流程
- 表情切换触发条件
- 位置拖拽与保存

## Implementation Plan

### Phase 1: 基础框架 (Day 1)
1. 创建 MikuPet 组件骨架
2. 实现 petStore 基础状态
3. 添加基础 SVG 形象

### Phase 2: 交互功能 (Day 2)
1. 实现拖拽逻辑
2. 添加点击交互
3. 实现气泡提示

### Phase 3: 数据集成 (Day 3)
1. 对接系统状态 API
2. 实现状态映射到表情
3. 添加自动刷新

### Phase 4: 优化完善 (Day 4)
1. 性能优化
2. 动画细节打磨
3. 配置面板集成

## References

[^1]: (GitHub) - Miku Pet Concept Design
[^2]: (Vue Docs) - Teleport Component
[^3]: (MDN) - Web Animations API
