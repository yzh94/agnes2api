import { defineStore } from 'pinia'
import { ref } from 'vue'
import { changePassword } from '@/services/auth'
import { useAuthStore } from './auth'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/utils/errorMessage'

function makeAuthStore() { return useAuthStore() }

export const usePwdStore = defineStore('pwd', () => {
  const showModal = ref(false)
  const form = ref({ old: '', new: '', confirm: '' })

  async function handleChangePassword() {
    if (form.value.new !== form.value.confirm) {
      ElMessage.error('两次输入的新密码不一致')
      return
    }
    try {
      await changePassword(form.value.old, form.value.new)
      ElMessage.success('密码修改成功，请重新登录')
      showModal.value = false
      makeAuthStore().logout()
    } catch (err: any) {
      ElMessage.error(getErrorMessage(err, '密码修改失败'))
    }
  }

  return {
    showModal,
    form,
    handleChangePassword,
  }
})
