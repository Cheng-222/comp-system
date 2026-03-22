import request from '@/utils/request'

export function listMessages(query) {
  return request({ url: '/api/v1/messages', method: 'get', params: query })
}

export function addMessage(data) {
  return request({ url: '/api/v1/messages', method: 'post', data })
}

export function updateMessage(data) {
  return request({ url: `/api/v1/messages/${data.id}`, method: 'put', data })
}

export function listTodoRules(query) {
  return request({ url: '/api/v1/messages/todo-rules', method: 'get', params: query })
}

export function addTodoRule(data) {
  return request({ url: '/api/v1/messages/todo-rules', method: 'post', data })
}

export function updateTodoRule(data) {
  return request({ url: `/api/v1/messages/todo-rules/${data.id}`, method: 'put', data })
}

export function applyTodoRule(id) {
  return request({ url: `/api/v1/messages/todo-rules/${id}/apply`, method: 'post' })
}

export function listMessageFailures(query) {
  return request({ url: '/api/v1/messages/failures', method: 'get', params: query })
}

export function sendMessage(id) {
  return request({ url: `/api/v1/messages/${id}/send`, method: 'post' })
}

export function cancelMessage(id) {
  return request({ url: `/api/v1/messages/${id}/cancel`, method: 'post' })
}

export function readMessage(id) {
  return request({ url: `/api/v1/messages/${id}/read`, method: 'post' })
}
