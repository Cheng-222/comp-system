import request from '@/utils/request'

export function getFileCategories() {
  return request({ url: '/api/v1/files/categories', method: 'get' })
}

export function listFiles(params) {
  return request({ url: '/api/v1/files', method: 'get', params })
}

export function getFileExportMetadata() {
  return request({ url: '/api/v1/files/export-metadata', method: 'get' })
}

export function listFileExportPolicies(params) {
  return request({ url: '/api/v1/files/export-policies', method: 'get', params })
}

export function getFileExportPolicy(policyId) {
  return request({ url: `/api/v1/files/export-policies/${policyId}`, method: 'get' })
}

export function addFileExportPolicy(data) {
  return request({ url: '/api/v1/files/export-policies', method: 'post', data })
}

export function updateFileExportPolicy(policyId, data) {
  return request({ url: `/api/v1/files/export-policies/${policyId}`, method: 'put', data })
}

export function deleteFileExportPolicy(policyId) {
  return request({ url: `/api/v1/files/export-policies/${policyId}`, method: 'delete' })
}

export function runFileExportPolicy(policyId) {
  return request({ url: `/api/v1/files/export-policies/${policyId}/run`, method: 'post' })
}

export function runDueFileExportPolicies() {
  return request({ url: '/api/v1/files/export-policies/run-due', method: 'post' })
}

export function listFileExportBatches(params) {
  return request({ url: '/api/v1/files/export-batches', method: 'get', params })
}

export function getFileExportBatch(batchId) {
  return request({ url: `/api/v1/files/export-batches/${batchId}`, method: 'get' })
}

export function retryFileExportBatch(batchId) {
  return request({ url: `/api/v1/files/export-batches/${batchId}/retry`, method: 'post' })
}

export function listDeliveryChannels(params) {
  return request({ url: '/api/v1/files/delivery-channels', method: 'get', params })
}

export function getDeliveryChannel(channelId) {
  return request({ url: `/api/v1/files/delivery-channels/${channelId}`, method: 'get' })
}

export function addDeliveryChannel(data) {
  return request({ url: '/api/v1/files/delivery-channels', method: 'post', data })
}

export function updateDeliveryChannel(channelId, data) {
  return request({ url: `/api/v1/files/delivery-channels/${channelId}`, method: 'put', data })
}

export function deleteDeliveryChannel(channelId) {
  return request({ url: `/api/v1/files/delivery-channels/${channelId}`, method: 'delete' })
}

export function validateDeliveryChannel(channelId) {
  return request({ url: `/api/v1/files/delivery-channels/${channelId}/validate`, method: 'post' })
}

export function beginDeliveryChannelOauth(channelId) {
  return request({ url: `/api/v1/files/delivery-channels/${channelId}/oauth-authorize`, method: 'post' })
}
