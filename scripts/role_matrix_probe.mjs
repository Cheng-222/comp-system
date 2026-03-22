import fs from 'node:fs'
import path from 'node:path'

import { chromium } from '../frontend/node_modules/playwright/index.mjs'

const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const apiBaseUrl = process.env.E2E_API_URL || 'http://127.0.0.1:5000'
const outputDir = '/tmp/competition-role-matrix'
fs.mkdirSync(outputDir, { recursive: true })

const stamp = new Date().toISOString().replace(/\D/g, '').slice(0, 14)

const report = {
  startedAt: new Date().toISOString(),
  baseUrl,
  apiBaseUrl,
  outputDir,
  roles: {},
  apiProbes: {},
  findings: [],
}

const roleScenarios = [
  {
    key: 'admin',
    username: 'admin',
    password: 'Admin123!',
    allowedRoutes: [
      { path: '/competition/students', marker: { type: 'text', value: '新增学生' } },
      { path: '/competition/contests', marker: { type: 'text', value: '新增赛事' } },
      { path: '/competition/registrations', marker: { type: 'text', value: '新建报名记录' } },
      { path: '/competition/qualifications', marker: { type: 'text', value: '资格流转列表' } },
      { path: '/competition/reviews', marker: { type: 'text', value: '审核队列' } },
      { path: '/competition/messages', marker: { type: 'text', value: '我的消息' } },
      { path: '/competition/results', marker: { type: 'text', value: '赛后管理' } },
      { path: '/competition/statistics', marker: { type: 'text', value: '统计概览' } },
      { path: '/system/user', marker: { type: 'text', value: '新增账号' } },
      { path: '/system/role', marker: { type: 'text', value: '角色名称' } },
      { path: '/system/menu', marker: { type: 'text', value: '菜单名称' } },
      { path: '/system/dict', marker: { type: 'text', value: '字典名称' } },
      { path: '/system/config', marker: { type: 'text', value: '参数名称' } },
      { path: '/monitor/operlog', marker: { type: 'text', value: '日志编号' } },
      { path: '/monitor/logininfor', marker: { type: 'text', value: '访问编号' } },
      { path: '/monitor/runtime', marker: { type: 'text', value: '存储与备份运行态' } },
    ],
    blockedRoutes: [],
    extraProbes: [probeCustomRoleRuntime],
  },
  {
    key: 'teacher',
    username: 'teacher',
    password: 'Demo123!',
    allowedRoutes: [
      { path: '/competition/contests', marker: { type: 'text', value: '新增赛事' } },
      { path: '/competition/registrations', marker: { type: 'text', value: '新建报名记录' } },
      { path: '/competition/qualifications', marker: { type: 'text', value: '资格流转列表' } },
      { path: '/competition/messages', marker: { type: 'text', value: '我的消息' } },
      { path: '/competition/results', marker: { type: 'text', value: '新增成绩' } },
      { path: '/competition/statistics', marker: { type: 'text', value: '统计概览' } },
    ],
    blockedRoutes: [
      { path: '/competition/students' },
      { path: '/system/user' },
      { path: '/monitor/operlog' },
      { path: '/monitor/runtime' },
    ],
    extraProbes: [probeTeacherWorkflowLinks],
  },
  {
    key: 'reviewer',
    username: 'reviewer',
    password: 'Demo123!',
    allowedRoutes: [
      { path: '/competition/reviews', marker: { type: 'text', value: '审核队列' } },
      { path: '/competition/messages', marker: { type: 'text', value: '我的消息' } },
    ],
    blockedRoutes: [
      { path: '/competition/contests' },
      { path: '/competition/qualifications' },
      { path: '/competition/results' },
      { path: '/system/user' },
      { path: '/monitor/runtime' },
    ],
    extraProbes: [probeReviewerRegistrationGap],
  },
  {
    key: 'student',
    username: '20260001',
    password: 'Demo123!',
    allowedRoutes: [
      { path: '/competition/registrations', marker: { type: 'text', value: '开始报名' } },
      { path: '/competition/messages', marker: { type: 'text', value: '我的消息' } },
      { path: '/competition/results', marker: { type: 'text', value: '我的赛后结果' } },
    ],
    blockedRoutes: [
      { path: '/competition/contests' },
      { path: '/competition/qualifications' },
      { path: '/competition/reviews' },
      { path: '/competition/statistics' },
      { path: '/system/user' },
      { path: '/monitor/runtime' },
    ],
    extraProbes: [],
  },
]

function pageUrl(routePath) {
  return `${baseUrl}${routePath}`
}

function apiUrl(routePath) {
  return `${apiBaseUrl}${routePath}`
}

function flattenLeafRoutes(routes = []) {
  const leaves = []
  for (const route of routes) {
    if (Array.isArray(route.children) && route.children.length) {
      leaves.push(...flattenLeafRoutes(route.children))
      continue
    }
    if (route.component && route.component !== 'Layout') {
      leaves.push(route)
    }
  }
  return leaves
}

async function saveScreenshot(page, name) {
  const target = path.join(outputDir, `${name}.png`)
  await page.screenshot({ path: target, fullPage: true })
  return target
}

async function login(page, username, password) {
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('账号').fill(username)
  await page.getByPlaceholder('密码').fill(password)
  await page.locator('.login-form .el-button').click()
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 15000 })
  await page.locator('#app').waitFor({ timeout: 10000 })
}

async function waitForMarker(page, marker) {
  if (!marker) return
  const locator = marker.type === 'selector'
    ? page.locator(marker.value).first()
    : page.getByText(marker.value, { exact: false }).first()
  await locator.waitFor({ state: 'visible', timeout: 10000 })
}

async function isDeniedPage(page) {
  if (await page.locator('.wscn-http404-container').count()) return true
  if (page.url().includes('/401')) return true
  const deniedTexts = [
    '404错误!',
    '找不到网页！',
    '当前账号无权访问该资源',
  ]
  for (const text of deniedTexts) {
    if (await page.getByText(text, { exact: false }).count()) return true
  }
  return false
}

async function probeAllowedRoute(page, roleKey, route) {
  const result = { path: route.path, expected: 'allow', status: 'passed' }
  try {
    await page.goto(pageUrl(route.path), { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})
    if (await isDeniedPage(page)) {
      result.status = 'failed'
      result.note = '页面被拦截或进入 404'
      result.screenshot = await saveScreenshot(page, `${roleKey}-${route.path.replace(/[^\w]/g, '_')}-denied`)
      return result
    }
    await waitForMarker(page, route.marker)
  } catch (error) {
    result.status = 'failed'
    result.note = String(error?.message || error)
    result.screenshot = await saveScreenshot(page, `${roleKey}-${route.path.replace(/[^\w]/g, '_')}-failed`)
  }
  return result
}

async function probeBlockedRoute(page, roleKey, route) {
  const result = { path: route.path, expected: 'deny', status: 'passed' }
  try {
    await page.goto(pageUrl(route.path), { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})
    if (!(await isDeniedPage(page))) {
      result.status = 'failed'
      result.note = '越权路径可直接打开'
      result.screenshot = await saveScreenshot(page, `${roleKey}-${route.path.replace(/[^\w]/g, '_')}-unexpected`)
    }
  } catch (error) {
    result.status = 'failed'
    result.note = String(error?.message || error)
    result.screenshot = await saveScreenshot(page, `${roleKey}-${route.path.replace(/[^\w]/g, '_')}-error`)
  }
  return result
}

async function getContextToken(context) {
  const cookies = await context.cookies()
  return cookies.find((cookie) => cookie.name === 'Admin-Token')?.value || ''
}

async function apiRequest(routePath, { method = 'GET', token = '', body, headers = {} } = {}) {
  const response = await fetch(apiUrl(routePath), {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()
  return { status: response.status, payload }
}

function addFinding(finding) {
  report.findings.push({
    detectedAt: new Date().toISOString(),
    ...finding,
  })
}

async function probeTeacherWorkflowLinks({ page, roleKey }) {
  const result = { key: 'teacher_workflow_links', status: 'passed' }
  try {
    await page.goto(pageUrl('/competition/registrations'), { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})

    await page.getByRole('button', { name: '去资格管理' }).first().click()
    await waitForMarker(page, { type: 'text', value: '资格流转列表' })
    result.qualificationLink = 'passed'

    await page.goto(pageUrl('/competition/registrations'), { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})
    const reviewLinkCount = await page.getByRole('button', { name: '去材料审核' }).count()
    result.reviewLink = reviewLinkCount === 0 ? 'hidden' : 'visible'
    if (reviewLinkCount > 0) {
      result.status = 'failed'
      result.screenshot = await saveScreenshot(page, `${roleKey}-teacher-review-link-visible`)
      addFinding({
        key: 'teacher_review_link_broken',
        severity: 'high',
        title: '教师端“去材料审核”内链断裂',
        detail: '教师不具备审核路由，但报名管理页仍然展示“去材料审核”按钮，页面引导与真实权限矩阵不一致。',
        evidence: result.screenshot,
      })
    }
  } catch (error) {
    result.status = 'failed'
    result.note = String(error?.message || error)
    result.screenshot = await saveScreenshot(page, `${roleKey}-teacher-link-probe-error`)
  }
  return result
}

async function probeReviewerRegistrationGap({ context, page }) {
  const token = await getContextToken(context)
  const result = { key: 'reviewer_registration_gap', status: 'passed' }
  const apiRes = await apiRequest('/api/v1/registrations?pageNum=1&pageSize=2', { token })
  result.apiStatus = apiRes.status
  result.apiCode = apiRes.payload?.code
  result.apiTotal = apiRes.payload?.data?.total ?? null

  await page.goto(pageUrl('/competition/registrations'), { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})
  result.routeDenied = await isDeniedPage(page)

  if (apiRes.status === 200 && apiRes.payload?.code === 200 && result.routeDenied) {
    result.status = 'failed'
    result.screenshot = await saveScreenshot(page, 'reviewer-registration-route-denied')
    addFinding({
      key: 'reviewer_registration_route_missing',
      severity: 'high',
      title: '审核员报名台账前后端断裂',
      detail: '审核员可以通过后端接口读取报名列表，但前端 /competition/registrations 路由不存在，导致报名台账无法从页面进入。',
      evidence: result.screenshot,
    })
  }
  return result
}

async function probeCustomRoleRuntime({ context }) {
  const token = await getContextToken(context)
  const roleKey = `observer_${stamp}`
  const username = `observer_${stamp}`
  const password = 'Observe123!'

  const createRoleRes = await apiRequest('/system/role', {
    method: 'POST',
    token,
    body: {
      roleName: `观测员-${stamp.slice(-4)}`,
      roleKey,
      roleSort: 91,
      status: '0',
      dataScope: '2',
      deptIds: [12],
      menuIds: [1, 103, 106],
      remark: '运行时 RBAC 探针',
    },
  })

  const roleListRes = await apiRequest(`/system/role/list?roleKey=${roleKey}`, { token })
  const roleRow = roleListRes.payload?.rows?.[0]
  const roleId = roleRow?.roleId

  const createUserRes = roleId
    ? await apiRequest('/system/user', {
        method: 'POST',
        token,
        body: {
          userName: username,
          nickName: `观测账号-${stamp.slice(-4)}`,
          password,
          status: '0',
          roleIds: [roleId],
        },
      })
    : { status: 500, payload: { code: 500, msg: '角色创建失败，未取得 roleId' } }

  const loginRes = await apiRequest('/login', {
    method: 'POST',
    body: { username, password },
  })
  const customToken = loginRes.payload?.token || ''
  const infoRes = customToken ? await apiRequest('/getInfo', { token: customToken }) : { status: 500, payload: {} }
  const routersRes = customToken ? await apiRequest('/getRouters', { token: customToken }) : { status: 500, payload: {} }
  const roleDetailRes = roleId ? await apiRequest(`/system/role/${roleId}`, { token }) : { status: 500, payload: {} }

  const menuIds = roleDetailRes.payload?.data?.menuIds || []
  const routeLeaves = flattenLeafRoutes(routersRes.payload?.data || [])
  const permissions = infoRes.payload?.permissions || []

  const result = {
    key: 'custom_role_runtime',
    roleKey,
    username,
    createRoleStatus: createRoleRes.status,
    createRoleCode: createRoleRes.payload?.code,
    createUserStatus: createUserRes.status,
    createUserCode: createUserRes.payload?.code,
    loginStatus: loginRes.status,
    loginCode: loginRes.payload?.code,
    menuIds,
    runtimePermissions: permissions,
    runtimeRouteCount: routeLeaves.length,
    runtimeRoutes: routeLeaves.map((item) => item.path),
    status: 'passed',
  }

  report.apiProbes.customRoleRuntime = result

  if (menuIds.length > 0 && routeLeaves.length === 0) {
    result.status = 'failed'
    addFinding({
      key: 'custom_role_runtime_ignored',
      severity: 'high',
      title: '自定义角色菜单配置未驱动运行时授权',
      detail: '后台已成功保存自定义角色及 menuIds，但该角色登录后 getRouters 仍为空、permissions 也没有对应能力，说明角色/菜单配置没有真正接到运行时授权。',
      evidence: JSON.stringify({ menuIds, runtimePermissions: permissions, runtimeRoutes: result.runtimeRoutes }),
    })
  }

  return result
}

async function runRoleScenario(browser, scenario) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } })
  const page = await context.newPage()
  const roleReport = {
    username: scenario.username,
    startedAt: new Date().toISOString(),
    allowedRoutes: [],
    blockedRoutes: [],
    extras: [],
    status: 'passed',
  }

  try {
    await login(page, scenario.username, scenario.password)

    for (const route of scenario.allowedRoutes) {
      const current = await probeAllowedRoute(page, scenario.key, route)
      roleReport.allowedRoutes.push(current)
      if (current.status !== 'passed') {
        roleReport.status = 'failed'
      }
    }

    for (const route of scenario.blockedRoutes) {
      const current = await probeBlockedRoute(page, scenario.key, route)
      roleReport.blockedRoutes.push(current)
      if (current.status !== 'passed') {
        roleReport.status = 'failed'
        addFinding({
          key: `${scenario.key}_unexpected_access_${route.path}`,
          severity: 'high',
          title: `${scenario.key} 越权访问未被拦截`,
          detail: `${scenario.key} 可以直接打开 ${route.path}，实际越权保护没有生效。`,
          evidence: current.screenshot || route.path,
        })
      }
    }

    for (const probe of scenario.extraProbes) {
      const current = await probe({ context, page, roleKey: scenario.key })
      roleReport.extras.push(current)
      if (current.status !== 'passed') {
        roleReport.status = 'failed'
      }
    }
  } catch (error) {
    roleReport.status = 'failed'
    roleReport.error = String(error?.message || error)
    roleReport.screenshot = await saveScreenshot(page, `${scenario.key}-fatal`)
  } finally {
    roleReport.finishedAt = new Date().toISOString()
    report.roles[scenario.key] = roleReport
    await context.close()
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  try {
    await Promise.all(roleScenarios.map((scenario) => runRoleScenario(browser, scenario)))
  } finally {
    await browser.close()
  }

  report.finishedAt = new Date().toISOString()
  const failedRoleCount = Object.values(report.roles).filter((item) => item.status !== 'passed').length
  report.summary = {
    roleCount: roleScenarios.length,
    failedRoleCount,
    findingCount: report.findings.length,
  }

  const reportPath = path.join(outputDir, 'role-matrix-report.json')
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`)

  console.log(`ROLE_MATRIX_REPORT ${reportPath}`)
  console.log(`ROLE_MATRIX_FINDINGS ${report.findings.length}`)
  for (const finding of report.findings) {
    console.log(`FINDING ${finding.key}: ${finding.title}`)
  }

  if (failedRoleCount || report.findings.length) {
    process.exitCode = 1
  }
}

await main()
