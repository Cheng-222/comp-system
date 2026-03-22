import request from '@/utils/request'

export function listContests(query) {
  return request({ url: '/api/v1/contests', method: 'get', params: query })
}

export function getContest(id) {
  return request({ url: `/api/v1/contests/${id}`, method: 'get' })
}

export function listContestPermissionUsers() {
  return request({ url: '/api/v1/contests/permission-users', method: 'get' })
}

export function addContest(data) {
  return request({ url: '/api/v1/contests', method: 'post', data })
}

export function updateContest(data) {
  return request({ url: `/api/v1/contests/${data.id}`, method: 'put', data })
}

export function publishContest(id) {
  return request({ url: `/api/v1/contests/${id}/publish`, method: 'post' })
}

export function updateContestStatus(id, data) {
  return request({ url: `/api/v1/contests/${id}/status`, method: 'post', data })
}

export function uploadContestRuleAttachment(id, data) {
  return request({
    url: `/api/v1/contests/${id}/rule-attachment`,
    method: 'post',
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    data,
  })
}

export function removeContestRuleAttachment(id) {
  return request({ url: `/api/v1/contests/${id}/rule-attachment/remove`, method: 'post' })
}
