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
  status: 'active' | 'disabled'
  disabled_reason: string | null
  disabled_at: string | null
  // Key 池最后使用时间（ISO 8601 UTC），从未使用或池缺失时为 null
  last_used_at: string | null
  user_id?: number
  owner_name?: string
}

// 上游 Key 全量状态汇总（跨分页）
export interface UpstreamKeySummary {
  total: number
  active: number
  disabled: number
}

// 上游 Key 分页列表
export interface UpstreamKeyListResponse {
  items: UpstreamKeyResponse[]
  total: number
  page: number
  page_size: number
  summary: UpstreamKeySummary
  // 上次定时失败 Key 检验时间（北京时间字符串），无记录时为 null
  last_validation_at: string | null
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
  discord_id?: string | null
  discord_username?: string | null
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
  request_level?: GlobalModelStats  // 请求级成功率（用户视角：重试后成功即成功）
  failure_reasons?: Record<string, number>  // Key 池失败原因分类计数
  user_ranking: AdminUserRanking[]
  pagination?: AdminPagination
}

// 上游 Base URL 健康度统计（最近 100 次滑动窗口）
export interface UpstreamUrlStat {
  url: string
  total: number
  success: number
  failure: number
  success_rate: number
  is_best: boolean
}

export interface AdminPagination {
  page: number
  page_size: number
  total: number
  total_pages: number
}

// 时间序列单条记录
export interface TimelineEntry {
  timestamp: string
  text?: { success_rate: number | null }
  image?: { success_rate: number | null }
  video?: { success_rate: number | null }
}

// 公告项
export interface AnnouncementItem {
  id: number
  title: string
  content: string
  is_active: boolean
  is_pinned: boolean
  sort_order: number
  created_at: string | null
  updated_at: string | null
}
