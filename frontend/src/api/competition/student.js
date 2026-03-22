import request from '@/utils/request'

export function listStudents(query) {
  return request({ url: '/api/v1/students', method: 'get', params: query })
}

export function getStudent(id) {
  return request({ url: `/api/v1/students/${id}`, method: 'get' })
}

export function addStudent(data) {
  return request({ url: '/api/v1/students', method: 'post', data })
}

export function updateStudent(data) {
  return request({ url: `/api/v1/students/${data.id}`, method: 'put', data })
}

export function updateStudentStatus(id, data) {
  return request({ url: `/api/v1/students/${id}/status`, method: 'post', data })
}

export function importStudents(data) {
  return request({
    url: '/api/v1/students/import',
    method: 'post',
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    data,
  })
}

export function listStudentImportRecords(query) {
  return request({ url: '/api/v1/students/import-records', method: 'get', params: query })
}
