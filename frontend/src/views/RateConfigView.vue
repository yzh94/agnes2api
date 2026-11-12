<template>
  <div class="rate-config">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title">速率限制配置</span>
          <span class="card-subtitle mono-font">限流控制面板</span>
        </div>
      </template>

      <el-form class="rate-form" label-position="top">
        <el-form-item label="是否启用速率限制">
          <el-switch
            v-model="enabled"
            active-text="启用"
            inactive-text="禁用"
          />
        </el-form-item>
        <el-form-item label="上传 Key 用户 RPM">
          <el-input-number v-model="uploaderRpm" :min="1" :max="1000" />
        </el-form-item>
        <el-form-item label="未上传 Key 用户 RPM">
          <el-input-number v-model="nonUploaderRpm" :min="1" :max="100" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="loading">保存配置</el-button>
        </el-form-item>
      </el-form>

      <el-alert
        title="说明"
        type="info"
        :closable="false"
        style="margin-top: 20px;"
      >
        <p>· RPM: 每分钟请求数限制</p>
        <p>· 上传 Key 的用户享有更高的 RPM 额度</p>
        <p>· 未上传 Key 的用户使用较低的 RPM 额度</p>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchSystemConfigs, updateSystemConfig } from '@/services/api'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/utils/errorMessage'
import type { SystemConfigResponse } from '@/types/api'

const enabled = ref(true)
const uploaderRpm = ref(60)
const nonUploaderRpm = ref(10)
const loading = ref(false)

async function loadConfigs() {
  try {
    const configs = await fetchSystemConfigs()
    configs.forEach((cfg: SystemConfigResponse) => {
      if (cfg.key === 'rate_limit_enabled') enabled.value = cfg.value === '1'
      if (cfg.key === 'rate_limit_uploader_rpm') uploaderRpm.value = parseInt(cfg.value, 10)
      if (cfg.key === 'rate_limit_non_uploader_rpm') nonUploaderRpm.value = parseInt(cfg.value, 10)
    })
  } catch (err) {
    console.error('Failed to load configs:', err)
  }
}

async function handleSave() {
  loading.value = true
  try {
    await updateSystemConfig('rate_limit_enabled', enabled.value ? '1' : '0')
    await updateSystemConfig('rate_limit_uploader_rpm', String(uploaderRpm.value))
    await updateSystemConfig('rate_limit_non_uploader_rpm', String(nonUploaderRpm.value))
    ElMessage.success('配置已保存')
  } catch (err: any) {
    ElMessage.error(getErrorMessage(err, '保存失败'))
  } finally {
    loading.value = false
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}
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
.rate-config { padding: 20px; }
.rate-form { max-width: 600px; }
.rate-form :deep(.el-input-number) { width: 180px; max-width: 100%; }
.rate-form :deep(.el-form-item__label) {
  color: var(--text-tertiary) !important;
  font-size: 12px !important;
  letter-spacing: 1px !important;
  text-transform: uppercase;
  font-family: var(--el-font-family-mono);
}
.rate-form :deep(.el-form-item) { margin-bottom: 20px; }
@media (max-width: 480px) {
  .rate-config { padding: 0; }
  .rate-form { max-width: 100%; }
  .rate-form :deep(.el-input-number) { width: 100%; }
}
</style>
