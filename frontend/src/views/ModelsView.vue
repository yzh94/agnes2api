<template>
  <div class="models-view">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="card-title">可用模型列表</span>
            <span class="card-subtitle mono-font">已注册 {{ models.length }} 个模型</span>
          </div>
          <el-button type="primary" @click="openCreateDialog">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            添加模型
          </el-button>
        </div>
      </template>

      <!-- 桌面端表格 -->
      <el-table :data="models" v-loading="loading" class="desktop-table"
        :header-cell-style="{ background: 'transparent', color: 'var(--text-tertiary)', fontSize: '11px', fontWeight: '600' }">
        <el-table-column prop="name" label="模型名称" min-width="200">
          <template #default="{ row }">
            <span class="mono-font model-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="所属体系" min-width="130">
          <template #default="{ row }">
            <el-tag :type="getProviderTagType(row.provider)" effect="dark">{{ getProviderLabel(row.provider) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" min-width="110">
          <template #default="{ row }">
            <el-tag effect="plain" :type="getTypeTagType(row.type)">{{ getTypeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
         <el-table-column label="状态" min-width="120">
           <template #default="{ row }">
             <el-switch
               v-model="row.is_active"
               @change="(val) => handleToggleStatus(row, val as boolean)"
               active-color="#6366f1"
               inactive-color="rgba(255,255,255,0.08)"
             />
           </template>
         </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-popconfirm title="确认删除该模型？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 移动端卡片 -->
      <div v-if="!loading && models.length > 0" class="mobile-cards">
        <div v-for="model in models" :key="model.id" class="model-card">
          <div class="model-card-header">
            <span class="model-name mono-font">{{ model.name }}</span>
            <el-switch
              v-model="model.is_active"
              @change="(val) => handleToggleStatus(model, val as boolean)"
              size="small"
              active-color="#6366f1"
              inactive-color="rgba(255,255,255,0.08)"
            />
          </div>
          <div class="model-card-tags">
            <el-tag :type="getProviderTagType(model.provider)" size="small" effect="dark">{{ getProviderLabel(model.provider) }}</el-tag>
            <el-tag effect="plain" :type="getTypeTagType(model.type)" size="small">{{ getTypeLabel(model.type) }}</el-tag>
          </div>
          <div class="model-card-actions">
            <el-button size="small" @click="openEditDialog(model)">编辑</el-button>
            <el-popconfirm title="确认删除该模型？" @confirm="handleDelete(model.id)">
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
      :title="isEdit ? '编辑模型' : '添加模型'"
      width="440px"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-position="top">
        <el-form-item label="模型名称（API 标识）" prop="name">
          <el-input v-model="form.name" placeholder="例如：gpt-4o" />
        </el-form-item>
        <el-form-item label="所属体系" prop="provider">
          <el-select v-model="form.provider" style="width: 100%">
            <el-option label="共享（两个接口均可使用）" value="shared" />
            <el-option label="OpenAI" value="openai" />
            <el-option label="Gemini" value="gemini" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型类型" prop="type">
          <el-select v-model="form.type" style="width: 100%">
            <el-option label="文本" value="text" />
            <el-option label="图像" value="image" />
            <el-option label="视频" value="video" />
          </el-select>
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
import { fetchModels, createModel, updateModel, deleteModel } from '@/services/api'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/utils/errorMessage'
import type { AvailableModel } from '@/types/api'

const models = ref<AvailableModel[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const formRef = ref()

const form = ref({
  id: 0,
  name: '',
  provider: 'shared',
  type: 'text',
  is_active: true,
})

const rules = {
  name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  provider: [{ required: true, message: '请选择所属体系', trigger: 'change' }],
  type: [{ required: true, message: '请选择模型类型', trigger: 'change' }],
}

function getProviderTagType(provider: string) {
  if (provider === 'shared') return 'info'
  if (provider === 'openai') return 'success'
  if (provider === 'gemini') return 'primary'
  return 'warning'
}

function getTypeTagType(type: string) {
  if (type === 'text') return 'primary'
  if (type === 'image') return 'success'
  if (type === 'video') return 'warning'
  return 'info'
}

function getProviderLabel(provider: string) {
  const map: Record<string, string> = { shared: '共享', openai: 'OpenAI', gemini: 'Gemini' }
  return map[provider] ?? provider
}

function getTypeLabel(type: string) {
  const map: Record<string, string> = { text: '文本', image: '图像', video: '视频' }
  return map[type] ?? type
}

async function loadModels() {
  loading.value = true
  try {
    models.value = await fetchModels()
  } catch (err: any) {
    ElMessage.error(getErrorMessage(err, '加载失败'))
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  isEdit.value = false
  form.value = { id: 0, name: '', provider: 'shared', type: 'text', is_active: true }
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

function openEditDialog(row: AvailableModel) {
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
      if (isEdit.value) {
        await updateModel(form.value.id, { name: form.value.name, provider: form.value.provider, type: form.value.type, is_active: form.value.is_active })
        ElMessage.success('更新成功')
      } else {
        await createModel({ name: form.value.name, provider: form.value.provider, type: form.value.type })
        ElMessage.success('添加成功')
      }
      dialogVisible.value = false
      loadModels()
    } catch (err: any) {
      ElMessage.error(getErrorMessage(err, '保存失败'))
    } finally {
      submitting.value = false
    }
  })
}

async function handleToggleStatus(row: AvailableModel, val: boolean) {
  try {
    await updateModel(row.id, { name: row.name, provider: row.provider, type: row.type, is_active: val })
    ElMessage.success(val ? '已启用' : '已停用')
  } catch (err: any) {
    row.is_active = !val
    ElMessage.error(getErrorMessage(err, '状态更新失败'))
  }
}

async function handleDelete(id: number) {
  try {
    await deleteModel(id)
    ElMessage.success('删除成功')
    loadModels()
  } catch (err: any) {
    ElMessage.error(getErrorMessage(err, '删除失败'))
  }
}

onMounted(loadModels)
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

.model-name {
  font-family: var(--el-font-family-mono) !important;
  color: var(--text-primary);
  font-size: 13px;
}

.mobile-cards { display: none; }

.model-card {
  border: 1px solid var(--border-subtle);
  border-radius: 2px;
  padding: 14px;
  margin-bottom: 10px;
  background: var(--bg-secondary);
}

.model-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.model-card-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.model-card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .desktop-table { display: none; }
  .mobile-cards { display: block; }
  .model-card-header { gap: 12px; }
  .model-card-actions .el-button { flex: 1 1 calc(50% - 4px); margin-left: 0; }
}
</style>
