<template>
  <div class="keys-view">
    <el-card class="main-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">授权密钥管理</span>
          <el-button type="primary" @click="showCreateDialog = true">生成新密钥</el-button>
        </div>
      </template>

      <!-- 桌面端：表格视图 -->
      <el-table :data="keysStore.keys" v-loading="keysStore.isLoading" class="desktop-table">
        <el-table-column prop="name" label="别名标识" min-width="120" />
        <el-table-column label="API Key (安全令牌)" min-width="200">
          <template #default="{ row }">
            <span class="mono-font text-secondary">{{ maskKey(row.key) }}</span>
            <el-button class="copy-btn" link type="primary" size="small" @click="copyKey(row.key)">
              <el-icon><CopyDocument /></el-icon> 复制
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'">
              {{ row.status === 'active' ? '活跃' : '已吊销' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="已用额度" min-width="100">
          <template #default="{ row }">
            <span class="quota-text">${{ row.used_quota.toFixed(4) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="220">
          <template #default="{ row }">
            <el-button size="small" type="info" @click="keysStore.handleResetKey(row.id)">
              重置
            </el-button>
            <el-button
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row.id, row.status)"
            >
              {{ row.status === 'active' ? '吊销' : '恢复' }}
            </el-button>
            <el-popconfirm
              title="确定要永久删除此密钥吗？"
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
      <div v-if="!keysStore.isLoading && keysStore.keys.length > 0" class="mobile-cards">
        <div v-for="key in keysStore.keys" :key="key.id" class="key-card">
          <div class="key-card-header">
            <span class="key-name">{{ key.name }}</span>
            <el-tag :type="key.status === 'active' ? 'success' : 'danger'" size="small">
              {{ key.status === 'active' ? '活跃' : '已吊销' }}
            </el-tag>
          </div>
          <div class="key-card-body">
            <div class="key-value">
              <span class="label">API Key</span>
              <span class="mono-font">{{ maskKey(key.key) }}</span>
              <el-button link type="primary" size="small" @click="copyKey(key.key)">
                <el-icon><CopyDocument /></el-icon> 复制
              </el-button>
            </div>
            <div class="key-value">
              <span class="label">已用额度</span>
              <span class="quota-text">${{ key.used_quota.toFixed(4) }}</span>
            </div>
          </div>
          <div class="key-card-actions">
            <el-button size="small" type="info" @click="keysStore.handleResetKey(key.id)">重置</el-button>
            <el-button size="small" :type="key.status === 'active' ? 'warning' : 'success'" @click="toggleStatus(key.id, key.status)">
              {{ key.status === 'active' ? '吊销' : '恢复' }}
            </el-button>
            <el-popconfirm title="确定要永久删除此密钥吗？" @confirm="handleDeleteKey(key.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>

      <div v-if="!keysStore.isLoading && keysStore.keys.length === 0" class="empty-state">
        <el-empty description="暂无授权密钥" />
      </div>
    </el-card>

    <!-- 新建 Key 对话框 -->
    <el-dialog v-model="showCreateDialog" title="生成新密钥" width="400px">
      <el-form @submit.prevent="handleCreateKey" label-position="top">
        <el-form-item label="别名标识">
          <el-input v-model="newKeyName" placeholder="例如：测试环境接入" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreateKey">确认生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useKeysStore } from '@/stores/keys'
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'

const keysStore = useKeysStore()
const showCreateDialog = ref(false)
const newKeyName = ref('')

function maskKey(key: string) {
  if (key.length <= 8) return key
  return key.substring(0, 6) + '...' + key.substring(key.length - 4)
}

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

function toggleStatus(id: number, status: string) {
  keysStore.handleToggleStatus(id, status)
}

function handleDeleteKey(id: number) {
  keysStore.handleDeleteKey(id)
}

// 初始加载
keysStore.fetchKeys()
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

.copy-btn {
  margin-left: 8px;
}

.quota-text {
  font-weight: 600;
  color: var(--el-color-warning);
}

.text-secondary {
  color: var(--el-text-color-secondary);
}

.empty-state {
  padding: 60px 0;
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
  gap: 10px;
  margin-bottom: 14px;
}

.key-value {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  min-width: 0;
}

.key-value .label {
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  min-width: 60px;
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
    align-items: flex-start;
  }

  .card-title {
    min-width: 0;
    line-height: 32px;
  }

  .key-value .mono-font {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .key-card-actions .el-button {
    flex: 1 1 calc(33.333% - 6px);
    margin-left: 0;
  }
}
</style>
