export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/manage'

export const ENDPOINTS = {
  login: '/login',
  keys: '/keys',
  password: '/password',
  upstreamKeys: '/upstream-keys',
  upstreamStats: '/upstream-stats',
} as const
