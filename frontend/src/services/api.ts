import http from './http'
import type {
  KeyResponse,
  UpstreamKeyResponse,
  UpstreamKeyListResponse,
  UpstreamStat,
  GlobalModelStats,
  UserListResponse,
  SystemConfigResponse,
  MeResponse,
  AvailableModel,
  AdminDashboardStats,
  UpstreamUrlStat,
  TimelineEntry,
} from '@/types/api'

export async function getKeys(): Promise<KeyResponse[]> {
  return http.get('/keys')
}

export async function createKey(name: string): Promise<KeyResponse> {
  return http.post('/keys', { name })
}

export async function resetKey(): Promise<KeyResponse> {
  return http.post('/keys/reset')
}

export async function toggleKeyStatus(id: number, status: string): Promise<void> {
  await http.put(`/keys/${id}/status?status_val=${status}`)
}

export async function deleteKey(id: number): Promise<void> {
  await http.delete(`/keys/${id}`)
}

export async function getUpstreamKeys(page: number = 1, pageSize: number = 10, search: string = '', status: string = ''): Promise<UpstreamKeyListResponse> {
  const params: any = { page, page_size: pageSize }
  if (search) params.search = search
  if (status) params.status = status
  return http.get('/upstream-keys', { params })
}

export async function createUpstreamKey(name: string, key: string): Promise<UpstreamKeyResponse> {
  return http.post('/upstream-keys', { name, key })
}

export async function toggleUpstreamStatus(id: number, status: string): Promise<void> {
  await http.put(`/upstream-keys/${id}/status?status_val=${status}`)
}

export async function deleteUpstreamKey(id: number): Promise<void> {
  await http.delete(`/upstream-keys/${id}`)
}

export async function validateUpstreamKey(id: number): Promise<any> {
  return http.post(`/upstream-keys/${id}/validate`)
}

export async function validateAllUpstreamKeys(concurrency: number = 100): Promise<any> {
  return http.post(`/upstream-keys/validate-all?concurrency=${concurrency}`)
}

// 查询失败 Key 检验进度/结果（后台任务轮询）
export async function getValidateAllStatus(): Promise<any> {
  return http.get('/upstream-keys/validate-all/status')
}

export async function cleanDisabledKeys(): Promise<any> {
  return http.delete('/upstream-keys/clean-disabled')
}

export async function fetchUpstreamStats(): Promise<UpstreamStat[]> {
  return http.get('/upstream-stats')
}

export async function fetchUserDashboardStats(): Promise<GlobalModelStats> {
  return http.get('/dashboard/me')
}

export async function fetchTimeline(minutes: number = 30): Promise<TimelineEntry[]> {
  return http.get('/dashboard/timeline', { params: { minutes } })
}

export async function fetchUsers(page: number = 1, pageSize: number = 10): Promise<UserListResponse> {
  return http.get('/users', { params: { page, page_size: pageSize } })
}

export async function createUser(username: string, password: string): Promise<void> {
  await http.post('/users', { username, password })
}

export async function resetUserPassword(userId: number, newPassword: string): Promise<void> {
  await http.put(`/users/${userId}/password`, { new_password: newPassword })
}

export async function deleteUser(userId: number): Promise<void> {
  await http.delete(`/users/${userId}`)
}

export async function fetchModels(): Promise<AvailableModel[]> {
  return http.get('/models')
}

export async function createModel(data: { name: string; provider: string; type: string }): Promise<AvailableModel> {
  return http.post('/models', data)
}

export async function updateModel(id: number, data: { name: string; provider: string; type: string; is_active: boolean }): Promise<AvailableModel> {
  return http.put(`/models/${id}`, data)
}

export async function deleteModel(id: number): Promise<void> {
  await http.delete(`/models/${id}`)
}

export async function fetchAnnouncements(): Promise<any[]> {
  return http.get('/announcements')
}

export interface AnnouncementPayload {
  title: string
  content: string
  is_active?: boolean
  is_pinned: boolean
  sort_order: number
}

export async function createAnnouncement(data: AnnouncementPayload): Promise<any> {
  return http.post('/announcements', data)
}

export async function updateAnnouncement(id: number, data: AnnouncementPayload): Promise<any> {
  return http.put(`/announcements/${id}`, data)
}

export async function deleteAnnouncement(id: number): Promise<void> {
  await http.delete(`/announcements/${id}`)
}

export async function fetchSystemConfigs(): Promise<SystemConfigResponse[]> {
  return http.get('/system-config')
}

export async function updateSystemConfig(key: string, value: string): Promise<void> {
  await http.put(`/system-config/${key}`, { key, value })
}

export async function fetchMe(): Promise<MeResponse> {
  return http.get('/me')
}

export async function fetchAdminDashboard(page: number = 1, page_size: number = 10): Promise<AdminDashboardStats> {
  return http.get('/admin/dashboard', { params: { page, page_size } })
}

export async function fetchUpstreamUrlStats(): Promise<UpstreamUrlStat[]> {
  return http.get('/upstream-url-stats')
}
