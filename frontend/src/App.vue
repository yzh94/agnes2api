<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
/* ============================================================
   SCIFI — Refined Design System
   Linear / Vercel inspired: restrained, spacious, precise
   ============================================================ */

/* === Color Tokens === */
:root {
  /* Background — near-black, not blue-tinted */
  --bg-primary: #08090a;
  --bg-secondary: rgba(255, 255, 255, 0.03);
  --bg-tertiary: rgba(255, 255, 255, 0.02);
  --bg-elevated: rgba(255, 255, 255, 0.04);

  /* Border — hairline, barely visible */
  --border-subtle: rgba(255, 255, 255, 0.06);
  --border-default: rgba(255, 255, 255, 0.10);
  --border-hover: rgba(255, 255, 255, 0.16);
  --border-focus: rgba(99, 102, 241, 0.40);

  /* Accent — Indigo, not cyan. One color only. */
  --accent: #6366f1;
  --accent-light: #818cf8;
  --accent-dim: rgba(99, 102, 241, 0.12);
  --accent-glow: rgba(99, 102, 241, 0.25);

  /* Semantic colors — muted, not neon */
  --success: #34d399;
  --success-dim: rgba(52, 211, 153, 0.12);
  --warning: #fb923c;
  --warning-dim: rgba(251, 146, 60, 0.12);
  --danger: #f87171;
  --danger-dim: rgba(248, 113, 113, 0.12);
  --info: #60a5fa;
  --info-dim: rgba(96, 165, 250, 0.12);

  /* Text — high contrast on dark */
  --text-primary: #f4f4f5;
  --text-secondary: #a1a1aa;
  --text-tertiary: #71717a;
  --text-muted: #52525b;

  /* Element Plus overrides */
  --el-color-primary: #6366f1;
  --el-color-primary-light-3: #818cf8;
  --el-color-primary-light-5: rgba(99, 102, 241, 0.3);
  --el-color-primary-light-7: rgba(99, 102, 241, 0.15);
  --el-color-primary-light-9: rgba(99, 102, 241, 0.08);
  --el-color-primary-dark-2: #4f46e5;

  --el-color-success: #34d399;
  --el-color-warning: #fb923c;
  --el-color-danger: #f87171;
  --el-color-info: #94a3b8;

  --el-bg-color: #08090a;
  --el-bg-color-page: #08090a;
  --el-bg-color-overlay: #16161a;
  --el-fill-color: #16161a;
  --el-fill-color-light: #1c1c21;
  --el-fill-color-blank: #0c0c10;

  --el-border-color-light: rgba(255, 255, 255, 0.08);
  --el-border-color-lighter: rgba(255, 255, 255, 0.06);
  --el-border-color: rgba(255, 255, 255, 0.12);

  --el-text-color-primary: #f4f4f5;
  --el-text-color-regular: #c4c4cc;
  --el-text-color-secondary: #8b8b9e;
  --el-text-color-placeholder: #52525b;

  --el-border-radius-base: 6px;
  --el-border-radius-small: 4px;
  --el-border-radius-round: 20px;

  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.03);
  --el-table-row-hover-bg-color: rgba(255, 255, 255, 0.04);
  --el-table-border-color: rgba(255, 255, 255, 0.06);

  --el-font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif;
  --el-font-family-mono: 'SF Mono', 'Fira Code', 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
}

body {
  margin: 0;
  font-family: var(--el-font-family);
  background-color: var(--el-bg-color-page);
  color: var(--el-text-color-primary);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

*, *::before, *::after { box-sizing: border-box; }
html, body, #app { width: 100%; min-height: 100%; overflow-x: hidden; }

/* ============================================================
   ELEMENT PLUS OVERRIDES — Refined Dark
   ============================================================ */

/* 全局按钮 */
.el-button {
  font-weight: 500;
  border-radius: 6px !important;
  letter-spacing: 0.2px;
  transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1) !important;
  border: 1px solid var(--border-default) !important;
  background: var(--bg-secondary) !important;
  color: var(--text-secondary) !important;
}
.el-button:hover {
  border-color: var(--border-hover) !important;
  color: var(--text-primary) !important;
  background: var(--bg-elevated) !important;
}
.el-button:active {
  transform: scale(0.98);
}
.el-button--primary {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
  color: #fff !important;
  font-weight: 500 !important;
}
.el-button--primary:hover {
  background: var(--accent-light) !important;
  border-color: var(--accent-light) !important;
  box-shadow: 0 4px 12px var(--accent-dim) !important;
}
.el-button--danger {
  border-color: rgba(248, 113, 113, 0.3) !important;
  color: var(--danger) !important;
  background: var(--danger-dim) !important;
}
.el-button--danger:hover {
  background: rgba(248, 113, 113, 0.18) !important;
  border-color: rgba(248, 113, 113, 0.5) !important;
}
.el-button--warning {
  border-color: rgba(251, 146, 60, 0.3) !important;
  color: var(--warning) !important;
  background: var(--warning-dim) !important;
}
.el-button--info {
  border-color: rgba(96, 165, 250, 0.3) !important;
  color: var(--info) !important;
  background: var(--info-dim) !important;
}
.el-button--text {
  color: var(--accent-light) !important;
}
.el-button--text:hover {
  color: var(--accent) !important;
}
.el-button.is-disabled, .el-button.is-disabled:hover {
  background: var(--bg-tertiary) !important;
  border-color: var(--border-subtle) !important;
  color: var(--text-muted) !important;
}

/* 输入框 */
.el-input__wrapper {
  background-color: var(--bg-secondary) !important;
  box-shadow: 0 0 0 1px var(--border-subtle) inset !important;
  border-radius: 6px !important;
  transition: all 0.15s ease !important;
  padding: 7px 11px !important;
}
.el-input__wrapper:hover {
  box-shadow: 0 0 0 1px var(--border-default) inset !important;
}
.el-input__wrapper.is-focus {
  box-shadow: 0 0 0 1px var(--accent) inset, 0 0 0 3px var(--accent-dim) !important;
}
.el-input__inner {
  color: var(--el-text-color-primary) !important;
  font-size: 14px;
}
.el-input__inner::placeholder {
  color: var(--text-tertiary) !important;
}
.el-input-group__prepend, .el-input-group__append {
  background: var(--bg-secondary) !important;
  border-color: var(--border-subtle) !important;
  color: var(--text-secondary) !important;
  border-radius: 6px 0 0 6px !important;
}

/* 卡片 */
.el-card {
  background: var(--bg-primary) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  box-shadow: none !important;
  overflow: hidden;
}
.el-card:hover {
  border-color: var(--border-default) !important;
}
.el-card__header {
  border-bottom: 1px solid var(--border-subtle) !important;
  padding: 16px 20px !important;
  background: transparent !important;
}
.el-card__body {
  padding: 20px !important;
}
.el-card__footer {
  border-top: 1px solid var(--border-subtle) !important;
  padding: 12px 20px !important;
}

/* 标签 */
.el-tag {
  border-radius: 4px !important;
  font-weight: 500;
  font-size: 11px;
  letter-spacing: 0.3px;
  border: none !important;
  padding: 2px 8px !important;
}
.el-tag--success {
  background: var(--success-dim) !important;
  color: var(--success) !important;
}
.el-tag--danger {
  background: var(--danger-dim) !important;
  color: var(--danger) !important;
}
.el-tag--info {
  background: var(--info-dim) !important;
  color: var(--info) !important;
}
.el-tag--warning {
  background: var(--warning-dim) !important;
  color: var(--warning) !important;
}
.el-tag--primary {
  background: var(--accent-dim) !important;
  color: var(--accent-light) !important;
}
.el-tag--dark {
  background: var(--bg-elevated) !important;
  color: var(--text-secondary) !important;
}

/* 表格 */
.el-table {
  --el-table-border: 1px solid var(--border-subtle);
  --el-table-border-color: var(--border-subtle);
  background: transparent !important;
  font-size: 13px;
}
.el-table th.el-table__cell {
  background: rgba(255, 255, 255, 0.02) !important;
  color: var(--text-tertiary) !important;
  font-weight: 600 !important;
  font-size: 11px !important;
  letter-spacing: 0.5px !important;
  text-transform: uppercase;
  border-color: var(--border-subtle) !important;
  padding: 12px 16px !important;
}
.el-table td.el-table__cell {
  border-color: var(--border-subtle) !important;
  padding: 12px 16px !important;
  color: var(--text-secondary) !important;
}
.el-table__body tr:hover > td.el-table__cell {
  background: rgba(255, 255, 255, 0.03) !important;
}
.el-table--border .el-table__cell {
  border-color: var(--border-subtle) !important;
}

/* 对话框 */
.el-dialog {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default) !important;
  border-radius: 12px !important;
  box-shadow: 0 25px 50px rgba(0, 0, 0, 0.6) !important;
  max-width: 90vw !important;
}
.el-dialog__header {
  border-bottom: 1px solid var(--border-subtle) !important;
  padding: 20px 24px !important;
  margin-right: 0 !important;
}
.el-dialog__title {
  color: var(--text-primary) !important;
  font-weight: 600 !important;
  font-size: 15px !important;
  letter-spacing: -0.2px !important;
}
.el-dialog__body {
  color: var(--text-secondary) !important;
  padding: 24px !important;
}
.el-dialog__footer {
  border-top: 1px solid var(--border-subtle) !important;
  padding: 16px 24px !important;
}
.el-dialog__headerbtn .el-dialog__close {
  color: var(--text-tertiary) !important;
}
.el-dialog__headerbtn .el-dialog__close:hover {
  color: var(--text-primary) !important;
}

/* 消息提示 */
.el-message {
  border-radius: 8px !important;
  border: 1px solid var(--border-default) !important;
  background: var(--bg-elevated) !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4) !important;
}
.el-message--success .el-message__content { color: var(--success) !important; }
.el-message--error   .el-message__content { color: var(--danger) !important; }
.el-message--warning .el-message__content { color: var(--warning) !important; }
.el-message--info    .el-message__content { color: var(--info) !important; }

/* 空状态 */
.el-empty__description p {
  color: var(--text-tertiary) !important;
  font-size: 13px !important;
}

/* 分页器 */
.el-pagination.is-background .el-pager li:not(.disabled).active {
  background: var(--accent) !important;
  color: #fff !important;
  border-radius: 6px !important;
}
.el-pagination.is-background .el-pager li:not(.disabled):hover {
  background: var(--accent-dim) !important;
  color: var(--accent-light) !important;
}
.el-pagination button:not(:disabled):hover {
  color: var(--accent-light) !important;
}
.el-pagination__items {
  gap: 4px;
}

/* 滚动条 */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.2); }

/* 加载中 */
.el-loading-spinner .circular { stroke: var(--accent) !important; }
.el-loading-spinner .el-loading-text { color: var(--text-tertiary) !important; }

/* 切换开关 */
.el-switch.is-checked .el-switch__core {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
}
.el-switch__core::after {
  background: #fff !important;
}

/* 数字输入 */
.el-input-number .el-input__wrapper {
  background: var(--bg-secondary) !important;
  box-shadow: 0 0 0 1px var(--border-subtle) inset !important;
}

/* 下拉选择 */
.el-select .el-input__wrapper {
  background: var(--bg-secondary) !important;
  box-shadow: 0 0 0 1px var(--border-subtle) inset !important;
}
.el-select-dropdown {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default) !important;
  border-radius: 8px !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4) !important;
}
.el-select-dropdown__item:hover {
  background: var(--bg-secondary) !important;
}
.el-select-dropdown__item.selected {
  color: var(--accent-light) !important;
}

/* 确认框 */
.el-message-box {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default) !important;
  border-radius: 12px !important;
  box-shadow: 0 25px 50px rgba(0, 0, 0, 0.6) !important;
}
.el-message-box__title {
  color: var(--text-primary) !important;
  font-weight: 600;
}
.el-message-box__message {
  color: var(--text-secondary) !important;
}

/* 等宽字体类 */
.mono-font {
  font-family: var(--el-font-family-mono) !important;
  font-size: 12px;
  letter-spacing: 0.3px;
}

/* 页面过渡 */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(2px);
}
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-2px);
}

/* ============================================================
   RESPONSIVE
   ============================================================ */
@media (max-width: 768px) {
  .el-dialog { width: calc(100vw - 24px) !important; max-width: calc(100vw - 24px) !important; }
}
</style>
