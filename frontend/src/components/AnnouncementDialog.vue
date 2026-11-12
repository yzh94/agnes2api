<template>
  <el-dialog
    v-model="store.showDialog"
    title="系统公告"
    :width="isMobile ? 'calc(100vw - 32px)' : '600px'"
    :close-on-click-modal="true"
  >
    <div v-if="store.visibleAnnouncements.length === 0" class="empty-tip">
      暂无公告
    </div>
    <div v-else class="announcement-list">
      <div
        v-for="item in store.visibleAnnouncements"
        :key="item.id"
        class="announcement-item"
      >
        <div class="item-header">
          <el-tag v-if="item.is_pinned" size="small" type="warning" effect="dark">置顶</el-tag>
          <span class="item-title">{{ item.title }}</span>
        </div>
        <div class="item-content">{{ item.content }}</div>
        <div class="item-footer">{{ formatDate(item.created_at) }}</div>
      </div>
    </div>
    <template #footer>
      <el-button @click="store.showDialog = false">关闭</el-button>
      <el-button type="primary" @click="handleMarkRead">我知道了</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { useAnnouncementStore } from '@/stores/announcement'
import { useDevice } from '@/composables/useDevice'

const store = useAnnouncementStore()
const { isMobile } = useDevice()

function formatDate(dateStr: string | null) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

function handleMarkRead() {
  store.dismissAll()
  store.showDialog = false
}
</script>

<style scoped>
.empty-tip {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 32px 0;
}

.announcement-list {
  max-height: 60vh;
  overflow-y: auto;
}

.announcement-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.announcement-item:last-child {
  border-bottom: none;
}

.item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.item-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.item-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
}

.item-footer {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
