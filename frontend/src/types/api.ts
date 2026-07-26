// API 响应类型定义

// 客户端 Key
export interface KeyResponse {
  id: number
  name: string
  key: string
  status: 'active' | 'disabled'
  quota: number
  used_quota: number
  user_id: number
}

// 上游 Key
export interface UpstreamKeyResponse {
  id: number
  name: string
  key: string
  weight: number
  status: 'active' | 'disabled'
  disabled_reason: string | null
  disabled_at: string | null
  user_id?: number
  owner_name?: string
}

// 上游渠道统计（含各模型数据）
export interface UpstreamStat {
  name: string
  masked_key: string
  status: string
  total: number
  success: number
  failure: number
  success_rate: number
  text: ModelStat
  image: ModelStat
  video: ModelStat
}

// 单个模型统计
export interface ModelStat {
  total: number
  success: number
  failure: number
  success_rate: number
}

// 登录/注册响应
export interface LoginResponse {
  access_token: string
  token_type: string
  role: string
}

// 全局模型统计（Dashboard）
export interface GlobalModelStats {
  text: ModelStat
  image: ModelStat
  video: ModelStat
  summary: ModelStat
}

// 用户列表项
export interface UserListItem {
  id: number
  username: string
  role: string
  is_active: boolean
  created_at: string | null
  has_upstream_key: boolean
  text_total: number
  text_success: number
  text_failure: number
  image_total: number
  image_success: number
  image_failure: number
  video_total: number
  video_success: number
  video_failure: number
}

// 用户分页列表
export interface UserListResponse {
  items: UserListItem[]
  total: number
  page: number
  page_size: number
}

// 系统配置
export interface SystemConfigResponse {
  key: string
  value: string
}

// 可用模型
export interface AvailableModel {
  id: number
  name: string
  provider: string
  type: string
  is_active: boolean
  created_at: string | null
}

// 当前用户信息
export interface MeResponse {
  id: number
  username: string
  role: string
  created_at: string | null
}

// 管理员看板 - 用户请求排名
export interface AdminUserRanking {
  user_id: number
  username: string
  total_requests: number
  success_rate: number
  text_requests: number
  text_success_rate: number
  image_requests: number
  image_success_rate: number
  video_requests: number
  video_success_rate: number
}

// 管理员看板响应
export interface AdminDashboardStats {
  key_pool: GlobalModelStats
  user_ranking: AdminUserRanking[]
  pagination?: AdminPagination
}

export interface AdminPagination {
  page: number
  page_size: number
  total: number
  total_pages: number
}
