<template>
  <div class="user-management">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="card-title">用户管理</span>
            <span class="card-subtitle mono-font">已注册 {{ total }} 个用户</span>
          </div>
          <el-button type="primary" @click="showCreateDialog = true">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            创建用户
          </el-button>
        </div>
      </template>

      <!-- 桌面端表格 -->
      <el-table :data="users" v-loading="loading" class="desktop-table"
        :header-cell-style="{ background: 'transparent', color: 'var(--text-tertiary)', fontSize: '11px', fontWeight: '600' }">
        <el-table-column prop="username" label="用户名" min-width="140">
          <template #default="{ row }">
            <span class="mono-font user-name">{{ row.username }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'warning' : 'info'" size="small" effect="dark">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上传 Key" width="110">
          <template #default="{ row }">
            <el-tag :type="row.has_upstream_key ? 'success' : 'danger'" size="small" effect="dark">
              {{ row.has_upstream_key ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文本" width="130">
          <template #default="{ row }">
            <span class="mono-font stat-cell">
              {{ row.text_total }}
              <span :style="{ color: getRateColor(calcSuccessRate(row.text_total, row.text_success)) }">
                ({{ calcSuccessRate(row.text_total, row.text_success) }}%)
              </span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="图像" width="130">
          <template #default="{ row }">
            <span class="mono-font stat-cell">
              {{ row.image_total }}
              <span :style="{ color: getRateColor(calcSuccessRate(row.image_total, row.image_success)) }">
                ({{ calcSuccessRate(row.image_total, row.image_success) }}%)
              </span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="视频" width="130">
          <template #default="{ row }">
            <span class="mono-font stat-cell">
              {{ row.video_total }}
              <span :style="{ color: getRateColor(calcSuccessRate(row.video_total, row.video_success)) }">
                ({{ calcSuccessRate(row.video_total, row.video_success) }}%)
              </span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="Discord" width="150">
          <template #default="{ row }">
            <span v-if="row.discord_username" class="discord-cell mono-font">
              <svg class="discord-icon" viewBox="0 0 24 24" fill="#5865F2" width="14" height="14"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg>
              {{ row.discord_username }}
            </span>
            <span v-else class="mono-font text-tertiary">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210">
          <template #default="{ row }">
            <el-button size="small" @click="resetPassword(row)">重置密码</el-button>
            <el-popconfirm title="确认删除该用户？" @confirm="handleDelete(row)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-if="!loading && users.length > 0" class="mobile-cards">
        <div v-for="user in users" :key="user.id" class="user-card">
          <div class="uc-header">
            <span class="uc-name mono-font">{{ user.username }}</span>
            <el-tag :type="user.role === 'admin' ? 'warning' : 'info'" size="small" effect="dark">
              {{ user.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </div>
          <div class="uc-stats">
            <div class="stat-row"><span class="label mono-font">上传 Key</span><span class="mono-font">{{ user.has_upstream_key ? '是' : '否' }}</span></div>
            <div class="stat-row"><span class="label mono-font">文本</span><span class="mono-font">{{ user.text_total }} ({{ calcSuccessRate(user.text_total, user.text_success) }}%)</span></div>
            <div class="stat-row"><span class="label mono-font">图像</span><span class="mono-font">{{ user.image_total }} ({{ calcSuccessRate(user.image_total, user.image_success) }}%)</span></div>
            <div class="stat-row"><span class="label mono-font">视频</span><span class="mono-font">{{ user.video_total }} ({{ calcSuccessRate(user.video_total, user.video_success) }}%)</span></div>
            <div v-if="user.discord_username" class="stat-row discord-row">
              <span class="label mono-font"><svg class="discord-icon" viewBox="0 0 24 24" fill="#5865F2" width="12" height="12" style="vertical-align:-2px;margin-right:3px"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.645.874-1.313 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.128-.094.256-.192.372-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg>Discord</span><span class="mono-font discord-val">{{ user.discord_username }}</span></div>
            <div v-else class="stat-row"><span class="label mono-font">Discord</span><span class="mono-font text-tertiary">—</span></div>
          </div>
          <div class="uc-actions">
            <el-button size="small" @click="resetPassword(user)">重置密码</el-button>
            <el-popconfirm title="确认删除该用户？" @confirm="handleDelete(user)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="pageSizeOptions"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="handlePageSizeChange"
          @current-change="handleCurrentPageChange"
        />
      </div>
    </el-card>

    <!-- 创建用户弹窗 -->
    <el-dialog v-model="showCreateDialog" title="创建用户" width="420px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" @submit.prevent="handleCreate" label-position="top">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" />
        </el-form-item>
        <el-form-item label="登录密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog v-model="showResetDialog" title="重置登录密码" width="420px">
      <el-form ref="resetFormRef" :model="resetForm" :rules="resetRules" @submit.prevent="handleResetPassword" label-position="top">
        <el-form-item label="新密码" prop="password">
          <el-input v-model="resetForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input v-model="resetForm.confirm" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showResetDialog = false">取消</el-button>
        <el-button type="primary" @click="handleResetPassword">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchUsers, createUser, resetUserPassword, deleteUser } from '@/services/api'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/utils/errorMessage'
import type { UserListItem } from '@/types/api'
import type { FormInstance, FormRules } from 'element-plus'

const users = ref<UserListItem[]>([])
const total = ref(0)
const loading = ref(false)
const showCreateDialog = ref(false)
const showResetDialog = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)
const pageSizeOptions = [10, 20, 50, 100]

const createFormRef = ref<FormInstance>()
const resetFormRef = ref<FormInstance>()
const createForm = ref({ username: '', password: '' })
const resetForm = ref({ userId: 0, password: '', confirm: '' })

const createRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const resetRules: FormRules = {
  password: [{ required: true, message: '请输入新密码', trigger: 'blur' }],
  confirm: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: (_rule: any, value: string, callback: (e?: Error) => void) => {
      if (value !== resetForm.value.password) callback(new Error('两次密码不一致'))
      else callback()
    }},
  ],
}

const calcSuccessRate = (total: number, success: number) => total > 0 ? ((success / total) * 100).toFixed(1) : '0.0'

function getRateColor(rate: string) {
  const n = parseFloat(rate)
  if (n > 90) return 'var(--success)'
  if (n > 60) return 'var(--warning)'
  return 'var(--danger)'
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  loadUsers()
}

function handleCurrentPageChange(page: number) {
  currentPage.value = page
  loadUsers()
}

async function loadUsers(retryPreviousPage = true) {
  loading.value = true
  try {
    const res = await fetchUsers(currentPage.value, pageSize.value)
    users.value = res.items
    total.value = res.total
    if (retryPreviousPage && users.value.length === 0 && total.value > 0 && currentPage.value > 1) {
      currentPage.value -= 1
      await loadUsers(false)
    }
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    try {
      await createUser(createForm.value.username, createForm.value.password)
      ElMessage.success('用户创建成功')
      showCreateDialog.value = false
      createForm.value = { username: '', password: '' }
      currentPage.value = 1
      loadUsers()
    } catch (err: any) {
      ElMessage.error(getErrorMessage(err, '创建失败'))
    }
  })
}

function resetPassword(row: UserListItem) {
  resetForm.value.userId = row.id
  resetForm.value.password = resetForm.value.confirm = ''
  showResetDialog.value = true
  if (resetFormRef.value) resetFormRef.value.clearValidate()
}

async function handleResetPassword() {
  if (!resetFormRef.value) return
  await resetFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    try {
      await resetUserPassword(resetForm.value.userId, resetForm.value.password)
      ElMessage.success('密码重置成功')
      showResetDialog.value = false
    } catch (err: any) {
      ElMessage.error(getErrorMessage(err, '重置失败'))
    }
  })
}

async function handleDelete(row: UserListItem) {
  try {
    await deleteUser(row.id)
    ElMessage.success('用户已删除')
    loadUsers()
  } catch (err: any) {
    ElMessage.error(getErrorMessage(err, '删除失败'))
  }
}

onMounted(loadUsers)
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

.user-name {
  color: var(--text-primary);
  font-size: 13px;
}

.stat-cell {
  color: var(--text-tertiary);
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}

.mobile-cards { display: none; }

.user-card {
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
  padding: 14px;
  margin-bottom: 10px;
  background: var(--bg-secondary);
}

.uc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.uc-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.5px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.uc-stats {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  gap: 12px;
}

.stat-row .label {
  color: var(--text-tertiary);
  white-space: nowrap;
}

.uc-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.discord-cell {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-primary);
  font-size: 12px;
}

.discord-icon {
  flex-shrink: 0;
}

.discord-val {
  color: var(--text-primary);
}

@media (max-width: 768px) {
  .desktop-table { display: none; }
  .mobile-cards { display: block; }
  .pagination-wrap { justify-content: center; }
  :deep(.el-pagination) { flex-wrap: wrap; justify-content: center; gap: 8px 4px; white-space: normal; }
  :deep(.el-pagination__total), :deep(.el-pagination__sizes), :deep(.el-pagination__jump) { display: none; }
  .uc-actions .el-button { flex: 1 1 calc(50% - 4px); margin-left: 0; }
}
</style>
