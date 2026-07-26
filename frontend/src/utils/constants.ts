// API 基础地址
export const API_BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL || '/api/manage'

// 后端 API 端点
export const ENDPOINTS = {
  login: '/login',
  keys: '/keys',
  password: '/password',
  upstreamKeys: '/upstream-keys',
  upstreamStats: '/upstream-stats',
} as const