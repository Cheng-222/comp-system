import request from '@/utils/request'

export function getCompetitionDashboard() {
  return request({
    url: '/api/v1/system/dashboard',
    method: 'get'
  })
}
