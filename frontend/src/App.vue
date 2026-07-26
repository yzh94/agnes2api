<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
/* 现代企业级 SaaS 风格 (Modern Dark SaaS) 全局变量覆盖 */
:root {
  /* 主色调 (沉稳的科技蓝) */
  --el-color-primary: #3b82f6;
  --el-color-primary-light-3: #60a5fa;
  --el-color-primary-light-5: #93c5fd;
  --el-color-primary-light-7: #bfdbfe;
  --el-color-primary-light-9: rgba(59, 130, 246, 0.1);
  --el-color-primary-dark-2: #2563eb;

  /* 辅助色 */
  --el-color-success: #10b981;
  --el-color-warning: #f59e0b;
  --el-color-danger: #ef4444;
  --el-color-info: #64748b;

  /* 页面深色背景 (Slate色系，加深层级感) */
  --el-bg-color: #0f172a;
  --el-bg-color-page: #020617;
  --el-bg-color-overlay: #1e293b;

  /* 边框和线条 (更柔和) */
  --el-border-color-light: #334155;
  --el-border-color-lighter: #1e293b;
  --el-border-color: #475569;

  /* 文本颜色 */
  --el-text-color-primary: #f8fafc;
  --el-text-color-regular: #cbd5e1;
  --el-text-color-secondary: #94a3b8;
  --el-text-color-placeholder: #64748b;

  /* 卡片和表格 */
  --el-fill-color-blank: #1e293b;
  --el-fill-color-light: #0f172a;
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: #0f172a;
  --el-table-row-hover-bg-color: #334155;
  --el-table-border-color: #334155;

  /* 优雅的圆角 */
  --el-border-radius-base: 8px;
  --el-border-radius-small: 6px;
  --el-border-radius-round: 20px;
}

body {
  margin: 0;
  /* 恢复符合人类阅读习惯的现代无衬线字体 */
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background-color: var(--el-bg-color-page);
  color: var(--el-text-color-primary);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

html,
body,
#app {
  width: 100%;
  min-height: 100%;
  overflow-x: hidden;
}

/* 只保留数据和代码部位的等宽字体 */
.mono-font {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'JetBrains Mono', Consolas, Monaco, monospace;
}

/* 按钮优雅过渡 */
.el-button {
  font-weight: 500;
  border-radius: 6px; /* 增加圆润感 */
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.el-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
}
.el-button:active {
  transform: translateY(0);
  box-shadow: none;
}

/* 空状态美化 */
.el-empty__description p {
  color: var(--el-text-color-secondary) !important;
  font-size: 14px !important;
}

/* 卡片轻拟物阴影 */
.el-card {
  border: 1px solid var(--el-border-color-light) !important;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;
  background-color: var(--el-bg-color-overlay) !important;
  transition: box-shadow 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.el-card:hover {
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;
}
.el-card__header {
  border-bottom: 1px solid var(--el-border-color-light) !important;
  padding: 16px 20px !important;
}

/* 对话框美化及移动端适配 */
.el-dialog {
  background-color: var(--el-bg-color-overlay) !important;
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px !important;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2) !important;
  /* 移动端自适应宽度 */
  max-width: 90vw !important;
}
.el-dialog__header {
  border-bottom: 1px solid var(--el-border-color-light) !important;
  margin-right: 0 !important;
  padding: 20px !important;
}
.el-dialog__title {
  font-weight: 600;
}
.el-dialog__footer {
  border-top: 1px solid var(--el-border-color-light) !important;
  padding: 16px 20px !important;
}

.el-dialog__footer .dialog-footer,
.el-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

/* 表格边框与悬停 */
.el-table {
  --el-table-border: 1px solid var(--el-border-color-light);
  --el-table-border-color: var(--el-border-color-light);
}
.el-table th.el-table__cell {
  font-weight: 600;
  color: var(--el-text-color-secondary);
}
.el-table__body tr:hover > td.el-table__cell {
  background-color: var(--el-table-row-hover-bg-color) !important;
}

/* 输入框柔和背景 */
.el-input__wrapper {
  background-color: var(--el-bg-color) !important;
  box-shadow: 0 0 0 1px var(--el-border-color-light) inset !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.el-input__wrapper:hover {
  box-shadow: 0 0 0 1px var(--el-border-color) inset !important;
}
.el-input__wrapper.is-focus {
  box-shadow: 0 0 0 1px var(--el-color-primary) inset !important;
}

/* 全局滚动条美化 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--el-border-color);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--el-text-color-secondary);
}

@media (max-width: 768px) {
  .el-card__header {
    padding: 14px 16px !important;
  }

  .el-card__body {
    padding: 16px !important;
  }

  .el-dialog {
    width: calc(100vw - 24px) !important;
    max-width: calc(100vw - 24px) !important;
    max-height: calc(100vh - 24px);
    margin: 12px auto !important;
    display: flex;
    flex-direction: column;
  }

  .el-dialog__body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 16px 20px !important;
  }

  .el-dialog__footer .el-button {
    margin-left: 0 !important;
  }
}

@media (max-width: 480px) {
  .el-card__header {
    padding: 12px !important;
  }

  .el-card__body {
    padding: 12px !important;
  }

  .el-dialog__header {
    padding: 16px !important;
  }

  .el-dialog__body {
    padding: 14px 16px !important;
  }

  .el-dialog__footer {
    padding: 12px 16px !important;
  }
}
</style>
