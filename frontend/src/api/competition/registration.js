import request from '@/utils/request'

export function listRegistrations(query) {
  return request({ url: '/api/v1/registrations', method: 'get', params: query })
}

export function getRegistration(id) {
  return request({ url: `/api/v1/registrations/${id}`, method: 'get' })
}

export function addRegistration(data) {
  return request({ url: '/api/v1/registrations', method: 'post', data })
}

export function updateRegistration(data) {
  return request({ url: `/api/v1/registrations/${data.id}`, method: 'put', data })
}

export function importRegistrations(data) {
  return request({
    url: '/api/v1/registrations/import',
    method: 'post',
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    data,
  })
}

export function submitMaterials(id, data) {
  const isFormData = typeof FormData !== 'undefined' && data instanceof FormData
  return request({
    url: `/api/v1/registrations/${id}/materials`,
    method: 'post',
    headers: isFormData ? { 'Content-Type': 'multipart/form-data', repeatSubmit: false } : undefined,
    data,
  })
}

export function reviewRegistration(id, data) {
  return request({ url: `/api/v1/registrations/${id}/review`, method: 'post', data })
}

export function withdrawRegistration(id, data) {
  return request({ url: `/api/v1/registrations/${id}/withdraw`, method: 'post', data })
}

export function supplementRegistration(id, data) {
  return request({ url: `/api/v1/registrations/${id}/supplement`, method: 'post', data })
}

export function correctionRegistration(id, data) {
  const isFormData = typeof FormData !== 'undefined' && data instanceof FormData
  return request({
    url: `/api/v1/registrations/${id}/correction`,
    method: 'post',
    headers: isFormData ? { 'Content-Type': 'multipart/form-data', repeatSubmit: false } : undefined,
    data,
  })
}

export function replaceRegistration(id, data) {
  return request({ url: `/api/v1/registrations/${id}/replace`, method: 'post', data })
}
