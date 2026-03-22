import request from '@/utils/request'

export function getAwardStatistics(params) {
  return request({ url: '/api/v1/statistics/awards', method: 'get', params })
}

export function createStatisticsExportRecord(data) {
  return request({ url: '/api/v1/statistics/export-records', method: 'post', data })
}

export function listStatisticsExportRecords(params) {
  return request({ url: '/api/v1/statistics/export-records', method: 'get', params })
}

export function retryStatisticsExportRecord(taskId) {
  return request({ url: `/api/v1/statistics/export-records/${taskId}/retry`, method: 'post' })
}
