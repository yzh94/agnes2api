import http from './http'
import type { LoginResponse } from '@/types/api'

export async function login(username: string, password: string): Promise<LoginResponse> {
  const response = await http.post<any, LoginResponse>('/login', { username, password })
  return response
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await http.put('/password', { old_password: oldPassword, new_password: newPassword })
}
