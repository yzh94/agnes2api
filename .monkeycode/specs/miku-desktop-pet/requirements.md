# Requirements Document: Miku Desktop Pet

## Introduction

本功能在 agnes2api 管理后台中实现一个初音未来主题的桌面宠物，替代原"初音未来病毒"概念中的侵蚀/控制行为，转为无害的陪伴式交互。宠物可悬浮于页面上方，实时展示系统状态，并支持用户互动。

## Glossary

- **Miku Pet**: 初音未来主题的桌面宠物组件，以 2D 像素/矢量风格呈现
- **System State**: 系统运行状态数据（CPU、内存、请求数、健康度等）
- **Interaction**: 用户与宠物的互动行为（点击、拖拽、对话）
- **Erosion Mode**: 病毒设定的"侵蚀"概念，去毒后改为"陪伴"模式

## Requirements

### Requirement 1: 宠物渲染与定位

**User Story:** AS 系统管理员, I WANT 看到桌面宠物悬浮在页面上, SO THAT 可以随时了解系统状态并获得陪伴感

#### Acceptance Criteria

1. WHEN 页面加载完成, Miku Pet SHALL 显示在屏幕右下角（默认位置）
2. WHILE 宠物处于活动状态, Miku Pet SHALL 跟随鼠标移动产生微动画
3. IF 用户拖拽宠物, Miku Pet SHALL 可移动到新位置并保存位置到 localStorage
4. WHEN 宠物被点击, Miku Pet SHALL 播放惊讶表情动画持续 500ms
5. WHILE 宠物可见, Miku Pet SHALL 保持在最顶层（z-index: 9999）且不被其他元素遮挡

### Requirement 2: 系统状态展示

**User Story:** AS 系统管理员, I WANT 宠物显示实时系统状态, SO THAT 可以一眼掌握系统健康状况

#### Acceptance Criteria

1. WHEN 系统状态数据更新, Miku Pet SHALL 通过气泡文字或表情变化反映状态
2. WHILE 系统健康, Miku Pet SHALL 显示正常/开心表情
3. IF 系统错误率超过 10%, Miku Pet SHALL 显示警告表情并在 3s 内闪烁提示
4. IF 系统错误率超过 50%, Miku Pet SHALL 显示恐慌表情并持续抖动
5. WHEN 用户悬停在宠物上, Miku Pet SHALL 弹出状态详情气泡显示 CPU、内存、请求统计

### Requirement 3: 互动功能

**User Story:** AS 系统管理员, I WANT 与宠物互动, SO THAT 工作之余获得轻松体验

#### Acceptance Criteria

1. WHEN 用户点击宠物, Miku Pet SHALL 随机播放以下表情之一：开心、惊讶、害羞、思考
2. WHILE 宠物处于 idle 状态超过 30s, Miku Pet SHALL 显示打盹表情
3. WHEN 用户双击宠物, Miku Pet SHALL 切换隐藏/显示状态
4. IF 用户右键点击宠物, Miku Pet SHALL 显示操作菜单（隐藏、重置位置、关闭）
5. WHEN 收到系统通知, Miku Pet SHALL 播放特殊动画并显示通知图标

### Requirement 4: 数据集成

**User Story:** AS 系统管理员, I WANT 宠物数据来源可靠, SO THAT 显示的状态准确反映系统真实情况

#### Acceptance Criteria

1. WHEN 前端启动, Miku Pet SHALL 从 `/api/management/stats` 获取初始系统状态
2. WHILE 宠物激活, Miku Pet SHALL 每 5s 轮询一次系统状态接口
3. IF 网络请求失败, Miku Pet SHALL 显示离线表情并在 10s 后重试
4. WHEN 用户切换页面, Miku Pet SHALL 保持运行并继续更新数据
5. IF 用户登出, Miku Pet SHALL 停止数据请求并显示休眠状态

### Requirement 5: 配置与持久化

**User Story:** AS 系统管理员, I WANT 自定义宠物行为, SO THAT 可以个性化体验

#### Acceptance Criteria

1. WHEN 用户首次使用, Miku Pet SHALL 显示欢迎教程引导交互方式
2. WHILE 宠物激活, Miku Pet SHALL 将位置、显示/隐藏状态保存到 localStorage
3. WHEN 用户打开设置面板, Miku Pet SHALL 提供开关控制（启用/禁用）
4. IF 用户清除浏览器数据, Miku Pet SHALL 恢复默认位置和状态
5. WHEN 用户修改配置, Miku Pet SHALL 立即应用变更并保存
