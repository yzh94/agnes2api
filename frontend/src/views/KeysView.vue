<template>
  <div class="keys-view">
    <el-card class="main-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="card-title">授权密钥管理</span>
            <span class="card-subtitle mono-font">密钥仓库 · 共 {{ keysStore.keys.length }} 条</span>
          </div>
          <el-button type="primary" @click="showCreateDialog = true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            生成新密钥
          </el-button>
        </div>
      </template>

      <!-- 桌面端表格 -->
      <el-table :data="keysStore.keys" v-loading="keysStore.isLoading" class="desktop-table"
        :header-cell-style="{ background: 'transparent', color: 'var(--text-tertiary)', fontSize: '11px', fontWeight: '600' }">
        <el-table-column prop="name" label="别名" min-width="140">
          <template #default="{ row }">
            <span class="mono-font key-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="密钥" min-width="220">
          <template #default="{ row }">
            <span class="mono-font text-secondary">{{ maskKey(row.key) }}</span>
            <el-button class="copy-btn" link type="primary" size="small" @click="copyKey(row.key)">
              <el-icon><CopyDocument /></el-icon> 复制
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'" effect="dark">
              <span class="tag-dot"></span>{{ row.status === 'active' ? '启用' : '已吊销' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="配额" min-width="110">
          <template #default="{ row }">
            <span class="quota-text mono-font">${{ row.used_quota.toFixed(4) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="280">
          <template #default="{ row }">
            <el-button size="small" type="info" @click="keysStore.handleResetKey(row.id)">重置</el-button>
            <el-button size="small" :type="row.status === 'active' ? 'warning' : 'success'" @click="keysStore.handleToggleStatus(row.id, row.status)">
              {{ row.status === 'active' ? '吊销' : '恢复' }}
            </el-button>
            <el-popconfirm title="确认永久删除该密钥？" @confirm="keysStore.handleDeleteKey(row.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-if="!keysStore.isLoading && keysStore.keys.length > 0" class="mobile-cards">
        <div v-for="key in keysStore.keys" :key="key.id" class="key-card">
          <div class="key-card-header">
            <span class="key-name mono-font">{{ key.name }}</span>
            <el-tag :type="key.status === 'active' ? 'success' : 'danger'" size="small" effect="dark">
              <span class="tag-dot"></span>{{ key.status === 'active' ? '启用' : '已吊销' }}
            </el-tag>
          </div>
          <div class="key-card-body">
            <div class="key-value">
              <span class="label mono-font">密钥</span>
              <span class="mono-font">{{ maskKey(key.key) }}</span>
              <el-button link type="primary" size="small" @click="copyKey(key.key)">
                <el-icon><CopyDocument /></el-icon> 复制
              </el-button>
            </div>
            <div class="key-value">
              <span class="label mono-font">配额</span>
              <span class="quota-text mono-font">${{ key.used_quota.toFixed(4) }}</span>
            </div>
          </div>
          <div class="key-card-actions">
            <el-button size="small" type="info" @click="keysStore.handleResetKey(key.id)">重置</el-button>
            <el-button size="small" :type="key.status === 'active' ? 'warning' : 'success'" @click="keysStore.handleToggleStatus(key.id, key.status)">
              {{ key.status === 'active' ? '吊销' : '恢复' }}
            </el-button>
            <el-popconfirm title="确认永久删除该密钥？" @confirm="keysStore.handleDeleteKey(key.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>

      <div v-if="!keysStore.isLoading && keysStore.keys.length === 0" class="empty-state mono-font">
        <el-empty description="暂无授权密钥" />
      </div>
    </el-card>

    <!-- 新建 Key 对话框 -->
    <el-dialog v-model="showCreateDialog" title="生成新密钥" width="420px">
      <el-form @submit.prevent="handleCreateKey" label-position="top">
        <el-form-item label="别名标识">
          <el-input v-model="newKeyName" placeholder="例如：production-primary-01" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreateKey">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useKeysStore } from '@/stores/keys'
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'
import { maskKey } from '@/utils/security'

const keysStore = useKeysStore()
const showCreateDialog = ref(false)
const newKeyName = ref('')

function copyKey(key: string) {
  navigator.clipboard.writeText(key)
  ElMessage.success('密钥已复制到剪贴板')
}

function handleCreateKey() {
  if (!newKeyName.value) {
    ElMessage.error('请填写别名标识')
    return
  }
  keysStore.handleCreateKey(newKeyName.value)
  showCreateDialog.value = false
  newKeyName.value = ''
}

keysStore.fetchKeys()
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.header-left { display: flex; flex-direction: column; gap: 4px; }

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 2px;
  text-transform: uppercase;
  font-family: var(--el-font-family-mono);
}

.card-subtitle {
  font-size: 10px;
  color: var(--text-tertiary);
  letter-spacing: 1px;
}

.copy-btn { margin-left: 8px; }
.quota-text { font-weight: 600; color: var(--warning); }
.text-secondary { color: var(--text-secondary); }

.empty-state { padding: 60px 0; }

.desktop-table { display: block; }
.mobile-cards { display: none; }

.key-card {
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
  padding: 14px;
  margin-bottom: 10px;
  background: var(--bg-secondary);
}
.key-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-default), transparent);
}
.key-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.key-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.5px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.key-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.key-value {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  min-width: 0;
}
.key-value .label { color: var(--text-tertiary); white-space: nowrap; min-width: 60px; }
.key-card-actions { display: flex; gap: 8px; flex-wrap: wrap; }

@media (max-width: 768px) {
  .desktop-table { display: none; }
  .mobile-cards { display: block; }
  .card-header { align-items: flex-start; }
  .card-title { min-width: 0; line-height: 28px; }
  .key-value .mono-font { min-width: 0; overflow-wrap: anywhere; }
  .key-card-actions .el-button { flex: 1 1 calc(33.333% - 6px); margin-left: 0; }
}
</style>
