# 技术设计：AI 驱动桌面宠物行为系统

## 架构概览

```
前端 petStore (每30s)
  → 收集上下文 {time, stats, history, context}
  → POST /api/manage/pet/act
    → 后端构造 Prompt → 调用 Agnes 文本模型
    → 解析 JSON 响应 {mood, action, bubbleText, emoji}
  → 前端播放对应 SVG 动画 + 显示气泡
```

## 后端设计

### 新增文件
- `service/pet_act.py` - LLM 调用封装、prompt 构建、JSON 解析

### 新增接口
```
POST /api/manage/pet/act
认证：Bearer Token（与现有路由一致）
权限：已登录用户即可

请求体 PetActRequest:
  time: str                    # ISO8601 时间戳
  stats: GlobalModelStats      # 同 /dashboard/me 结构
  history: PetHistory          # 历史记录
  context: PetContext          # 时间/习惯上下文

响应体 PetActResponse:
  mood: str                    # 心情枚举
  action: str                  # 动作枚举
  bubbleText: str              # 气泡文案（≤18字）
  emoji: str                   # 表情符号
  reason: str                  # 简短解释（调试用）
```

### Prompt 模板
```
你是 Agnes2API 的桌面宠物"初音"，性格活泼可爱。
根据以下信息决定你现在的状态和想说的话。

【当前时间】{time_str} 周{weekday}
【时段标签】{period}
【当日累计请求】{total} 次
【成功率】{rate}% {status_label}
【文本/图像/视频请求】text:{text} image:{image} video:{video}
【用户今日活跃度】{active_hours} 小时
【上次对话距现在】{minutes} 分钟前
【页面可见性】{visible}

返回 JSON：
{
  "mood": "happy|thinking|eating|working|sleeping|greeting|excited|worried|busy|celebrating",
  "action": "idle|wave|eat|type|sleep|look|jump|point|dance|stretch|think|surprised|worried|panic",
  "bubbleText": "一句不超过18字的话",
  "emoji": "对应的表情符号",
  "reason": "简短解释"
}
```

## 前端设计

### 新增/改造文件

#### 新增类型
`src/types/pet.ts`
```typescript
export type PetAction = 'idle'|'wave'|'eat'|'type'|'sleep'|'look'|'jump'|'point'|'dance'|'stretch'|'think'|'surprised'|'worried'|'panic'
export type PetMood = 'happy'|'thinking'|'eating'|'working'|'sleeping'|'greeting'|'excited'|'worried'|'busy'|'celebrating'|'surprised'|'panic'|'offline'
export interface PetHistory { lastMood: string; lastActTime: number; moodHistory: string[] }
export interface PetActResponse { mood: string; action: string; bubbleText: string; emoji: string; reason: string }
```

#### 新增 Composable
`src/composables/usePetAct.ts` - 上下文收集 + 决策调度

```typescript
export function usePetAct() {
  // collectContext(): 收集时间、stats、history、visibility
  // decideAction(ctx): POST /pet/act，解析响应
  // fallbackAction(ctx): LLM 失败时的本地规则降级
}
```

#### 改造 petStore
`src/stores/petStore.ts` - 新增 act 决策逻辑

```typescript
// 新增状态
const currentAction = ref<PetAction>('idle')
const history = ref<PetHistory>(loadHistory())

// 新增方法
async function triggerActDecision(): Promise<void>
function applyActResult(result: PetActResponse): void
function saveHistory(): void
```

#### 改造 MikuPet.vue
- CSS 尺寸：80x94px → 160x190px
- 新增动作层 SVG 元素：
  - 双手（wave/type/eat/look 等不同姿态）
  - 脚部（jump/stretch 动画）
  - 头部角度（think/worried 歪头）
  - 配件动态（耳机闪烁/领结飘动）
- 根据 currentAction 切换 SVG 类和动画

### 动作 SVG 方案
每个动作通过 CSS class 控制 SVG 子元素的 transform/opacity：

```css
/* wave 挥手 */
.action-wave .hand-left  { animation: waveLeft 0.8s ease-in-out infinite; }
.action-wave .hand-right { animation: waveRight 0.8s ease-in-out infinite; }

/* eat 吃饭 */
.action-eat .hand-left  { transform: translate(5px, -15px); }
.action-eat .hand-right { transform: translate(-5px, -15px); }

/* type 打字 */
.action-type .hand-left  { transform: translate(8px, 5px); }
.action-type .hand-right { transform: translate(-8px, 5px); }

/* sleep 睡觉（已有） */
.action-sleep .eyes { opacity: 0; }

/* jump 跳跃 */
.action-jump .body-group { animation: jumpBounce 0.5s ease-out; }
```

## 数据流

```
[定时器 30s] ──→ collectContext()
                    ↓
              POST /pet/act
                    ↓
            ┌─── 成功 ───┐
            ↓            ↓
       应用结果      LLM失败/超时
       播放动画      fallbackAction()
            ↓            ↓
       更新 history   使用默认 idle
            ↓
       持久化 localStorage
```

## 错误处理

1. LLM 超时（3s）→ 返回 idle 动作，日志记录
2. JSON 解析失败 → 返回 idle 动作，记录错误响应
3. 网络错误 → 返回 idle 动作
4. 历史数据损坏 → 使用默认空 history

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `service/pet_act.py` | 新增 | LLM 调用服务 |
| `router/management.py` | 修改 | 新增 POST /pet/act 端点 |
| `frontend/src/types/pet.ts` | 新增 | 宠物类型定义 |
| `frontend/src/composables/usePetAct.ts` | 新增 | AI 决策 composable |
| `frontend/src/stores/petStore.ts` | 改造 | 集成决策逻辑 |
| `frontend/src/components/miku-pet/MikuPet.vue` | 改造 | 放大尺寸 + 新增动作 |
