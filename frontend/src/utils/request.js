import axios from 'axios'
import { ElNotification , ElMessageBox, ElMessage, ElLoading } from 'element-plus'
import { getToken } from '@/utils/auth'
import errorCode from '@/utils/errorCode'
import { tansParams, blobValidate } from '@/utils/ruoyi'
import cache from '@/plugins/cache'
import { saveAs } from 'file-saver'
import useUserStore from '@/store/modules/user'

let downloadLoadingInstance
// 是否显示重新登录
export let isRelogin = { show: false }

axios.defaults.headers['Content-Type'] = 'application/json;charset=utf-8'
// 创建axios实例
const service = axios.create({
  // axios中请求配置有baseURL选项，表示请求URL公共部分
  baseURL: import.meta.env.VITE_APP_BASE_API,
  // 超时
  timeout: 30000
})

// request拦截器
service.interceptors.request.use(config => {
  // 是否需要设置 token
  const isToken = (config.headers || {}).isToken === false
  // 是否需要防止数据重复提交
  const isRepeatSubmit = (config.headers || {}).repeatSubmit === false
  // 间隔时间(ms)，小于此时间视为重复提交
  const interval = (config.headers || {}).interval || 1000
  if (getToken() && !isToken) {
    config.headers['Authorization'] = 'Bearer ' + getToken() // 让每个请求携带自定义token 请根据实际情况自行修改
  }
  // get请求映射params参数
  if (config.method === 'get' && config.params) {
    let url = config.url + '?' + tansParams(config.params)
    url = url.slice(0, -1)
    config.params = {}
    config.url = url
  }
  if (!isRepeatSubmit && (config.method === 'post' || config.method === 'put')) {
    const requestObj = {
      url: config.url,
      data: typeof config.data === 'object' ? JSON.stringify(config.data) : config.data,
      time: new Date().getTime()
    }
    const requestSize = Object.keys(JSON.stringify(requestObj)).length // 请求数据大小
    const limitSize = 5 * 1024 * 1024 // 限制存放数据5M
    if (requestSize >= limitSize) {
      console.warn(`[${config.url}]: ` + '请求数据大小超出允许的5M限制，无法进行防重复提交验证。')
      return config
    }
    const sessionObj = cache.session.getJSON('sessionObj')
    if (sessionObj === undefined || sessionObj === null || sessionObj === '') {
      cache.session.setJSON('sessionObj', requestObj)
    } else {
      const s_url = sessionObj.url                // 请求地址
      const s_data = sessionObj.data              // 请求数据
      const s_time = sessionObj.time              // 请求时间
      if (s_data === requestObj.data && requestObj.time - s_time < interval && s_url === requestObj.url) {
        const message = '数据正在处理，请勿重复提交'
        console.warn(`[${s_url}]: ` + message)
        return Promise.reject(new Error(message))
      } else {
        cache.session.setJSON('sessionObj', requestObj)
      }
    }
  }
  return config
}, error => {
    console.log(error)
    Promise.reject(error)
})

// 响应拦截器
service.interceptors.response.use(res => {
    // 未设置状态码则默认成功状态
    const code = res.data.code || 200
    // 获取错误信息
    const msg = errorCode[code] || res.data.msg || errorCode['default']
    // 二进制数据则直接返回
    if (res.request.responseType ===  'blob' || res.request.responseType ===  'arraybuffer') {
      return res
    }
    if (code === 401) {
      if (!isRelogin.show) {
        isRelogin.show = true
        ElMessageBox.confirm('登录状态已过期，您可以继续留在该页面，或者重新登录', '系统提示', { confirmButtonText: '重新登录', cancelButtonText: '取消', type: 'warning' }).then(() => {
          isRelogin.show = false
          useUserStore().logOut().then(() => {
            location.href = '/index'
          })
      }).catch(() => {
        isRelogin.show = false
      })
    }
      return Promise.reject('无效的会话，或者会话已过期，请重新登录。')
    } else if (code === 500) {
      ElMessage({ message: msg, type: 'error' })
      return Promise.reject(new Error(msg))
    } else if (code === 601) {
      ElMessage({ message: msg, type: 'warning' })
      return Promise.reject(new Error(msg))
    } else if (code !== 200) {
      ElNotification.error({ title: msg })
      return Promise.reject('error')
    } else {
      return  Promise.resolve(res.data)
    }
  },
  error => {
    console.log('err' + error)
    const responseData = error?.response?.data || {}
    let message = responseData.msg || responseData.message || error.message || '系统接口异常'
    if (message == "Network Error") {
      message = "后端接口连接异常"
    } else if (message.includes("timeout")) {
      message = "系统接口请求超时"
    } else if (message.includes("Request failed with status code")) {
      const status = error?.response?.status
      message = status ? `系统接口${status}异常` : message
    }
    ElMessage({ message: message, type: 'error', duration: 5 * 1000 })
    return Promise.reject(error)
  }
)

function parseContentDispositionFilename(headerValue) {
  if (!headerValue) return ''
  const utf8Match = headerValue.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }
  const normalMatch = headerValue.match(/filename="?([^";]+)"?/i)
  return normalMatch?.[1] ? decodeURIComponent(normalMatch[1]) : ''
}

function normalizeBinaryResponse(response) {
  const data = response?.data ?? response
  const headers = response?.headers || {}
  return {
    data,
    headers,
    filename: parseContentDispositionFilename(headers['content-disposition']),
  }
}

function createBinaryBlob(data, headers = {}) {
  if (data instanceof Blob) {
    return data.type ? data : data.slice(0, data.size, headers['content-type'] || 'application/octet-stream')
  }
  return new Blob([data], { type: headers['content-type'] || 'application/octet-stream' })
}

async function printBlobError(data) {
  const resText = await data.text()
  const rspObj = JSON.parse(resText)
  const errMsg = errorCode[rspObj.code] || rspObj.msg || errorCode['default']
  ElMessage.error(errMsg)
}

function requestBinary(url, params, config) {
  return service.post(url, params, {
    transformRequest: [(payload) => tansParams(payload)],
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    responseType: 'blob',
    ...config
  })
}

export async function fetchBinary(url, params, config) {
  const response = await requestBinary(url, params, config)
  const { data, headers, filename } = normalizeBinaryResponse(response)
  const isBlob = blobValidate(data)
  if (!isBlob) {
    await printBlobError(data)
    throw new Error('binary-response-error')
  }
  const blob = createBinaryBlob(data, headers)
  return {
    blob,
    headers,
    filename,
    contentType: blob.type || headers['content-type'] || 'application/octet-stream',
  }
}

// 通用下载方法
export function download(url, params, filename, config) {
  downloadLoadingInstance = ElLoading.service({ text: "正在下载数据，请稍候", background: "rgba(0, 0, 0, 0.7)", })
  return fetchBinary(url, params, config).then(async ({ blob, filename: headerFilename }) => {
    saveAs(blob, filename || headerFilename || '下载文件')
    downloadLoadingInstance.close()
  }).catch((r) => {
    console.error(r)
    ElMessage.error('下载文件出现错误，请联系管理员！')
    downloadLoadingInstance.close()
  })
}

export function previewFile(url, params, filename, config) {
  const previewWindow = window.open('', '_blank')
  if (previewWindow) {
    previewWindow.document.title = filename || '文件预览'
    previewWindow.document.body.innerHTML = '<p style="font-family: sans-serif; padding: 24px;">文件加载中...</p>'
  }
  return fetchBinary(url, params, config).then(async ({ blob }) => {
    const objectUrl = window.URL.createObjectURL(blob)
    if (previewWindow) {
      previewWindow.location.href = objectUrl
    } else {
      const fallbackWindow = window.open(objectUrl, '_blank', 'noopener,noreferrer')
      if (!fallbackWindow) {
        saveAs(blob, filename || '下载文件')
      }
    }
    window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60 * 1000)
  }).catch((error) => {
    previewWindow?.close()
    console.error(error)
    ElMessage.error('打开文件出现错误，请联系管理员！')
  })
}

export default service
