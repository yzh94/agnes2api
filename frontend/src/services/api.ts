import http from './http'
import type { KeyResponse, UpstreamKeyResponse, UpstreamStat, GlobalModelStats, AdminDashboardStats } from '@/types/api'

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

export async function getUpstreamKeys(): Promise<UpstreamKeyResponse[]> {
  return http.get('/upstream-keys')
}

export async function createUpstreamKey(name: string, key: string): Promise<UpstreamKeyResponse> {
  return http.post('/upstream-keys', { name, key })
}

export async function updateUpstreamWeight(id: number, weight: number): Promise<void> {
  await http.put(`/upstream-keys/${id}/weight?weight=${weight}`)
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

export async function cleanDisabledKeys(): Promise<any> {
  return http.delete('/upstream-keys/clean-disabled')
}

export async function fetchUpstreamStats(): Promise<UpstreamStat[]> {
  return http.get('/upstream-stats')
}

export async function fetchDashboardStats(): Promise<GlobalModelStats> {
  return http.get('/dashboard')
}

export async function fetchUserDashboardStats(): Promise<GlobalModelStats> {
  return http.get('/dashboard/me')
}

export async function fetchTimeline(hours: number = 24): Promise<any[]> {
  return http.get('/dashboard/timeline', { params: { hours } })
}

export async function fetchMe(): Promise<{ username: string; role: string }> {
  return http.get('/me')
}

export async function fetchAdminDashboard(page: number = 1, pageSize: number = 10): Promise<AdminDashboardStats> {
  return http.get('/dashboard/admin', { params: { page, page_size: pageSize } })
}
