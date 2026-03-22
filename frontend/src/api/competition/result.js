import request from '@/utils/request'

export function listResults(query) {
  return request({ url: '/api/v1/results', method: 'get', params: query })
}

export function getResult(id) {
  return request({ url: `/api/v1/results/${id}`, method: 'get' })
}

export function addResult(data) {
  return request({ url: '/api/v1/results', method: 'post', data })
}

export function updateResult(data) {
  return request({ url: `/api/v1/results/${data.id}`, method: 'put', data })
}

export function importResults(data) {
  return request({
    url: '/api/v1/results/import',
    method: 'post',
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    data,
  })
}

export function uploadCertificate(data) {
  return request({
    url: '/api/v1/certificates/upload',
    method: 'post',
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    data,
  })
}
