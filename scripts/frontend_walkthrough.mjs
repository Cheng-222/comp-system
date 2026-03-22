import fs from 'node:fs'
import path from 'node:path'

import { chromium } from '../frontend/node_modules/playwright/index.mjs'
import * as XLSX from '../frontend/node_modules/xlsx/xlsx.mjs'

const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const outputDir = '/tmp/competition-walkthrough'
fs.mkdirSync(outputDir, { recursive: true })

const stamp = new Date().toISOString().replace(/\D/g, '').slice(0, 14)
const studentNo = `2099${stamp.slice(-6)}`
const studentName = `走查学生${stamp.slice(-4)}`
const contestName = `前端走查竞赛-${stamp.slice(-6)}`
const projectName = `前端走查项目-${stamp.slice(-4)}`
const reviewMessageTitle = `审核通过：${contestName} / ${studentName}`
const samplePdf = path.join(outputDir, 'sample.pdf')
const rulePreviewXlsx = path.join(outputDir, 'rule-preview.xlsx')

const report = []

function ensureFixtures() {
  if (!fs.existsSync(samplePdf)) {
    fs.writeFileSync(
      samplePdf,
      `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 47 >>
stream
BT
/F1 18 Tf
72 88 Td
(Competition Walkthrough) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000063 00000 n 
0000000122 00000 n 
0000000248 00000 n 
0000000346 00000 n 
trailer
<< /Root 1 0 R /Size 6 >>
startxref
416
%%EOF`,
    )
  }

  if (!fs.existsSync(rulePreviewXlsx)) {
    const workbook = XLSX.utils.book_new()
    const worksheet = XLSX.utils.aoa_to_sheet([
      ['规则清单', '说明'],
      ['报名材料', '请提交方案书和证明材料'],
      ['资格要求', '需为在校本科生'],
    ])
    XLSX.utils.book_append_sheet(workbook, worksheet, '规则清单')
    fs.writeFileSync(rulePreviewXlsx, XLSX.write(workbook, { bookType: 'xlsx', type: 'buffer' }))
  }
}

ensureFixtures()

function logStep(step, status, note) {
  const entry = { step, status, note, at: new Date().toISOString() }
  report.push(entry)
  console.log(`${status.toUpperCase()} ${step}: ${note}`)
}

function pageUrl(urlPath) {
  return `${baseUrl}${urlPath}`
}

async function saveScreenshot(page, name) {
  const target = path.join(outputDir, `${name}.png`)
  await page.screenshot({ path: target, fullPage: true })
  return target
}

async function waitForMessage(page, expectedText) {
  const locator = expectedText
    ? page.locator(`.el-message:has-text("${expectedText}")`).last()
    : page.locator('.el-message').last()
  await locator.waitFor({ state: 'visible', timeout: 10000 })
  const text = (await locator.textContent())?.trim() || ''
  if (expectedText && !text.includes(expectedText)) {
    throw new Error(`提示文案不匹配，期望包含“${expectedText}”，实际为“${text}”`)
  }
  return text
}

function dialog(page) {
  return page.locator('.el-dialog:visible').last()
}

function drawer(page) {
  return page.locator('.el-drawer:visible').last()
}

function rowByText(page, text) {
  return page.locator('.el-table__row').filter({ hasText: text }).first()
}

async function waitForLocatorText(locator, rowText, expectedText, timeout = 15000) {
  await locator.waitFor({ state: 'visible', timeout })
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const text = (await locator.textContent()) || ''
    if (text.includes(expectedText)) {
      return locator
    }
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
  throw new Error(`未在 ${timeout}ms 内等到“${rowText}”行出现“${expectedText}”`)
}

async function clickButton(container, text) {
  await container.locator(`button:has-text("${text}")`).first().click()
}

async function fillFormInput(container, label, value) {
  const item = container.locator(`.el-form-item:has(label:has-text("${label}"))`).first()
  const input = item.locator('input:not([type="hidden"]), textarea').first()
  await input.waitFor({ state: 'visible', timeout: 10000 })
  await input.fill('')
  await input.type(String(value))
}

async function selectFormOption(page, container, label, optionText) {
  const item = container.locator(`.el-form-item:has(label:has-text("${label}"))`).first()
  await item.locator('.el-select').first().click()
  const option = page.locator('.el-select-dropdown__item').filter({ hasText: optionText }).last()
  await option.waitFor({ state: 'visible', timeout: 10000 })
  await option.click()
  await page.keyboard.press('Escape').catch(() => {})
}

async function pickDateTime(container, label, value) {
  const item = container.locator(`.el-form-item:has(label:has-text("${label}"))`).first()
  const input = item.locator('input:not([type="hidden"])').first()
  await input.waitFor({ state: 'visible', timeout: 10000 })
  await input.fill('')
  await input.type(value)
  await input.press('Enter')
}

async function uploadInForm(container, label, filePath) {
  const item = container.locator(`.el-form-item:has(label:has-text("${label}"))`).first()
  const input = await item.locator('input[type="file"]').count()
    ? item.locator('input[type="file"]').first()
    : container.locator('input[type="file"]').last()
  await input.setInputFiles(filePath)
}

async function confirmBox(page) {
  const box = page.locator('.el-message-box:visible').last()
  await box.waitFor({ state: 'visible', timeout: 10000 })
  await clickButton(box, '确定')
}

async function closeDrawer(page) {
  const current = drawer(page)
  await current.locator('.el-drawer__header button').click()
  await current.waitFor({ state: 'hidden', timeout: 10000 })
}

async function closeDialog(page, text = '关闭') {
  const current = dialog(page)
  await clickButton(current, text)
  await current.waitFor({ state: 'hidden', timeout: 10000 })
}

async function waitForPreviewDialog(page, fileName) {
  const current = dialog(page)
  await current.locator('.el-dialog__title').filter({ hasText: fileName }).first().waitFor({ timeout: 15000 })
  return current
}

async function login(page, username, password) {
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('账号').fill(username)
  await page.getByPlaceholder('密码').fill(password)
  await page.locator('.login-form .el-button').click()
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 15000 })
  await page.locator('#app').waitFor({ timeout: 10000 })
}

async function gotoModule(page, urlPath, titleText) {
  await page.goto(pageUrl(urlPath), { waitUntil: 'domcontentloaded' })
  await page.locator(`text=${titleText}`).first().waitFor({ timeout: 15000 })
}

async function createStudent(page) {
  await gotoModule(page, '/competition/students', '学生管理')
  await saveScreenshot(page, '01-students')
  await clickButton(page, '新增学生')
  const currentDialog = dialog(page)
  await fillFormInput(currentDialog, '学号', studentNo)
  await fillFormInput(currentDialog, '姓名', studentName)
  await selectFormOption(page, currentDialog, '性别', '女')
  await fillFormInput(currentDialog, '学院', '计算机学院')
  await fillFormInput(currentDialog, '专业', '软件工程')
  await fillFormInput(currentDialog, '班级', '软件工程 2601')
  await fillFormInput(currentDialog, '导师', '走查导师')
  await fillFormInput(currentDialog, '手机', '13800008888')
  await fillFormInput(currentDialog, '邮箱', `walkthrough_${stamp}@example.com`)
  await fillFormInput(currentDialog, '历史经历', '前端走查创建的学生档案')
  await fillFormInput(currentDialog, '备注', '用于前端全流程走查')
  await clickButton(currentDialog, '确定')
  await waitForMessage(page, '学生新增成功')
  await fillFormInput(page, '关键字', studentNo)
  await clickButton(page, '搜索')
  await rowByText(page, studentNo).waitFor({ timeout: 10000 })
  await saveScreenshot(page, '02-student-created')
  logStep('学生管理', 'passed', `已通过前端新增学生 ${studentNo}`)
}

async function createContest(page) {
  await gotoModule(page, '/competition/contests', '赛事管理')
  await clickButton(page, '新增赛事')
  const currentDialog = dialog(page)
  await fillFormInput(currentDialog, '赛事名称', contestName)
  await fillFormInput(currentDialog, '赛事级别', '校级')
  await fillFormInput(currentDialog, '赛事分类', '前端工程')
  await fillFormInput(currentDialog, '赛事年度', '2026')
  await fillFormInput(currentDialog, '主办单位', '前端走查实验室')
  await fillFormInput(currentDialog, '承办单位', '产品体验组')
  await fillFormInput(currentDialog, '面向对象', '本科生')
  await fillFormInput(currentDialog, '比赛地点', '创新中心 A201')
  await fillFormInput(currentDialog, '联系人', '测试老师')
  await fillFormInput(currentDialog, '联系电话', '13800009999')
  await pickDateTime(currentDialog, '报名开始', '2026-03-12 09:00:00')
  await pickDateTime(currentDialog, '报名结束', '2026-03-20 18:00:00')
  await pickDateTime(currentDialog, '比赛时间', '2026-03-25 14:00:00')
  await fillFormInput(currentDialog, '材料要求', '请提交方案书和证明材料。')
  await fillFormInput(currentDialog, '赛事简介', '用于验证前端全流程走查。')
  await selectFormOption(page, currentDialog, '负责教师', '竞赛教师')
  await selectFormOption(page, currentDialog, '审核人', '资格审核员')
  await uploadInForm(currentDialog, '规则附件', rulePreviewXlsx)
  await clickButton(currentDialog, '确定')
  await waitForMessage(page, '赛事新增成功')

  await fillFormInput(page, '关键字', contestName)
  await clickButton(page, '搜索')
  const currentRow = rowByText(page, contestName)
  await currentRow.waitFor({ timeout: 10000 })
  await currentRow.locator('button:has-text("发布")').click()
  await confirmBox(page)
  await waitForMessage(page, '赛事发布成功')
  await currentRow.locator('button:has-text("详情")').click()
  const currentDrawer = drawer(page)
  await currentDrawer.locator('button:has-text("查看附件")').click()
  await waitForPreviewDialog(page, 'rule-preview.xlsx')
  await dialog(page).locator('td').filter({ hasText: '规则清单' }).first().waitFor({ timeout: 15000 })
  await saveScreenshot(page, '03-contest-rule-preview')
  await closeDialog(page)
  await closeDrawer(page)
  logStep('赛事管理', 'passed', `已创建并发布赛事 ${contestName}，规则附件 xlsx 预览正常`)
}

async function createRegistration(page) {
  await gotoModule(page, '/competition/registrations', '报名管理')
  await fillFormInput(page, '关键字', '')
  await clickButton(page, '新建报名记录')
  const currentDialog = dialog(page)
  await selectFormOption(page, currentDialog, '赛事', contestName)
  await selectFormOption(page, currentDialog, '学生', `${studentName}（${studentNo}）`)
  await fillFormInput(currentDialog, '项目名称', projectName)
  await fillFormInput(currentDialog, '报名方向', '体验优化')
  await fillFormInput(currentDialog, '队伍名称', '前端走查队')
  await fillFormInput(currentDialog, '指导老师', '测试老师')
  await fillFormInput(currentDialog, '导师电话', '13800007777')
  await fillFormInput(currentDialog, '紧急联系人', '紧急联系人')
  await fillFormInput(currentDialog, '紧急电话', '13800006666')
  await fillFormInput(currentDialog, '备注', '前端走查报名记录')
  await clickButton(currentDialog, '确定')
  await waitForMessage(page, '报名提交成功')

  await fillFormInput(page, '关键字', projectName)
  await clickButton(page, '搜索')
  const row = rowByText(page, projectName)
  await row.waitFor({ timeout: 10000 })
  await row.locator('button:has-text("提交材料")').click()
  const materialDialog = dialog(page)
  await uploadInForm(materialDialog, '材料文件', samplePdf)
  await fillFormInput(materialDialog, '提交说明', '前端走查上传的真实材料')
  await clickButton(materialDialog, '确认上传')
  await waitForMessage(page, '材料提交成功')

  await rowByText(page, projectName).locator('button:has-text("详情")').click()
  const currentDrawer = drawer(page)
  await currentDrawer.locator('button:has-text("查看")').first().click()
  await waitForPreviewDialog(page, 'sample.pdf')
  await saveScreenshot(page, '04-registration-material-preview')
  await closeDialog(page)
  await closeDrawer(page)

  await selectFormOption(page, page, '数据质量', '脏数据')
  await clickButton(page, '搜索')
  await page.locator('.el-table__row').first().waitFor({ timeout: 10000 })
  await saveScreenshot(page, '05-registration-dirty-filter')
  await clickButton(page, '重置')
  logStep('报名管理', 'passed', `已创建报名 ${projectName} 并上传、预览真实材料`)
}

async function approveRegistration(page) {
  await gotoModule(page, '/competition/reviews', '材料审核')
  await fillFormInput(page, '关键字', projectName)
  await clickButton(page, '筛选')
  const row = rowByText(page, projectName)
  await row.waitFor({ timeout: 10000 })
  await row.locator('button:has-text("通过")').click()
  const currentDialog = dialog(page)
  await fillFormInput(currentDialog, '审核意见', '前端走查审核通过')
  await clickButton(currentDialog, '确定')
  await waitForMessage(page, '审核通过成功')
  await saveScreenshot(page, '06-review-approved')
  logStep('材料审核', 'passed', `已通过前端审核报名 ${projectName}`)
}

async function inspectQualification(page) {
  await gotoModule(page, '/competition/qualifications', '资格管理')
  await fillFormInput(page, '关键字', projectName)
  await clickButton(page, '搜索')
  const row = rowByText(page, projectName)
  await row.waitFor({ timeout: 10000 })
  await row.locator('button:has-text("详情")').click()
  await drawer(page).locator(`text=${projectName}`).waitFor({ timeout: 10000 })
  await saveScreenshot(page, '07-qualification-detail')
  await closeDrawer(page)
  logStep('资格管理', 'passed', '已打开资格详情并核对审核后的报名上下文')
}

async function createResult(page) {
  await gotoModule(page, '/competition/results', '赛后管理')
  await clickButton(page, '新增成绩')
  const currentDialog = dialog(page)
  await selectFormOption(page, currentDialog, '赛事', contestName)
  await selectFormOption(page, currentDialog, '学生', `${studentName}（${studentNo}）`)
  await fillFormInput(currentDialog, '获奖等级', '一等奖')
  await selectFormOption(page, currentDialog, '结果状态', '已获奖')
  await fillFormInput(currentDialog, '成绩分数', '98.5')
  await fillFormInput(currentDialog, '名次', '1')
  await fillFormInput(currentDialog, '证书编号', `CERT-${stamp.slice(-6)}`)
  await fillFormInput(currentDialog, '归档备注', '前端走查成绩记录')
  await clickButton(currentDialog, '确定')
  await waitForMessage(page, '成绩创建成功')

  await fillFormInput(page, '关键字', studentName)
  await clickButton(page, '搜索')
  await rowByText(page, studentName).waitFor({ timeout: 10000 })
  await page.locator('.el-tabs__item').filter({ hasText: '证书管理' }).click()
  await page.locator('text=证书管理').first().waitFor({ timeout: 10000 })
  await fillFormInput(page, '关键字', studentName)
  await clickButton(page, '搜索')
  const certificateRow = rowByText(page, studentName)
  await certificateRow.waitFor({ timeout: 10000 })
  await certificateRow.locator('button:has-text("上传证书")').click()
  const certificateDialog = dialog(page)
  await uploadInForm(certificateDialog, '证书文件', samplePdf)
  await clickButton(certificateDialog, '确定上传')
  await waitForMessage(page, '证书归档成功')

  await certificateRow.locator('button:has-text("查看证书")').click()
  await waitForPreviewDialog(page, 'sample.pdf')
  await saveScreenshot(page, '08-certificate-preview')
  await closeDialog(page)
  logStep('赛后管理', 'passed', `已新增成绩并上传、预览证书`)
}

async function inspectWorkflowMessages(page) {
  await gotoModule(page, '/competition/messages', '通知中心')
  await page.locator('.el-tabs__item').filter({ hasText: '通知发布' }).first().click()
  await page.locator('text=通知发布').first().waitFor({ timeout: 10000 })
  await fillFormInput(page, '关键字', reviewMessageTitle)
  await clickButton(page, '筛选')
  const row = rowByText(page, reviewMessageTitle)
  await row.waitFor({ timeout: 10000 })
  await row.locator('button:has-text("查看")').click()
  await drawer(page).locator(`text=${reviewMessageTitle}`).waitFor({ timeout: 10000 })
  await saveScreenshot(page, '09-message-detail')
  await closeDrawer(page)
  logStep('通知中心', 'passed', `已在通知中心看到自动生成的流程通知 ${reviewMessageTitle}`)
}

async function inspectStatistics(page) {
  await gotoModule(page, '/competition/statistics', '统计报表')
  await page.locator('.competition-summary-chip').first().waitFor({ timeout: 10000 })
  await selectFormOption(page, page, '赛事', contestName)
  await clickButton(page, '统计')
  await page.locator('.el-tabs__item').filter({ hasText: '导出中心' }).click()
  await page.locator('text=导出记录').first().waitFor({ timeout: 10000 })
  await clickButton(page, '创建统计导出')
  await waitForMessage(page, '统计导出任务已创建')
  const exportPane = page.locator('.el-tab-pane').filter({ hasText: '导出记录' }).first()
  const exportRow = exportPane.locator('.el-table__row').filter({ hasText: contestName }).first()
  await waitForLocatorText(exportRow, contestName, '已完成')
  const exportRowText = (await exportRow.textContent()) || ''
  if (!exportRowText.includes('获奖统计报表')) {
    throw new Error(`导出记录行缺少任务类型，实际为：${exportRowText}`)
  }
  await saveScreenshot(page, '10-statistics')
  logStep('统计报表', 'passed', '统计页已正常加载摘要卡片，导出中心可创建任务并轮询到完成状态')
}

async function inspectFileCenter(page) {
  await gotoModule(page, '/competition/files', '文件中心')
  await page.locator('.competition-file-tree').waitFor({ timeout: 10000 })
  await fillFormInput(page, '关键字', studentName)
  await clickButton(page, '搜索')
  const row = page.locator('.el-table__row').filter({ hasText: studentName }).filter({ hasText: '证书文件' }).first()
  await row.waitFor({ timeout: 10000 })
  await row.locator('button:has-text("预览")').click()
  await waitForPreviewDialog(page, 'sample.pdf')
  await closeDialog(page)

  await page.locator('.el-tabs__item').filter({ hasText: '导出规则' }).click()
  await page.locator('button:has-text("新增规则")').first().waitFor({ timeout: 10000 })
  await clickButton(page, '新增规则')
  await dialog(page).locator('text=模板变量').first().waitFor({ timeout: 10000 })
  await clickButton(dialog(page), '取消')

  await page.locator('.el-tabs__item').filter({ hasText: '导出批次' }).click()
  await page.locator('text=导出批次').first().waitFor({ timeout: 10000 })

  await page.locator('.el-tabs__item').filter({ hasText: '投递渠道' }).click()
  await page.locator('button:has-text("新增渠道")').first().waitFor({ timeout: 10000 })
  await clickButton(page, '新增渠道')
  await dialog(page).locator('.el-dialog__title').filter({ hasText: '新增投递渠道' }).first().waitFor({ timeout: 10000 })
  await clickButton(dialog(page), '取消')

  await saveScreenshot(page, '11-file-center')
  logStep('文件中心', 'passed', '文件中心已聚合显示证书文件，并打通导出规则、批次与投递渠道标签页')
}

async function inspectSystemSettings(page) {
  await gotoModule(page, '/system/role', '角色管理')
  await page.locator('button:has-text("新增")').first().waitFor({ timeout: 10000 })
  await rowByText(page, '系统管理员').waitFor({ timeout: 10000 })

  await gotoModule(page, '/system/menu', '菜单管理')
  await page.locator('button:has-text("新增")').first().waitFor({ timeout: 10000 })
  await rowByText(page, '系统设置').waitFor({ timeout: 10000 })

  await gotoModule(page, '/system/dict', '字典管理')
  await page.locator('button:has-text("新增")').first().waitFor({ timeout: 10000 })
  await rowByText(page, 'sys_normal_disable').waitFor({ timeout: 10000 })

  await gotoModule(page, '/system/config', '参数管理')
  await page.locator('button:has-text("新增")').first().waitFor({ timeout: 10000 })
  await rowByText(page, 'sys.user.initPassword').waitFor({ timeout: 10000 })

  await saveScreenshot(page, '12-system-settings')
  logStep('系统设置', 'passed', '角色、菜单、字典、参数页面均已成功打开')
}

async function inspectMonitorPages(page) {
  await gotoModule(page, '/monitor/operlog', '操作日志')
  await page.locator('button:has-text("清空")').first().waitFor({ timeout: 10000 })
  await page.locator('.el-table__row').first().waitFor({ timeout: 10000 })

  await gotoModule(page, '/monitor/logininfor', '登录日志')
  await page.locator('button:has-text("清空")').first().waitFor({ timeout: 10000 })
  await page.locator('.el-table__row').first().waitFor({ timeout: 10000 })

  await gotoModule(page, '/monitor/runtime', '存储与备份运行态')
  await page.locator('button:has-text("仅备份数据")').first().waitFor({ timeout: 10000 })
  await page.locator('button:has-text("仅备份数据")').first().click()
  await waitForMessage(page, '数据备份创建成功')
  await page.locator('.runtime-card__table .el-table__row').first().waitFor({ timeout: 10000 })

  await saveScreenshot(page, '13-monitor-pages')
  logStep('系统监控', 'passed', '操作日志、登录日志与存储备份运行态页面均已成功打开并可创建备份')
}

async function verifyStudentInbox() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1600, height: 1200 } })
  const page = await context.newPage()
  try {
    await login(page, studentNo, 'Demo123!')
    await gotoModule(page, '/competition/messages', '通知中心')
    const inboxRow = rowByText(page, reviewMessageTitle)
    await inboxRow.waitFor({ timeout: 15000 })
    await inboxRow.locator('button:has-text("查看")').click()
    await drawer(page).locator(`text=${reviewMessageTitle}`).waitFor({ timeout: 10000 })
    await saveScreenshot(page, '14-student-inbox')
    logStep('学生收件箱', 'passed', '学生端已经能看到并打开自动生成的审核结果通知')
  } finally {
    await context.close()
    await browser.close()
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1600, height: 1200 } })
  const page = await context.newPage()
  let capturedError

  try {
    await login(page, 'admin', 'Admin123!')
    logStep('登录', 'passed', '管理员成功登录前端')
    await saveScreenshot(page, '00-dashboard')

    await createStudent(page)
    await createContest(page)
    await createRegistration(page)
    await approveRegistration(page)
    await inspectQualification(page)
    await createResult(page)
    await inspectWorkflowMessages(page)
    await inspectStatistics(page)
    await inspectFileCenter(page)
    await inspectSystemSettings(page)
    await inspectMonitorPages(page)
  } catch (error) {
    logStep('前端走查', 'failed', error instanceof Error ? error.message : String(error))
    await saveScreenshot(page, '99-failure')
    capturedError = error
  } finally {
    await context.close()
    await browser.close()
  }

  if (!capturedError) {
    await verifyStudentInbox()
  }

  fs.writeFileSync(path.join(outputDir, 'frontend-walkthrough-report.json'), JSON.stringify(report, null, 2))

  if (capturedError) {
    throw capturedError
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
