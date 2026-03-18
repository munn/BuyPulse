import api from './client'
import type {
  AuditLogItem,
  CrawlStats,
  CrawlTaskItem,
  FetchRunItem,
  ImportJobItem,
  OverviewStats,
  PaginatedResponse,
  PricePoint,
  ProductDetail,
  ProductItem,
  RecentFailure,
  ThroughputBucket,
  User,
  WorkerStatus,
} from '../types'

export const login = (username: string, password: string) =>
  api.post<User>('/auth/login', { username, password })

export const logout = () => api.post('/auth/logout')

export const getMe = () => api.get<User>('/auth/me')

export const getOverview = () => api.get<OverviewStats>('/dashboard/overview')

export const getThroughput = (hours = 24) =>
  api.get<ThroughputBucket[]>('/dashboard/throughput', { params: { hours } })

export const getWorkers = () => api.get<WorkerStatus[]>('/dashboard/workers')

export const getRecentFailures = () =>
  api.get<RecentFailure[]>('/dashboard/recent-failures')

export const getProducts = (params: Record<string, unknown>) =>
  api.get<PaginatedResponse<ProductItem>>('/products', { params })

export const getProduct = (id: number) =>
  api.get<ProductDetail>(`/products/${id}`)

export const getPriceHistory = (id: number) =>
  api.get<PricePoint[]>(`/products/${id}/price-history`)

export const getFetchRuns = (id: number) =>
  api.get<FetchRunItem[]>(`/products/${id}/fetch-runs`)

export const addProduct = (platformId: string) =>
  api.post('/products', { platform_id: platformId })

export const importProducts = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/products/import', form)
}

export const getCrawlerTasks = (params: Record<string, unknown>) =>
  api.get<PaginatedResponse<CrawlTaskItem>>('/crawler/tasks', { params })

export const getCrawlerStats = () => api.get<CrawlStats>('/crawler/stats')

export const retryTask = (id: number) =>
  api.post(`/crawler/tasks/${id}/retry`)

export const enqueueAsins = (platformIds: string[], platform = 'amazon') =>
  api.post('/crawler/enqueue', { platform_ids: platformIds, platform })

export const retryAllFailed = () => api.post('/crawler/retry-all-failed')

export const getImports = () => api.get<ImportJobItem[]>('/imports')

export const getImport = (id: number) =>
  api.get<ImportJobItem>(`/imports/${id}`)

export const getAuditLog = (params: Record<string, unknown>) =>
  api.get<PaginatedResponse<AuditLogItem>>('/audit', { params })
