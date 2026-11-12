<template>
  <div class="upstream-view">
    <el-card class="main-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="card-title">上游通道配置</span>
            <span class="card-subtitle mono-font">代理路由表</span>
          </div>
          <div class="header-search">
            <el-radio-group v-model="statusFilter" size="small">
              <el-radio-button label="">全部</el-radio-button>
              <el-radio-button label="active">正常</el-radio-button>
              <el-radio-button label="disabled">异常</el-radio-button>
            </el-radio-group>
            <el-input
              v-model="searchInput"
              placeholder="筛选通道别名或 Key"
              clearable
              size="default"
              style="width: 240px"
              @input="onSearchInput"
              @clear="onSearchClear"
            >
              <template #prefix>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
              </template>
            </el-input>
          </div>
          <div class="header-btns">
            <el-button type="warning" :loading="upstreamStore.validatingAll" @click="upstreamStore.handleValidateAll(100)">
              <svg v-if="!upstreamStore.validatingAll" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              失败 Key 检验
            </el-button>
            <el-popconfirm title="确认清除所有已停用通道？此操作不可撤销。" confirm-button-text="确认清除" cancel-button-text="取消" confirm-button-type="danger" @confirm="upstreamStore.handleCleanDisabled()">
              <template #reference>
                <el-button type="danger" plain>清理无效通道</el-button>
              </template>
            </el-popconfirm>
            <el-button type="primary" @click="showCreateDialog = true">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              添加通道
            </el-button>
          </div>
        </div>
      </template>

      <!-- 状态汇总栏 -->
      <div class="summary-bar">
        <span class="summary-item">
          <span class="summary-label mono-font">启用</span>
          <span class="summary-value success mono-font">{{ upstreamStore.summary.active }}</span>
        </span>
        <span class="summary-divider">|</span>
        <span class="summary-item">
          <span class="summary-label mono-font">停用</span>
          <span class="summary-value danger mono-font">{{ upstreamStore.summary.disabled }}</span>
        </span>
        <span class="summary-divider">|</span>
        <span class="summary-item">
          <span class="summary-label mono-font">总计</span>
          <span class="summary-value mono-font">{{ upstreamStore.summary.total }}</span>
        </span>
        <span class="summary-validation">
          <span class="summary-label mono-font">最近校验</span>
          <span class="summary-value mono-font">{{ upstreamStore.lastValidationAt || '—' }}</span>
        </span>
      </div>

      <!-- 失败 Key 检验进度条 -->
      <div v-if="upstreamStore.validatingAll" class="validation-progress">
        <span class="vp-label mono-font">失败 Key 检验中</span>
        <div class="vp-track"><div class="vp-fill" :style="{ width: validatePercent + '%' }"></div></div>
        <span class="vp-text mono-font">{{ upstreamStore.validateProgress.done }}/{{ upstreamStore.validateProgress.total || '?' }} · {{ validatePercent }}%</span>
      </div>

      <!-- 桌面端表格 -->
      <el-table :data="upstreamStore.upstreamKeys" v-loading="upstreamStore.isLoading" class="desktop-table"
        :header-cell-style="{ background: 'transparent', color: 'var(--text-tertiary)', fontSize: '11px', fontWeight: '600' }">
        <el-table-column prop="name" label="通道别名" min-width="160">
          <template #default="{ row }">
            <span class="mono-font channel-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="密钥" min-width="220">
          <template #default="{ row }">
            <span class="mono-font text-secondary">{{ maskKey(row.key) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="130">
          <template #default="{ row }">
            <el-tooltip v-if="row.status === 'disabled' && row.disabled_reason" :content="row.disabled_reason" placement="top" effect="dark">
              <el-tag type="danger" style="cursor: help;">自动停用</el-tag>
            </el-tooltip>
            <el-tag v-else :type="row.status === 'active' ? 'success' : 'danger'" effect="dark">
              <span class="tag-dot"></span>{{ row.status === 'active' ? '启用' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后使用" prop="last_used_at" sortable min-width="170">
          <template #default="{ row }">
            <span v-if="row.last_used_at" class="text-secondary mono-font" style="font-size: 12px;">
              {{ new Date(row.last_used_at).toLocaleString('zh-CN') }}
            </span>
            <span v-else class="text-secondary mono-font">从未使用</span>
          </template>
        </el-table-column>
        <el-table-column label="停用时间" min-width="170">
          <template #default="{ row }">
            <span v-if="row.disabled_at" class="text-secondary mono-font" style="font-size: 12px;">
              {{ new Date(row.disabled_at).toLocaleString('zh-CN') }}
            </span>
            <span v-else class="text-secondary mono-font">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="340">
          <template #default="{ row }">
            <el-button size="small" @click="upstreamStore.handleValidateKey(row.id)">校验</el-button>
            <el-button size="small" :type="row.status === 'active' ? 'warning' : 'success'" @click="upstreamStore.handleToggleStatus(row.id, row.status)">
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-popconfirm title="确认删除该通道？删除后热加载立即生效。" @confirm="upstreamStore.handleDeleteKey(row.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-if="!upstreamStore.isLoading && upstreamStore.upstreamKeys.length > 0" class="mobile-cards">
        <div v-for="key in upstreamStore.upstreamKeys" :key="key.id" class="key-card">
          <div class="key-card-header">
            <span class="key-name mono-font">{{ key.name }}</span>
            <el-tag :type="key.status === 'active' ? 'success' : 'danger'" size="small" effect="dark">
              <span class="tag-dot"></span>{{ key.status === 'active' ? '启用' : '离线' }}
            </el-tag>
          </div>
          <div class="key-card-body">
            <div class="key-row"><span class="label mono-font">密钥</span><span class="mono-font">{{ maskKey(key.key) }}</span></div>
            <div class="key-row"><span class="label mono-font">最后使用</span><span class="text-secondary mono-font" style="font-size: 12px;">{{ key.last_used_at ? new Date(key.last_used_at).toLocaleString('zh-CN') : '从未使用' }}</span></div>
            <div v-if="key.disabled_at" class="key-row"><span class="label mono-font">停用</span><span class="text-secondary mono-font" style="font-size: 12px;">{{ new Date(key.disabled_at).toLocaleString('zh-CN') }}</span></div>
            <el-tooltip v-if="key.status === 'disabled' && key.disabled_reason" :content="key.disabled_reason" placement="top">
              <div class="key-row warning-row">
                <span class="label mono-font">原因</span>
                <span class="mono-font" style="font-size: 12px; color: var(--warning);">{{ key.disabled_reason }}</span>
              </div>
            </el-tooltip>
          </div>
          <div class="key-card-actions">
            <el-button size="small" @click="upstreamStore.handleValidateKey(key.id)">校验</el-button>
            <el-button size="small" :type="key.status === 'active' ? 'warning' : 'success'" @click="upstreamStore.handleToggleStatus(key.id, key.status)">
              {{ key.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-popconfirm title="确认删除该通道？删除后热加载立即生效。" @confirm="upstreamStore.handleDeleteKey(key.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>

      <div v-if="!upstreamStore.isLoading && upstreamStore.upstreamKeys.length === 0" class="empty-state mono-font">
        <el-empty description="暂无上游通道配置" />
      </div>

      <div v-if="upstreamStore.total > 0" class="pagination-wrap">
        <el-pagination
          v-model:current-page="upstreamStore.currentPage"
          v-model:page-size="upstreamStore.pageSize"
          :page-sizes="pageSizeOptions"
          :total="upstreamStore.total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="upstreamStore.setPageSize"
          @current-change="upstreamStore.setPage"
        />
      </div>
    </el-card>

    <!-- 新建渠道对话框 -->
    <el-dialog v-model="showCreateDialog" title="添加上游通道" width="500px">
      <el-form @submit.prevent="handleCreateKey" label-position="top">
        <el-form-item label="通道别名">
          <el-input v-model="createForm.name" placeholder="例如：agnes-primary-node-01" />
        </el-form-item>
        <el-form-item label="密钥">
          <el-input v-model="createForm.key" placeholder="sk-..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreateKey">保存配置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useUpstreamStore } from '@/stores/upstream'
import { ElMessage } from 'element-plus'
import { maskKey } from '@/utils/security'

const upstreamStore = useUpstreamStore()
const showCreateDialog = ref(false)
const createForm = ref({ name: '', key: '' })
const pageSizeOptions = [10, 20, 50, 100]
const searchInput = ref('')
const statusFilter = computed({
  get: () => upstreamStore.statusFilter,
  set: (v: string) => upstreamStore.setStatusFilter(v),
})
let searchTimer: ReturnType<typeof setTimeout> | null = null

// 防抖搜索：输入停止 350ms 后触发后端筛选
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    upstreamStore.setSearchKeyword(searchInput.value)
  }, 350)
}

function onSearchClear() {
  if (searchTimer) clearTimeout(searchTimer)
  searchInput.value = ''
  upstreamStore.setSearchKeyword('')
}

onMounted(() => {
  upstreamStore.fetchUpstreamKeys()
  // 挂载时同步检验状态：若有进行中的失败 Key 检验（含定时任务），接管进度展示
  upstreamStore.syncValidationState()
  // 启动实时轮询（Redis 状态变化时前端能在 15s 内反映）
  upstreamStore.startPolling()
})

onUnmounted(() => {
  upstreamStore.stopPolling()
  if (searchTimer) clearTimeout(searchTimer)
})

// 失败 Key 检验进度百分比（total 未知时按 0 显示，进度条静止在起点）
const validatePercent = computed(() => {
  const { done, total } = upstreamStore.validateProgress
  return total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
})

function handleCreateKey() {
  if (!createForm.value.name || !createForm.value.key) {
    ElMessage.error('请填写完整的通道信息')
    return
  }
  upstreamStore.handleCreateKey(createForm.value.name, createForm.value.key)
  showCreateDialog.value = false
  createForm.value = { name: '', key: '' }
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header-left { display: flex; flex-direction: column; gap: 4px; }

.header-search { flex: 0 0 auto; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

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

.text-secondary { color: var(--text-tertiary); }

.empty-state { padding: 60px 0; }

/* 状态汇总栏 */
.summary-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin-bottom: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
  font-size: 12px;
}

.summary-item { display: inline-flex; align-items: center; gap: 6px; }
.summary-label { color: var(--text-tertiary); }
.summary-value { font-weight: 600; color: var(--text-primary); }
.summary-value.success { color: var(--success); }
.summary-value.danger { color: var(--danger); }
.summary-divider { color: var(--border-default); }
.summary-validation { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; }

/* 失败 Key 检验进度条 */
.validation-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  margin: -8px 0 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
  font-size: 12px;
}
.vp-label { color: var(--text-tertiary); white-space: nowrap; }
.vp-track { flex: 1; height: 4px; background: var(--border-subtle); border-radius: 2px; overflow: hidden; }
.vp-fill { height: 100%; background: var(--el-color-warning); transition: width 0.5s ease; }
.vp-text { color: var(--text-primary); font-weight: 600; white-space: nowrap; }

.pagination-wrap { display: flex; justify-content: flex-end; padding-top: 16px; }
.desktop-table { display: block; }
.mobile-cards { display: none; }

.key-card {
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
  padding: 14px;
  margin-bottom: 10px;
  background: var(--bg-secondary);
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
.key-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  min-width: 0;
}
.key-row .label { color: var(--text-tertiary); white-space: nowrap; min-width: 60px; }
.key-card-actions { display: flex; gap: 8px; flex-wrap: wrap; }

@media (max-width: 768px) {
  .desktop-table { display: none; }
  .mobile-cards { display: block; }
  .card-header { align-items: flex-start; }
  .card-title { min-width: 0; line-height: 28px; }
  .key-row .mono-font { min-width: 0; overflow-wrap: anywhere; }
  .key-card-actions .el-button { flex: 1 1 calc(25% - 6px); margin-left: 0; }
  .summary-bar { flex-wrap: wrap; gap: 6px; }
  .summary-validation { margin-left: 0; width: 100%; }
}
</style>
