<template>
  <div class="announcements-view">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="card-title">系统公告管理</span>
            <span class="card-subtitle mono-font">广播频道 &bull; {{ announcements.length }} 条公告</span>
          </div>
          <el-button type="primary" @click="openCreateDialog">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            发布公告
          </el-button>
        </div>
      </template>

      <!-- 桌面端：表格视图 -->
      <el-table :data="announcements" v-loading="loading" class="desktop-table"
        :header-cell-style="{ background: 'transparent', color: 'var(--text-tertiary)', fontSize: '11px', fontWeight: '600' }">
        <el-table-column label="置顶" width="60">
          <template #default="{ row }">
            <el-tag v-if="row.is_pinned" size="small" type="warning">置顶</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" />
        <el-table-column label="状态" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="排序" width="80">
          <template #default="{ row }">
            {{ row.sort_order }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button size="small" @click="togglePin(row)">
              {{ row.is_pinned ? '取消置顶' : '置顶' }}
            </el-button>
            <el-popconfirm
              title="确定删除此公告吗？"
              @confirm="handleDelete(row.id)"
            >
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 移动端：卡片列表 -->
      <div v-if="!loading && announcements.length > 0" class="mobile-cards">
        <div v-for="item in announcements" :key="item.id" class="announcement-card">
          <div class="ac-header">
            <div class="ac-title-row">
              <el-tag v-if="item.is_pinned" size="small" type="warning" effect="dark">置顶</el-tag>
              <span class="ac-title">{{ item.title }}</span>
            </div>
            <el-tag :type="item.is_active ? 'success' : 'info'" size="small">
              {{ item.is_active ? '启用' : '停用' }}
            </el-tag>
          </div>
          <div class="ac-body">
            <div class="ac-meta">
              <span>排序: {{ item.sort_order }}</span>
              <span>创建: {{ formatDate(item.created_at) }}</span>
              <span>更新: {{ formatDate(item.updated_at) }}</span>
            </div>
          </div>
          <div class="ac-actions">
            <el-button size="small" @click="openEditDialog(item)">编辑</el-button>
            <el-button size="small" @click="togglePin(item)">
              {{ item.is_pinned ? '取消置顶' : '置顶' }}
            </el-button>
            <el-popconfirm title="确定删除此公告吗？" @confirm="handleDelete(item.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑公告' : '发布公告'"
      width="700px"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-position="top">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="请输入公告标题" />
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="8"
            placeholder="请输入公告内容（支持换行）"
          />
        </el-form-item>
        <el-form-item label="置顶">
          <el-switch v-model="form.is_pinned" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" inline-prompt active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import {
  fetchAnnouncements,
  createAnnouncement,
  updateAnnouncement,
  deleteAnnouncement,
} from '@/services/api'

interface AnnouncementItem {
  id: number
  title: string
  content: string
  is_active: boolean
  is_pinned: boolean
  sort_order: number
  created_at: string | null
  updated_at: string | null
}

const announcements = ref<AnnouncementItem[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = ref({
  id: 0,
  title: '',
  content: '',
  is_active: true,
  is_pinned: false,
  sort_order: 0,
})

const rules: FormRules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  content: [
    {
      required: true,
      validator: (_rule: any, _value: any, callback: (e?: Error) => void) => {
        if (!form.value.content.trim()) callback(new Error('请输入内容'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

function formatDate(dateStr: string | null) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

async function loadAnnouncements() {
  loading.value = true
  try {
    announcements.value = await fetchAnnouncements()
  } catch {
    // http 拦截器已统一提示错误
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  isEdit.value = false
  form.value = { id: 0, title: '', content: '', is_active: true, is_pinned: false, sort_order: 0 }
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

function openEditDialog(row: AnnouncementItem) {
  isEdit.value = true
  form.value = { ...row }
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = {
        title: form.value.title,
        content: form.value.content,
        is_active: form.value.is_active,
        is_pinned: form.value.is_pinned,
        sort_order: form.value.sort_order,
      }
      if (isEdit.value) {
        await updateAnnouncement(form.value.id, payload)
        ElMessage.success('更新成功')
      } else {
        await createAnnouncement(payload)
        ElMessage.success('发布成功')
      }
      dialogVisible.value = false
      loadAnnouncements()
    } catch {
      // http 拦截器已统一提示错误
    } finally {
      submitting.value = false
    }
  })
}

async function togglePin(row: AnnouncementItem) {
  try {
    await updateAnnouncement(row.id, {
      title: row.title,
      content: row.content,
      is_active: row.is_active,
      is_pinned: !row.is_pinned,
      sort_order: row.sort_order,
    })
    loadAnnouncements()
  } catch {
    // http 拦截器已统一提示错误
  }
}

async function handleDelete(id: number) {
  try {
    await deleteAnnouncement(id)
    ElMessage.success('删除成功')
    loadAnnouncements()
  } catch {
    // http 拦截器已统一提示错误
  }
}

onMounted(loadAnnouncements)
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

.mobile-cards {
  display: none;
}

.announcement-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  background: var(--el-bg-color-overlay);
}

.ac-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
}

.ac-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.ac-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ac-body {
  margin-bottom: 12px;
}

.ac-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ac-actions {
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

  .ac-actions .el-button {
    flex: 1 1 calc(50% - 4px);
    margin-left: 0;
  }

  .ac-title-row {
    align-items: flex-start;
  }
}
</style>
