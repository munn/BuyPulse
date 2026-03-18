export interface User {
  id: number
  username: string
  role: string
  is_active: boolean
  created_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface OverviewStats {
  products_total: number
  products_today: number
  crawled_total: number
  crawled_today: number
  success_rate_24h: number
  price_records_total: number
}

export interface WorkerStatus {
  worker_id: string
  platform: string
  status: 'online' | 'idle' | 'offline'
  current_task_id: number | null
  tasks_completed: number
  last_heartbeat: string
  started_at: string
}

export interface ThroughputBucket {
  hour: string
  count: number
}

export interface RecentFailure {
  task_id: number
  platform_id: string
  platform: string
  error_message: string | null
  updated_at: string
}

export interface ProductItem {
  id: number
  platform_id: string
  platform: string
  title: string | null
  category: string | null
  is_active: boolean
  first_seen: string
  updated_at: string
  current_price: number | null
}

export interface ProductDetail extends ProductItem {
  url: string | null
  lowest_price: number | null
  highest_price: number | null
}

export interface PricePoint {
  recorded_date: string
  price_cents: number
  price_type: string
}

export interface FetchRunItem {
  id: number
  status: string
  points_extracted: number | null
  ocr_confidence: number | null
  validation_passed: boolean | null
  error_message: string | null
  created_at: string
}

export interface CrawlTaskItem {
  id: number
  product_id: number
  platform_id: string
  platform: string
  status: string
  priority: number
  retry_count: number
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  updated_at: string
}

export interface CrawlStats {
  pending: number
  running: number
  completed: number
  failed: number
  speed_per_hour: number
}

export interface ImportJobItem {
  id: number
  filename: string
  status: string
  total: number
  processed: number
  added: number
  skipped: number
  error_message: string | null
  created_by: number
  created_at: string
  completed_at: string | null
}

export interface AuditLogItem {
  id: number
  user_id: number
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown> | null
  ip_address: string
  created_at: string
}
