<template>
  <div class="upstream-view">
    <el-card class="main-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">上游通道配置</span>
          <div class="header-btns">
            <el-button type="warning" @click="handleValidateAll(100)">全量检验</el-button>
            <el-popconfirm
              title="确认删除所有已禁用的上游通道？此操作不可撤销。"
              confirm-button-text="确认删除"
              cancel-button-text="取消"
              confirm-button-type="danger"
              @confirm="handleCleanDisabled"
            >
              <template #reference>
                <el-button type="danger" plain>清理无效通道</el-button>
              </template>
            </el-popconfirm>
            <el-button type="primary" @click="showCreateDialog = true">添加通道</el-button>
          </div>
        </div>
      </template>

      <!-- 桌面端：表格视图 -->
      <el-table :data="upstreamStore.upstreamKeys" v-loading="upstreamStore.isLoading" class="desktop-table">
        <el-table-column prop="name" label="通道别名" min-width="150" />
        <el-table-column label="API Key (安全凭证)" min-width="200">
          <template #default="{ row }">
            <span class="mono-font text-secondary">{{ maskKey(row.key) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="权重" min-width="100">
          <template #default="{ row }">
            <el-tag size="small" type="info">x{{ row.weight }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.status === 'disabled' && row.disabled_reason"
              :content="row.disabled_reason"
              placement="top"
              effect="dark"
            >
              <el-tag type="danger" style="cursor: help;">已自动停用</el-tag>
            </el-tooltip>
            <el-tag v-else :type="row.status === 'active' ? 'success' : 'danger'">
              {{ row.status === 'active' ? '启用中' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="停用时间" min-width="160">
          <template #default="{ row }">
            <span v-if="row.disabled_at" class="text-secondary" style="font-size: 13px;">
              {{ new Date(row.disabled_at).toLocaleString() }}
            </span>
            <span v-else class="text-secondary">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="320">
          <template #default="{ row }">
            <el-button size="small" @click="handleValidateKey(row.id)">检验</el-button>
            <el-button size="small" @click="showWeightDialog(row)">调整权重</el-button>
            <el-button
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row.id, row.status)"
            >
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-popconfirm
              title="确定要删除此通道吗？(将触发热更新)"
              @confirm="handleDeleteKey(row.id)"
            >
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 移动端：卡片列表 -->
      <div v-if="!upstreamStore.isLoading && upstreamStore.upstreamKeys.length > 0" class="mobile-cards">
        <div v-for="key in upstreamStore.upstreamKeys" :key="key.id" class="key-card">
          <div class="key-card-header">
            <span class="key-name">{{ key.name }}</span>
            <el-tag :type="key.status === 'active' ? 'success' : 'danger'" size="small">
              {{ key.status === 'active' ? '启用中' : '已停用' }}
            </el-tag>
          </div>
          <div class="key-card-body">
            <div class="key-row">
              <span class="label">API Key</span>
              <span class="mono-font">{{ maskKey(key.key) }}</span>
            </div>
            <div class="key-row">
              <span class="label">权重</span>
              <el-tag size="small" type="info">x{{ key.weight }}</el-tag>
            </div>
            <div v-if="key.disabled_at" class="key-row">
              <span class="label">停用时间</span>
              <span class="text-secondary" style="font-size: 12px;">{{ new Date(key.disabled_at).toLocaleString() }}</span>
            </div>
            <el-tooltip
              v-if="key.status === 'disabled' && key.disabled_reason"
              :content="key.disabled_reason"
              placement="top"
            >
              <div class="key-row warning-row">
                <span class="label">原因</span>
                <span style="font-size: 12px; color: var(--el-color-warning);">{{ key.disabled_reason }}</span>
              </div>
            </el-tooltip>
          </div>
          <div class="key-card-actions">
            <el-button size="small" @click="handleValidateKey(key.id)">检验</el-button>
            <el-button size="small" @click="showWeightDialog(key)">调整权重</el-button>
            <el-button size="small" :type="key.status === 'active' ? 'warning' : 'success'" @click="toggleStatus(key.id, key.status)">
              {{ key.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-popconfirm title="确定要删除此通道吗？(将触发热更新)" @confirm="handleDeleteKey(key.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>

      <div v-if="!upstreamStore.isLoading && upstreamStore.upstreamKeys.length === 0" class="empty-state">
        <el-empty description="暂无上游通道配置" />
      </div>
    </el-card>

    <!-- 新建渠道对话框 -->
    <el-dialog v-model="showCreateDialog" title="添加上游通道" width="500px">
      <el-form @submit.prevent="handleCreateKey" label-position="top">
        <el-form-item label="通道别名 (方便识别)">
          <el-input v-model="createForm.name" placeholder="例如：Agnes-主节点-01" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="createForm.key" placeholder="sk-..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreateKey">保存配置</el-button>
      </template>
    </el-dialog>

    <!-- 调权对话框 -->
    <el-dialog v-model="showWeightDialogFlag" title="调整轮询权重" width="400px">
      <el-form @submit.prevent="handleUpdateWeight" label-position="top">
        <el-form-item label="轮询权重 (最小为 1)">
          <el-input-number v-model="editingWeight" :min="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showWeightDialogFlag = false">取消</el-button>
        <el-button type="primary" @click="handleUpdateWeight">确认调整</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useUpstreamStore } from '@/stores/upstream'
import { ElMessage } from 'element-plus'
import type { UpstreamKeyResponse } from '@/types/api'

const upstreamStore = useUpstreamStore()
const showCreateDialog = ref(false)
const showWeightDialogFlag = ref(false)
const createForm = ref({ name: '', key: '' })
const editingId = ref<number | null>(null)
const editingWeight = ref(1)

function maskKey(key: string) {
  if (key.length <= 8) return key
  return key.substring(0, 6) + '...' + key.substring(key.length - 4)
}

function handleCreateKey() {
  if (!createForm.value.name || !createForm.value.key) {
    ElMessage.error('请填写完整的通道信息')
    return
  }
  upstreamStore.handleCreateKey(createForm.value.name, createForm.value.key)
  showCreateDialog.value = false
  createForm.value = { name: '', key: '' }
}

function showWeightDialog(row: UpstreamKeyResponse) {
  editingId.value = row.id
  editingWeight.value = row.weight
  showWeightDialogFlag.value = true
}

function handleUpdateWeight() {
  if (editingId.value !== null) {
    upstreamStore.handleUpdateWeight(editingId.value, editingWeight.value)
    showWeightDialogFlag.value = false
  }
}

function toggleStatus(id: number, status: string) {
  upstreamStore.handleToggleStatus(id, status)
}

function handleDeleteKey(id: number) {
  upstreamStore.handleDeleteKey(id)
}

function handleValidateKey(id: number) {
  upstreamStore.handleValidateKey(id)
}

function handleValidateAll(concurrency: number) {
  upstreamStore.handleValidateAll(concurrency)
}

function handleCleanDisabled() {
  upstreamStore.handleCleanDisabled()
}

// 初始加载
upstreamStore.fetchUpstreamKeys()
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.header-btns {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.text-secondary {
  color: var(--el-text-color-secondary);
}

.empty-state {
  padding: 60px 0;
}

.mono-font {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
}

/* ========== 移动端卡片列表 ========== */
.mobile-cards {
  display: none;
}

.key-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  background: var(--el-bg-color-overlay);
}

.key-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.key-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.key-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.key-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  gap: 12px;
  min-width: 0;
}

.key-row .label {
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.warning-row {
  justify-content: flex-start;
  align-items: flex-start;
}

.key-card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .desktop-table {
    display: none;
  }

  .mobile-cards {
    display: block;
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-btns {
    width: 100%;
  }

  .header-btns .el-button {
    flex: 1 1 calc(50% - 4px);
    min-width: calc(50% - 4px);
    margin-left: 0;
  }

  .key-row > :last-child {
    min-width: 0;
    text-align: right;
    overflow-wrap: anywhere;
  }

  .warning-row > :last-child {
    text-align: left;
  }

  .key-card-actions .el-button {
    flex: 1 1 calc(50% - 4px);
    margin-left: 0;
  }
}
</style>
