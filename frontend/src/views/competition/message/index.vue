<script setup>
import { Bell, ChatDotRound, EditPen, Plus, Refresh, Search, View } from '@element-plus/icons-vue'
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listContests } from '@/api/competition/contest'
import { addMessage, addTodoRule, applyTodoRule, cancelMessage, listMessageFailures, listMessages, listTodoRules, readMessage, sendMessage, updateMessage, updateTodoRule } from '@/api/competition/message'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import CompetitionStatusTag from '@/components/CompetitionStatusTag.vue'
import useUserStore from '@/store/modules/user'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const userStore = useUserStore()
const loading = ref(false)
const submitting = ref(false)
const open = ref(false)
const detailOpen = ref(false)
const ruleOpen = ref(false)
const ruleEditOpen = ref(false)
const failureOpen = ref(false)
const ruleLoading = ref(false)
const ruleSubmitting = ref(false)
const failureLoading = ref(false)
const applyingRuleId = ref(undefined)
const dialogTitle = ref('新建通知')
const ruleDialogTitle = ref('新建待办规则')
const activeTab = ref('inbox')
const total = ref(0)
const contestOptions = ref([])
const messageList = ref([])
const todoRuleList = ref([])
const failureList = ref([])
const activeMessage = ref({})
const formRef = ref()
const ruleFormRef = ref()
const manageQuery = reactive({ keyword: '', sendStatus: '', messageType: '', contestId: undefined, targetRole: '', priority: '', pageNum: 1, pageSize: 10 })
const inboxQuery = reactive({ keyword: '', messageType: '', contestId: undefined, priority: '', pageNum: 1, pageSize: 10 })
const form = reactive({ id: undefined, title: '', summary: '', content: '', messageType: 'notice', targetScope: 'all', contestId: undefined, targetRoles: [], targetStatus: '', priority: 'normal', plannedSendAt: '' })
const ruleTotal = ref(0)
const failureTotal = ref(0)
const ruleQuery = reactive({ keyword: '', scene: '', enabledStatus: '', pageNum: 1, pageSize: 10 })
const failureQuery = reactive({ keyword: '', roleCode: '', messageId: undefined, pageNum: 1, pageSize: 10 })
const ruleForm = reactive({
  id: undefined,
  ruleName: '',
  scene: 'pending_materials',
  contestId: undefined,
  targetRoles: ['student', 'teacher'],
  priority: 'high',
  enabledStatus: true,
  titleTemplate: '',
  summaryTemplate: '',
  contentTemplate: '',
})

const roleOptions = [
  { label: '管理员', value: 'admin' },
  { label: '教师', value: 'teacher' },
  { label: '审核人', value: 'reviewer' },
  { label: '学生', value: 'student' },
]

const scopeOptions = [
  { label: '全员', value: 'all' },
  { label: '指定赛事', value: 'contest' },
  { label: '指定角色', value: 'role' },
]

const todoSceneOptions = [
  { label: '未提交原件提醒', value: 'pending_materials' },
  { label: '补正未完成提醒', value: 'correction_required' },
]

const canManage = computed(() => Boolean(userStore.capabilities.manageMessages))
const currentQuery = computed(() => (activeTab.value === 'manage' ? manageQuery : inboxQuery))
const pageTitle = computed(() => (activeTab.value === 'manage' ? '通知发布' : '我的消息'))
const pageSubtitle = computed(() => (activeTab.value === 'manage' ? '维护通知内容、待办规则、发送状态和失败记录。' : '查看当前账号可见消息并处理已读状态。'))
const pageScopeNote = computed(() => (
  activeTab.value === 'manage'
    ? '注意：通知发布页除了手工发送，还要负责待办规则和失败排查；最终谁能收到，取决于范围、赛事和目标角色。'
    : '注意：这里是当前账号的收件箱，只负责查看、确认已读，不负责发布消息。'
))
const pageGuide = computed(() => {
  if (activeTab.value === 'manage') {
    return {
      eyebrow: '发布入口',
      title: '先定触达范围，再写用户看得懂的摘要和正文',
      desc: '一条通知至少要让接收人看出三件事：发给谁、为什么发、收到后要不要马上处理。',
      steps: [
        { step: '1', title: '先选范围和角色', desc: '先确定是全员、指定赛事还是指定角色，避免误发或漏发。' },
        { step: '2', title: '再写摘要和正文', desc: '摘要先说结论，正文再补充要求、时间和处理动作。' },
        { step: '3', title: '最后确认发送状态', desc: '发送前再核对优先级、计划时间和关联赛事，避免临时返工。' },
      ],
    }
  }
  return {
    eyebrow: '收件箱',
    title: '先判断这条消息要不要处理，再决定是否标记已读',
    desc: '阅读顺序按标题、摘要、优先级和时间节点来，不用先钻进长正文里找重点。',
    steps: [
      { step: '1', title: '先看标题和优先级', desc: '先筛出真正需要马上处理的提醒和高优先级消息。' },
      { step: '2', title: '再打开详情看摘要', desc: '详情会先告诉你这条消息是什么、要不要动作、来自哪里。' },
      { step: '3', title: '处理完再标记已读', desc: '如果只是看看不处理，已读状态很容易掩盖后续待办。' },
    ],
  }
})
const guideActions = computed(() => {
  if (activeTab.value === 'manage') {
    return canManage.value
      ? [
          { key: 'add', label: '新建通知', type: 'primary', plain: false },
          { key: 'todo-rules', label: '待办规则', type: 'warning' },
          { key: 'failures', label: '失败记录', type: 'danger' },
          { key: 'switch-inbox', label: '查看我的消息', type: 'info' },
        ]
      : []
  }
  return canManage.value
    ? [{ key: 'switch-manage', label: '去通知发布', type: 'primary' }]
    : []
})

const formRules = {
  title: [{ required: true, message: '请填写通知标题', trigger: 'blur' }],
  content: [{ required: true, message: '请填写通知内容', trigger: 'blur' }],
  messageType: [{ required: true, message: '请选择通知类型', trigger: 'change' }],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }],
}

const ruleFormRules = {
  ruleName: [{ required: true, message: '请填写规则名称', trigger: 'blur' }],
  scene: [{ required: true, message: '请选择规则场景', trigger: 'change' }],
  priority: [{ required: true, message: '请选择提醒优先级', trigger: 'change' }],
}

const metricCards = computed(() => {
  if (activeTab.value === 'manage') {
    return [
      { title: '消息总数', value: total.value, desc: '按筛选条件统计', icon: Bell },
      { title: '已发送', value: messageList.value.filter(item => item.sendStatus === 'sent').length, desc: '当前页已发送消息', icon: ChatDotRound },
      { title: '发送失败', value: messageList.value.filter(item => item.sendStatus === 'failed').length, desc: '当前页需排查消息', icon: Search },
      { title: '待发送', value: messageList.value.filter(item => item.sendStatus === 'pending').length, desc: '当前页待处理消息', icon: Refresh },
    ]
  }
  return [
    { title: '收件箱总数', value: total.value, desc: '当前账号可见消息', icon: Bell },
    { title: '未读消息', value: messageList.value.filter(item => !item.readStatus).length, desc: '待处理消息', icon: ChatDotRound },
    { title: '高优先级', value: messageList.value.filter(item => ['high', 'urgent'].includes(item.priority)).length, desc: '当前页重点消息', icon: Refresh },
    { title: '已读消息', value: messageList.value.filter(item => item.readStatus).length, desc: '已完成阅读', icon: Search },
  ]
})

function formatDateTime(value, options = {}) {
  const { withTime = true, fallback = '待补充' } = options
  return formatBeijingDateTime(value, { fallback, withTime, withSeconds: false })
}

function messageTypeLabel(value) {
  return { notice: '公告', todo: '提醒', message: '通知' }[value] || value
}

function messageTypeTagType(value) {
  return { notice: 'info', todo: 'warning', message: 'primary' }[value] || 'info'
}

function priorityLabel(value) {
  return { low: '低', normal: '普通', high: '高', urgent: '紧急' }[value] || value
}

function priorityTagType(value) {
  return { low: 'info', normal: 'info', high: 'warning', urgent: 'danger' }[value] || 'info'
}

function scopeLabel(value) {
  return { all: '全员', contest: '指定赛事', role: '指定角色', user: '指定用户' }[value] || value || '全员'
}

function readStatusLabel(value) {
  return value ? '已读' : '未读'
}

function parseTargetRoles(value) {
  if (Array.isArray(value)) return value.filter(Boolean)
  if (!value) return []
  return String(value).split(',').map(item => item.trim()).filter(Boolean)
}

function roleLabel(value) {
  return roleOptions.find(item => item.value === value)?.label || value
}

function roleNames(value) {
  const roles = parseTargetRoles(value)
  return roles.length ? roles.map(roleLabel).join('、') : '全部'
}

function todoSceneLabel(value) {
  return todoSceneOptions.find(item => item.value === value)?.label || value
}

function audienceLabel(row) {
  const roles = row.targetRoles?.length ? row.targetRoles : row.targetRole
  const roleLabelText = `角色：${roleNames(roles)}`
  const statusLabel = row.targetStatus ? `状态：${row.targetStatus}` : '状态：不限'
  return `${roleLabelText} / ${statusLabel}`
}

function buildSnippet(value, limit = 88) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > limit ? `${text.slice(0, limit)}...` : text
}

const detailHeaderSubtitle = computed(() => {
  const row = activeMessage.value || {}
  const contestLabel = row.contestName || (activeTab.value === 'manage' ? '未关联赛事' : '公共消息')
  const sourceLabel = row.createdByName || '系统通知'
  const timeLabel = formatDateTime(row.createdAt, { fallback: '未记录' })
  return [contestLabel, sourceLabel, timeLabel].join(' · ')
})

const detailSummaryText = computed(() => {
  const row = activeMessage.value || {}
  if (row.summary) return row.summary
  const snippet = buildSnippet(row.content)
  if (snippet) {
    return activeTab.value === 'manage'
      ? `未单独填写摘要，接收方大概率会先看到正文前半段：${snippet}`
      : snippet
  }
  return activeTab.value === 'manage'
    ? '未填写摘要，接收方很难快速判断这条通知值不值得马上处理。'
    : '这条消息没有摘要，请直接查看完整正文。'
})

const detailOverview = computed(() => {
  const row = activeMessage.value || {}
  if (activeTab.value === 'manage') {
    return [
      { label: '关联赛事', value: row.contestName || '未关联赛事' },
      { label: '触达对象', value: audienceLabel(row) },
      { label: '发送范围', value: scopeLabel(row.targetScope) },
      { label: '创建人', value: row.createdByName || '系统' },
      { label: '失败记录', value: row.failureCount ? `${row.failureCount} 条` : '无' },
      { label: '最近失败', value: row.latestFailureReason || '无' },
    ]
  }
  return [
    { label: '关联赛事', value: row.contestName || '公共消息' },
    { label: '消息来源', value: row.createdByName || '系统通知' },
    { label: '优先级', value: priorityLabel(row.priority) },
    { label: '当前状态', value: readStatusLabel(row.readStatus) },
  ]
})

const detailTimeline = computed(() => {
  const row = activeMessage.value || {}
  if (activeTab.value === 'manage') {
    return [
      {
        label: '创建时间',
        value: formatDateTime(row.createdAt, { fallback: '未记录' }),
        desc: row.createdByName ? `由 ${row.createdByName} 创建` : '由系统创建',
        type: 'info',
      },
      {
        label: '计划发送',
        value: formatDateTime(row.plannedSendAt, { fallback: '未设置' }),
        desc: row.sendStatus === 'sent' ? '这条通知已经发送' : row.sendStatus === 'canceled' ? '这条通知已取消' : row.sendStatus === 'failed' ? '发送失败，请检查失败记录后重试' : '发送前仍可继续编辑',
        type: row.sendStatus === 'sent' ? 'success' : row.sendStatus === 'canceled' ? 'info' : row.sendStatus === 'failed' ? 'danger' : 'warning',
        hollow: !row.plannedSendAt,
      },
      {
        label: '阅读反馈',
        value: formatDateTime(row.readAt, { fallback: row.readStatus ? '已读，未记录时间' : '暂无阅读记录' }),
        desc: row.readStatus ? '当前账号已确认阅读' : '当前还没有阅读反馈',
        type: row.readStatus ? 'success' : 'info',
        hollow: !row.readStatus,
      },
    ]
  }
  return [
    {
      label: '接收时间',
      value: formatDateTime(row.createdAt, { fallback: '未记录' }),
      desc: row.contestName ? `来自 ${row.contestName}` : '来自系统公共消息',
      type: 'primary',
    },
    {
      label: '阅读时间',
      value: formatDateTime(row.readAt, { fallback: row.readStatus ? '已读，未记录时间' : '尚未阅读' }),
      desc: row.readStatus ? '你已经完成已读确认' : '当前还没有已读记录',
      type: row.readStatus ? 'success' : 'info',
      hollow: !row.readStatus,
    },
  ]
})

const detailAction = computed(() => {
  const row = activeMessage.value || {}
  if (!row.id) {
    return { tone: 'primary', eyebrow: '处理建议', title: '暂无消息', desc: '请选择一条消息查看详情。' }
  }
  if (activeTab.value === 'manage') {
    if (row.sendStatus === 'pending') {
      return {
        tone: 'warning',
        eyebrow: '当前状态',
        title: '这条通知还没有发出去',
        desc: '先检查接收对象、摘要是否说清楚，再决定是否发送。',
      }
    }
    if (row.sendStatus === 'sent') {
      return {
        tone: 'success',
        eyebrow: '当前状态',
        title: '这条通知已经发送',
        desc: row.readStatus ? '当前账号已读，可继续跟进后续执行情况。' : '通知已下发，建议关注阅读反馈和后续处理结果。',
      }
    }
    if (row.sendStatus === 'canceled') {
      return {
        tone: 'info',
        eyebrow: '当前状态',
        title: '这条通知已取消',
        desc: '取消后不会继续下发；如需重新通知，建议调整内容后重新创建。',
      }
    }
    if (row.sendStatus === 'failed') {
      return {
        tone: 'danger',
        eyebrow: '当前状态',
        title: '这条通知发送失败',
        desc: row.latestFailureReason || '当前没有匹配到接收对象，请先检查失败记录和触达条件。',
      }
    }
    return {
      tone: 'primary',
      eyebrow: '当前状态',
      title: '请确认通知状态',
      desc: '建议检查发送状态和接收范围是否正确。',
    }
  }
  if (row.messageType === 'todo') {
    return row.readStatus
      ? {
          tone: 'warning',
          eyebrow: '处理建议',
          title: '这是一条待落实的提醒',
          desc: '你已经读过，但仍建议按摘要和正文尽快处理。',
        }
      : {
          tone: 'danger',
          eyebrow: '处理建议',
          title: '请优先处理这条提醒',
          desc: '先看摘要和正文，再完成“标记已读”，避免遗漏。',
        }
  }
  if (!row.readStatus) {
    return {
      tone: 'primary',
      eyebrow: '处理建议',
      title: '建议先完成已读确认',
      desc: '这条消息本身不复杂，但先确认已读能避免后续遗漏。',
    }
  }
  return {
    tone: 'success',
    eyebrow: '处理建议',
    title: '你已经完成阅读确认',
    desc: '如果还需要动作，请按正文说明继续处理。',
  }
})

function resetForm() {
  Object.assign(form, { id: undefined, title: '', summary: '', content: '', messageType: 'notice', targetScope: 'all', contestId: undefined, targetRoles: [], targetStatus: '', priority: 'normal', plannedSendAt: '' })
  nextTick(() => formRef.value?.clearValidate())
}

function resetRuleForm() {
  Object.assign(ruleForm, {
    id: undefined,
    ruleName: '',
    scene: 'pending_materials',
    contestId: undefined,
    targetRoles: ['student', 'teacher'],
    priority: 'high',
    enabledStatus: true,
    titleTemplate: '',
    summaryTemplate: '',
    contentTemplate: '',
  })
  nextTick(() => ruleFormRef.value?.clearValidate())
}

function handleScopeChange(value) {
  if (value !== 'all') return
  form.contestId = undefined
  form.targetRoles = []
  form.targetStatus = ''
}

function resetManageQuery() {
  manageQuery.keyword = ''
  manageQuery.sendStatus = ''
  manageQuery.messageType = ''
  manageQuery.contestId = undefined
  manageQuery.targetRole = ''
  manageQuery.priority = ''
  manageQuery.pageNum = 1
  getList()
}

function resetInboxQuery() {
  inboxQuery.keyword = ''
  inboxQuery.messageType = ''
  inboxQuery.contestId = undefined
  inboxQuery.priority = ''
  inboxQuery.pageNum = 1
  getList()
}

function resetRuleQuery() {
  ruleQuery.keyword = ''
  ruleQuery.scene = ''
  ruleQuery.enabledStatus = ''
  ruleQuery.pageNum = 1
  getTodoRuleList()
}

function resetFailureQuery() {
  failureQuery.keyword = ''
  failureQuery.roleCode = ''
  failureQuery.messageId = undefined
  failureQuery.pageNum = 1
  getFailureList()
}

async function getList() {
  loading.value = true
  try {
    const res = await listMessages({ ...currentQuery.value, scene: activeTab.value })
    messageList.value = res.data.list || []
    total.value = Number(res.data.total || 0)
    currentQuery.value.pageNum = Number(res.data.pageNum || currentQuery.value.pageNum)
    currentQuery.value.pageSize = Number(res.data.pageSize || currentQuery.value.pageSize)
  } finally {
    loading.value = false
  }
}

async function getTodoRuleList() {
  ruleLoading.value = true
  try {
    const res = await listTodoRules(ruleQuery)
    todoRuleList.value = res.data.list || []
    ruleTotal.value = Number(res.data.total || 0)
    ruleQuery.pageNum = Number(res.data.pageNum || ruleQuery.pageNum)
    ruleQuery.pageSize = Number(res.data.pageSize || ruleQuery.pageSize)
  } finally {
    ruleLoading.value = false
  }
}

async function getFailureList() {
  failureLoading.value = true
  try {
    const res = await listMessageFailures(failureQuery)
    failureList.value = res.data.list || []
    failureTotal.value = Number(res.data.total || 0)
    failureQuery.pageNum = Number(res.data.pageNum || failureQuery.pageNum)
    failureQuery.pageSize = Number(res.data.pageSize || failureQuery.pageSize)
  } finally {
    failureLoading.value = false
  }
}

async function loadContests() {
  const res = await listContests({ pageSize: 200 })
  contestOptions.value = res.data.list || []
}

async function openRulePanel() {
  ruleOpen.value = true
  await getTodoRuleList()
}

async function openFailurePanel(messageId) {
  failureQuery.messageId = messageId || undefined
  failureOpen.value = true
  await getFailureList()
}

function handleAdd() {
  resetForm()
  dialogTitle.value = '新建通知'
  open.value = true
}

function handleAddRule() {
  resetRuleForm()
  ruleDialogTitle.value = '新建待办规则'
  ruleEditOpen.value = true
}

function handleEdit(row) {
  resetForm()
  Object.assign(form, {
    id: row.id,
    title: row.title || '',
    summary: row.summary || '',
    content: row.content || '',
    messageType: row.messageType || 'notice',
    targetScope: row.targetScope || 'all',
    contestId: row.contestId || undefined,
    targetRoles: parseTargetRoles(row.targetRoles?.length ? row.targetRoles : row.targetRole),
    targetStatus: row.targetStatus || '',
    priority: row.priority || 'normal',
    plannedSendAt: row.plannedSendAt || '',
  })
  dialogTitle.value = '编辑通知'
  open.value = true
}

function handleEditRule(row) {
  resetRuleForm()
  Object.assign(ruleForm, {
    id: row.id,
    ruleName: row.ruleName || '',
    scene: row.scene || 'pending_materials',
    contestId: row.contestId || undefined,
    targetRoles: parseTargetRoles(row.targetRoles?.length ? row.targetRoles : row.targetRole),
    priority: row.priority || 'high',
    enabledStatus: Boolean(Number(row.enabledStatus ?? 1)),
    titleTemplate: row.titleTemplate || '',
    summaryTemplate: row.summaryTemplate || '',
    contentTemplate: row.contentTemplate || '',
  })
  ruleDialogTitle.value = '编辑待办规则'
  ruleEditOpen.value = true
}

function handlePreview(row) {
  activeMessage.value = { ...row }
  detailOpen.value = true
}

async function submitForm() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    const payload = {
      id: form.id,
      title: form.title,
      summary: form.summary,
      content: form.content,
      messageType: form.messageType,
      targetScope: form.targetScope,
      contestId: form.contestId,
      targetRoles: form.targetRoles,
      targetStatus: form.targetStatus,
      priority: form.priority,
      plannedSendAt: form.plannedSendAt,
    }
    if (form.id) {
      await updateMessage(payload)
      ElMessage.success('通知更新成功')
    } else {
      await addMessage(payload)
      ElMessage.success('通知创建成功')
    }
    open.value = false
    await getList()
  } finally {
    submitting.value = false
  }
}

async function submitRuleForm() {
  await ruleFormRef.value?.validate()
  ruleSubmitting.value = true
  try {
    const payload = {
      id: ruleForm.id,
      ruleName: ruleForm.ruleName,
      scene: ruleForm.scene,
      contestId: ruleForm.contestId,
      targetRoles: ruleForm.targetRoles,
      priority: ruleForm.priority,
      enabledStatus: ruleForm.enabledStatus,
      titleTemplate: ruleForm.titleTemplate,
      summaryTemplate: ruleForm.summaryTemplate,
      contentTemplate: ruleForm.contentTemplate,
    }
    if (ruleForm.id) {
      await updateTodoRule(payload)
      ElMessage.success('待办规则更新成功')
    } else {
      await addTodoRule(payload)
      ElMessage.success('待办规则创建成功')
    }
    ruleEditOpen.value = false
    await getTodoRuleList()
  } finally {
    ruleSubmitting.value = false
  }
}

async function handleSend(row) {
  await ElMessageBox.confirm(`确认发送“${row.title}”？`, '发送确认', { type: 'warning' })
  const res = await sendMessage(row.id)
  if (detailOpen.value && activeMessage.value.id === row.id) {
    activeMessage.value = res.data
  }
  ElMessage[res.data.sendStatus === 'sent' ? 'success' : 'warning'](res.msg || (res.data.sendStatus === 'sent' ? '通知发送成功' : '通知发送失败'))
  await getList()
}

async function handleCancel(row) {
  await ElMessageBox.confirm(`确认取消“${row.title}”？`, '取消确认', { type: 'warning' })
  const res = await cancelMessage(row.id)
  if (detailOpen.value && activeMessage.value.id === row.id) {
    activeMessage.value = res.data
  }
  ElMessage.success('通知已取消')
  await getList()
}

async function handleRead(row) {
  if (row.readStatus) {
    ElMessage.info('该消息已读')
    return
  }
  const res = await readMessage(row.id)
  if (detailOpen.value && activeMessage.value.id === row.id) {
    activeMessage.value = res.data
  }
  ElMessage.success('消息已读')
  await getList()
}

async function handleApplyRule(row) {
  applyingRuleId.value = row.id
  try {
    const res = await applyTodoRule(row.id)
    ElMessage.success(`待办规则已执行，生成 ${res.data.generatedCount || 0} 条提醒`)
    await Promise.all([getTodoRuleList(), getList()])
  } finally {
    applyingRuleId.value = undefined
  }
}

async function handleRuleEnabledChange(row, value) {
  await updateTodoRule({
    id: row.id,
    ruleName: row.ruleName,
    scene: row.scene,
    contestId: row.contestId,
    targetRoles: parseTargetRoles(row.targetRoles?.length ? row.targetRoles : row.targetRole),
    priority: row.priority,
    enabledStatus: value,
    titleTemplate: row.titleTemplate,
    summaryTemplate: row.summaryTemplate,
    contentTemplate: row.contentTemplate,
  })
  ElMessage.success(value ? '规则已启用' : '规则已停用')
  await getTodoRuleList()
}

async function handleTabChange(tab) {
  activeTab.value = tab
  await getList()
}

async function handleGuideAction(action) {
  if (action.key === 'add') {
    handleAdd()
    return
  }
  if (action.key === 'todo-rules') {
    await openRulePanel()
    return
  }
  if (action.key === 'failures') {
    await openFailurePanel()
    return
  }
  if (action.key === 'switch-manage') {
    await handleTabChange('manage')
    return
  }
  if (action.key === 'switch-inbox') {
    await handleTabChange('inbox')
  }
}

onMounted(async () => {
  activeTab.value = canManage.value ? 'manage' : 'inbox'
  await loadContests()
  await getList()
  if (canManage.value) {
    await Promise.all([getTodoRuleList(), getFailureList()])
  }
})
</script>

<template>
  <div class="competition-page">
    <el-card class="competition-control-card" shadow="never">
      <template #header>
        <div class="competition-control-head">
          <div class="competition-control-copy">
            <div class="competition-control-eyebrow">Messages Center</div>
            <div class="competition-control-title">通知中心</div>
            <div class="competition-control-subtitle">{{ pageSubtitle }}</div>
          </div>
          <div class="competition-control-actions">
            <el-button v-if="canManage && activeTab === 'manage'" type="primary" :icon="Plus" @click="handleAdd">新建通知</el-button>
            <el-button v-if="canManage && activeTab === 'manage'" plain @click="openRulePanel">待办规则</el-button>
            <el-button v-if="canManage && activeTab === 'manage'" plain @click="openFailurePanel()">失败记录</el-button>
            <el-button plain :icon="Refresh" @click="getList">刷新列表</el-button>
          </div>
        </div>
      </template>

      <el-tabs v-if="canManage" v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="通知发布" name="manage" />
        <el-tab-pane label="我的消息" name="inbox" />
      </el-tabs>

      <competition-guide-panel
        :note="pageScopeNote"
        :eyebrow="pageGuide.eyebrow"
        :title="pageGuide.title"
        :description="pageGuide.desc"
        :steps="pageGuide.steps"
        :actions="guideActions"
        @action="handleGuideAction"
      />

      <el-form v-if="activeTab === 'manage'" :model="manageQuery" :inline="true" class="competition-filter-form">
        <el-form-item label="关键字"><el-input v-model="manageQuery.keyword" placeholder="标题/摘要/内容" clearable @keyup.enter="getList" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="manageQuery.sendStatus" clearable style="width: 120px">
            <el-option label="待处理" value="pending" />
            <el-option label="已发送" value="sent" />
            <el-option label="发送失败" value="failed" />
            <el-option label="已取消" value="canceled" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="manageQuery.messageType" clearable style="width: 120px">
            <el-option label="公告" value="notice" />
            <el-option label="提醒" value="todo" />
            <el-option label="通知" value="message" />
          </el-select>
        </el-form-item>
        <el-form-item label="赛事">
          <el-select v-model="manageQuery.contestId" clearable style="width: 180px">
            <el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="manageQuery.targetRole" clearable style="width: 120px">
            <el-option label="管理员" value="admin" />
            <el-option label="教师" value="teacher" />
            <el-option label="审核人" value="reviewer" />
            <el-option label="学生" value="student" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="manageQuery.priority" clearable style="width: 120px">
            <el-option label="低" value="low" />
            <el-option label="普通" value="normal" />
            <el-option label="高" value="high" />
            <el-option label="紧急" value="urgent" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="getList">筛选</el-button>
          <el-button :icon="Refresh" @click="resetManageQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-form v-else :model="inboxQuery" :inline="true" class="competition-filter-form">
        <el-form-item label="关键字"><el-input v-model="inboxQuery.keyword" placeholder="标题/摘要/内容" clearable @keyup.enter="getList" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="inboxQuery.messageType" clearable style="width: 120px">
            <el-option label="公告" value="notice" />
            <el-option label="提醒" value="todo" />
            <el-option label="通知" value="message" />
          </el-select>
        </el-form-item>
        <el-form-item label="赛事">
          <el-select v-model="inboxQuery.contestId" clearable style="width: 180px">
            <el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="inboxQuery.priority" clearable style="width: 120px">
            <el-option label="低" value="low" />
            <el-option label="普通" value="normal" />
            <el-option label="高" value="high" />
            <el-option label="紧急" value="urgent" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="getList">筛选</el-button>
          <el-button :icon="Refresh" @click="resetInboxQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <div class="competition-summary-strip">
        <div v-for="item in metricCards" :key="item.title" class="competition-summary-chip">
          <div class="competition-summary-chip__label">{{ item.title }}</div>
          <div class="competition-summary-chip__value">{{ item.value }}</div>
          <div class="competition-summary-chip__desc">{{ item.desc }}</div>
        </div>
      </div>
    </el-card>

    <el-card class="competition-table-card" shadow="never">
      <template #header>
        <div class="competition-toolbar">
          <div class="competition-toolbar__left">
            <div>
              <div class="competition-panel__title">{{ pageTitle }}</div>
              <div class="competition-panel__desc">{{ pageSubtitle }}</div>
            </div>
          </div>
          <div class="competition-toolbar__right">
            <el-button v-if="canManage && activeTab === 'manage'" type="primary" plain :icon="Plus" @click="handleAdd">新增</el-button>
            <el-button v-if="canManage && activeTab === 'manage'" plain @click="openRulePanel">待办规则</el-button>
            <el-button v-if="canManage && activeTab === 'manage'" plain @click="openFailurePanel()">失败记录</el-button>
          </div>
        </div>
      </template>
      <div class="competition-empty-fix">
        <el-table v-loading="loading" :data="messageList" border row-key="id">
          <el-table-column label="标题" min-width="220" show-overflow-tooltip>
            <template #default="scope">
              <el-button link type="primary" @click="handlePreview(scope.row)">{{ scope.row.title }}</el-button>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100"><template #default="scope"><el-tag>{{ messageTypeLabel(scope.row.messageType) }}</el-tag></template></el-table-column>
          <el-table-column label="赛事" prop="contestName" min-width="140" />
          <el-table-column v-if="activeTab === 'manage'" label="触达范围" min-width="180">
            <template #default="scope">{{ audienceLabel(scope.row) }}</template>
          </el-table-column>
          <el-table-column label="优先级" width="100"><template #default="scope"><el-tag :type="['high', 'urgent'].includes(scope.row.priority) ? 'danger' : 'info'">{{ priorityLabel(scope.row.priority) }}</el-tag></template></el-table-column>
          <el-table-column v-if="activeTab === 'manage'" label="发送状态" width="120"><template #default="scope"><competition-status-tag :value="scope.row.sendStatus" /></template></el-table-column>
          <el-table-column v-if="activeTab === 'manage'" label="失败记录" width="120">
            <template #default="scope">
              <el-button v-if="scope.row.failureCount" link type="danger" @click="openFailurePanel(scope.row.id)">{{ scope.row.failureCount }} 条</el-button>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column v-if="activeTab === 'manage'" label="计划发送" min-width="160" show-overflow-tooltip>
            <template #default="scope">{{ formatDateTime(scope.row.plannedSendAt, { fallback: '未设置' }) }}</template>
          </el-table-column>
          <el-table-column v-if="activeTab === 'inbox'" label="接收时间" min-width="160" show-overflow-tooltip>
            <template #default="scope">{{ formatDateTime(scope.row.createdAt, { fallback: '未记录' }) }}</template>
          </el-table-column>
          <el-table-column v-if="activeTab === 'inbox'" label="已读" width="100"><template #default="scope"><el-tag :type="scope.row.readStatus ? 'success' : 'info'">{{ scope.row.readStatus ? '已读' : '未读' }}</el-tag></template></el-table-column>
          <el-table-column label="操作" min-width="240" fixed="right">
            <template #default="scope">
              <div class="competition-row-actions">
                <el-button link type="primary" :icon="View" @click="handlePreview(scope.row)">查看</el-button>
                <el-button v-if="activeTab === 'manage' && scope.row.permissions?.canEdit" link type="primary" :icon="EditPen" @click="handleEdit(scope.row)">编辑</el-button>
                <el-button v-if="activeTab === 'manage' && scope.row.permissions?.canSend" link type="success" @click="handleSend(scope.row)">发送</el-button>
                <el-button v-if="activeTab === 'manage' && scope.row.permissions?.canCancel" link type="warning" @click="handleCancel(scope.row)">取消</el-button>
                <el-button v-if="activeTab === 'manage' && scope.row.failureCount" link type="danger" @click="openFailurePanel(scope.row.id)">失败记录</el-button>
                <el-button v-if="activeTab === 'inbox' && scope.row.permissions?.canRead" link type="primary" @click="handleRead(scope.row)">标记已读</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="competition-pagination">
        <pagination v-show="total > 0" :total="total" v-model:page="currentQuery.pageNum" v-model:limit="currentQuery.pageSize" @pagination="getList" />
      </div>
    </el-card>

    <el-dialog v-model="open" :title="dialogTitle" width="760px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="标题" prop="title"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="摘要"><el-input v-model="form.summary" /></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="类型" prop="messageType"><el-select v-model="form.messageType" style="width: 100%"><el-option label="公告" value="notice" /><el-option label="提醒" value="todo" /><el-option label="通知" value="message" /></el-select></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item label="范围">
              <el-select v-model="form.targetScope" style="width: 100%" @change="handleScopeChange">
                <el-option v-for="item in scopeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12"><el-form-item label="关联赛事"><el-select v-model="form.contestId" clearable style="width: 100%"><el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" /></el-select></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item label="目标角色">
              <el-select
                v-model="form.targetRoles"
                clearable
                filterable
                multiple
                collapse-tags
                collapse-tags-tooltip
                placeholder="可多选，不选表示全部角色"
                style="width: 100%"
              >
                <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12"><el-form-item label="目标状态"><el-input v-model="form.targetStatus" placeholder="如 approved" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="优先级" prop="priority"><el-select v-model="form.priority" style="width: 100%"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="计划发送"><el-date-picker v-model="form.plannedSendAt" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="内容" prop="content"><el-input v-model="form.content" type="textarea" :rows="6" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="open = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="ruleOpen" title="待办规则" size="min(860px, 100vw)">
      <div class="competition-detail-drawer">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="待办规则会按报名状态生成提醒消息。当前版本支持“未提交原件”和“补正未完成”两类规则。"
        />
        <el-form :model="ruleQuery" :inline="true" class="competition-filter-form" style="margin-top: 16px;">
          <el-form-item label="关键字"><el-input v-model="ruleQuery.keyword" placeholder="规则名称" clearable @keyup.enter="getTodoRuleList" /></el-form-item>
          <el-form-item label="场景">
            <el-select v-model="ruleQuery.scene" clearable style="width: 180px">
              <el-option v-for="item in todoSceneOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="ruleQuery.enabledStatus" clearable style="width: 140px">
              <el-option label="启用" value="true" />
              <el-option label="停用" value="false" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="getTodoRuleList">筛选</el-button>
            <el-button @click="resetRuleQuery">重置</el-button>
          </el-form-item>
        </el-form>
        <div class="competition-toolbar" style="margin-bottom: 12px;">
          <div class="competition-toolbar__left">
            <div>
              <div class="competition-panel__title">规则列表</div>
              <div class="competition-panel__desc">共 {{ ruleTotal }} 条规则</div>
            </div>
          </div>
          <div class="competition-toolbar__right">
            <el-button type="primary" @click="handleAddRule">新建规则</el-button>
            <el-button plain @click="getTodoRuleList">刷新规则</el-button>
          </div>
        </div>
        <el-table v-loading="ruleLoading" :data="todoRuleList" border row-key="id">
          <el-table-column label="规则名称" prop="ruleName" min-width="180" show-overflow-tooltip />
          <el-table-column label="场景" min-width="160">
            <template #default="scope">{{ todoSceneLabel(scope.row.scene) }}</template>
          </el-table-column>
          <el-table-column label="关联赛事" prop="contestName" min-width="160" show-overflow-tooltip />
          <el-table-column label="目标角色" min-width="140">
            <template #default="scope">{{ roleNames(scope.row.targetRoles?.length ? scope.row.targetRoles : scope.row.targetRole) }}</template>
          </el-table-column>
          <el-table-column label="优先级" width="100">
            <template #default="scope"><el-tag :type="priorityTagType(scope.row.priority)">{{ priorityLabel(scope.row.priority) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="启用" width="90">
            <template #default="scope">
              <el-switch
                :model-value="Boolean(Number(scope.row.enabledStatus))"
                @change="value => handleRuleEnabledChange(scope.row, value)"
              />
            </template>
          </el-table-column>
          <el-table-column label="最近执行" min-width="160">
            <template #default="scope">{{ formatDateTime(scope.row.lastRunAt, { fallback: '未执行' }) }}</template>
          </el-table-column>
          <el-table-column label="最近生成" width="100">
            <template #default="scope">{{ scope.row.lastGeneratedCount || 0 }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="200" fixed="right">
            <template #default="scope">
              <div class="competition-row-actions">
                <el-button link type="primary" @click="handleEditRule(scope.row)">编辑</el-button>
                <el-button link type="success" :loading="applyingRuleId === scope.row.id" :disabled="!scope.row.permissions?.canApply" @click="handleApplyRule(scope.row)">立即执行</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div class="competition-pagination">
          <pagination v-show="ruleTotal > 0" :total="ruleTotal" v-model:page="ruleQuery.pageNum" v-model:limit="ruleQuery.pageSize" @pagination="getTodoRuleList" />
        </div>
      </div>
    </el-drawer>

    <el-dialog v-model="ruleEditOpen" :title="ruleDialogTitle" width="760px" destroy-on-close>
      <el-form ref="ruleFormRef" :model="ruleForm" :rules="ruleFormRules" label-width="110px">
        <el-form-item label="规则名称" prop="ruleName"><el-input v-model="ruleForm.ruleName" placeholder="例如：报名原件催交" /></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="规则场景" prop="scene">
              <el-select v-model="ruleForm.scene" style="width: 100%">
                <el-option v-for="item in todoSceneOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12"><el-form-item label="关联赛事"><el-select v-model="ruleForm.contestId" clearable style="width: 100%"><el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" /></el-select></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item label="目标角色">
              <el-select v-model="ruleForm.targetRoles" multiple collapse-tags collapse-tags-tooltip style="width: 100%">
                <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12"><el-form-item label="优先级" prop="priority"><el-select v-model="ruleForm.priority" style="width: 100%"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="启用规则"><el-switch v-model="ruleForm.enabledStatus" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="标题模板"><el-input v-model="ruleForm.titleTemplate" placeholder="可用变量：{contestName} {studentName} {projectName}" /></el-form-item>
        <el-form-item label="摘要模板"><el-input v-model="ruleForm.summaryTemplate" placeholder="为空时使用系统默认摘要" /></el-form-item>
        <el-form-item label="正文模板"><el-input v-model="ruleForm.contentTemplate" type="textarea" :rows="5" placeholder="可用变量：{contestName} {studentName} {projectName} {status} {latestComment}" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleEditOpen = false">取消</el-button>
        <el-button type="primary" :loading="ruleSubmitting" @click="submitRuleForm">保存规则</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="failureOpen" title="发送失败记录" size="min(860px, 100vw)">
      <div class="competition-detail-drawer">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="这里展示发送时没有匹配到接收对象的记录，用来排查范围、赛事权限和目标角色配置。"
        />
        <el-form :model="failureQuery" :inline="true" class="competition-filter-form" style="margin-top: 16px;">
          <el-form-item label="关键字"><el-input v-model="failureQuery.keyword" placeholder="消息标题/失败原因" clearable @keyup.enter="getFailureList" /></el-form-item>
          <el-form-item label="角色">
            <el-select v-model="failureQuery.roleCode" clearable style="width: 140px">
              <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="getFailureList">筛选</el-button>
            <el-button @click="resetFailureQuery">重置</el-button>
          </el-form-item>
        </el-form>
        <div class="competition-toolbar" style="margin-bottom: 12px;">
          <div class="competition-toolbar__left">
            <div>
              <div class="competition-panel__title">失败记录</div>
              <div class="competition-panel__desc">共 {{ failureTotal }} 条记录</div>
            </div>
          </div>
          <div class="competition-toolbar__right">
            <el-button plain @click="getFailureList">刷新记录</el-button>
          </div>
        </div>
        <el-table v-loading="failureLoading" :data="failureList" border row-key="id">
          <el-table-column label="消息标题" prop="messageTitle" min-width="220" show-overflow-tooltip />
          <el-table-column label="角色" width="120">
            <template #default="scope">{{ scope.row.roleCode ? roleLabel(scope.row.roleCode) : '通用' }}</template>
          </el-table-column>
          <el-table-column label="关联赛事" prop="contestName" min-width="160" show-overflow-tooltip />
          <el-table-column label="失败原因" prop="reason" min-width="180" show-overflow-tooltip />
          <el-table-column label="明细" prop="detail" min-width="220" show-overflow-tooltip />
          <el-table-column label="消息状态" width="120">
            <template #default="scope"><competition-status-tag :value="scope.row.messageStatus" /></template>
          </el-table-column>
          <el-table-column label="记录时间" min-width="160">
            <template #default="scope">{{ formatDateTime(scope.row.createdAt, { fallback: '未记录' }) }}</template>
          </el-table-column>
        </el-table>
        <div class="competition-pagination">
          <pagination v-show="failureTotal > 0" :total="failureTotal" v-model:page="failureQuery.pageNum" v-model:limit="failureQuery.pageSize" @pagination="getFailureList" />
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="detailOpen" class="message-detail-drawer" size="min(560px, 100vw)">
      <template #header>
        <div class="message-detail-header">
          <div class="message-detail-header__eyebrow">{{ activeTab === 'manage' ? '通知详情' : '消息详情' }}</div>
          <div class="message-detail-header__title">{{ activeMessage.title || '未命名消息' }}</div>
          <div class="message-detail-header__subtitle">{{ detailHeaderSubtitle }}</div>
          <div class="message-detail-header__tags">
            <el-tag :type="messageTypeTagType(activeMessage.messageType)">{{ messageTypeLabel(activeMessage.messageType) }}</el-tag>
            <el-tag :type="priorityTagType(activeMessage.priority)">{{ priorityLabel(activeMessage.priority) }}</el-tag>
            <competition-status-tag v-if="activeTab === 'manage'" :value="activeMessage.sendStatus" />
            <el-tag v-else :type="activeMessage.readStatus ? 'success' : 'warning'">{{ readStatusLabel(activeMessage.readStatus) }}</el-tag>
          </div>
        </div>
      </template>

      <div class="message-detail">
        <section class="message-detail-callout" :class="`is-${detailAction.tone}`">
          <div class="message-detail-callout__copy">
            <div class="message-detail-callout__eyebrow">{{ detailAction.eyebrow }}</div>
            <div class="message-detail-callout__title">{{ detailAction.title }}</div>
            <div class="message-detail-callout__desc">{{ detailAction.desc }}</div>
          </div>
          <div class="message-detail-callout__actions">
            <el-button v-if="activeTab === 'manage' && activeMessage.permissions?.canEdit" type="primary" plain @click="handleEdit(activeMessage)">编辑</el-button>
            <el-button v-if="activeTab === 'manage' && activeMessage.permissions?.canSend" type="success" @click="handleSend(activeMessage)">发送</el-button>
            <el-button v-if="activeTab === 'manage' && activeMessage.permissions?.canCancel" type="warning" plain @click="handleCancel(activeMessage)">取消</el-button>
            <el-button v-if="activeTab === 'manage' && activeMessage.failureCount" type="danger" plain @click="openFailurePanel(activeMessage.id)">失败记录</el-button>
            <el-button v-if="activeTab === 'inbox' && activeMessage.permissions?.canRead" type="primary" @click="handleRead(activeMessage)">标记已读</el-button>
          </div>
        </section>

        <section class="message-detail-panel">
          <div class="message-detail-panel__head">
            <div>
              <div class="message-detail-panel__title">关键信息</div>
              <div class="message-detail-panel__desc">先判断这条消息和你有什么关系。</div>
            </div>
          </div>
          <div class="message-detail-overview">
            <div v-for="item in detailOverview" :key="item.label" class="message-detail-overview__item">
              <div class="message-detail-overview__label">{{ item.label }}</div>
              <div class="message-detail-overview__value">{{ item.value }}</div>
            </div>
          </div>
        </section>

        <section class="message-detail-panel">
          <div class="message-detail-panel__head">
            <div>
              <div class="message-detail-panel__title">{{ activeTab === 'manage' ? '列表摘要' : '先看重点' }}</div>
              <div class="message-detail-panel__desc">
                {{ activeTab === 'manage' ? '接收方打开前，通常会先扫到这段摘要。' : '先读这段，再决定是否需要立刻处理。' }}
              </div>
            </div>
          </div>
          <div class="message-detail-emphasis">{{ detailSummaryText }}</div>
        </section>

        <section class="message-detail-panel">
          <div class="message-detail-panel__head">
            <div>
              <div class="message-detail-panel__title">完整内容</div>
              <div class="message-detail-panel__desc">
                {{ activeTab === 'manage' ? '发送前请确认正文中的动作、对象和时间都说清楚。' : '需要执行的事项以正文说明为准。' }}
              </div>
            </div>
          </div>
          <div class="competition-detail-text">{{ activeMessage.content || '无内容' }}</div>
        </section>

        <section class="message-detail-panel">
          <div class="message-detail-panel__head">
            <div>
              <div class="message-detail-panel__title">时间节点</div>
              <div class="message-detail-panel__desc">
                {{ activeTab === 'manage' ? '从创建到发送计划，再到阅读反馈。' : '先确认什么时候收到，是否已经读过。' }}
              </div>
            </div>
          </div>
          <el-timeline class="message-detail-native-timeline">
            <el-timeline-item
              v-for="item in detailTimeline"
              :key="item.label"
              :timestamp="item.desc"
              placement="top"
              size="large"
              :type="item.type"
              :hollow="item.hollow"
            >
              <div class="message-detail-timeline-card">
                <div class="message-detail-timeline-card__label">{{ item.label }}</div>
                <div class="message-detail-timeline-card__value">{{ item.value }}</div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.message-detail-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 0;
}

.message-detail-drawer :deep(.el-drawer__body) {
  padding: 18px 20px 20px;
  background: linear-gradient(180deg, #f7fafc 0%, #ffffff 180px);
}

.message-detail-header {
  padding: 22px 20px 18px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background:
    radial-gradient(circle at top right, rgba(64, 158, 255, 0.14), transparent 38%),
    linear-gradient(135deg, #ffffff, #f5f9ff);
}

.message-detail-header__eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--el-color-primary);
}

.message-detail-header__title {
  margin-top: 10px;
  font-size: 24px;
  line-height: 1.35;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.message-detail-header__subtitle {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.message-detail-header__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.message-detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.message-detail-callout,
.message-detail-panel {
  border-radius: 18px;
  border: 1px solid var(--el-border-color-lighter);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
}

.message-detail-callout {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
}

.message-detail-callout.is-primary {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.12), rgba(255, 255, 255, 0.96));
}

.message-detail-callout.is-success {
  background: linear-gradient(135deg, rgba(103, 194, 58, 0.12), rgba(255, 255, 255, 0.96));
}

.message-detail-callout.is-warning {
  background: linear-gradient(135deg, rgba(230, 162, 60, 0.14), rgba(255, 255, 255, 0.96));
}

.message-detail-callout.is-danger {
  background: linear-gradient(135deg, rgba(245, 108, 108, 0.14), rgba(255, 255, 255, 0.96));
}

.message-detail-callout.is-info {
  background: linear-gradient(135deg, rgba(144, 147, 153, 0.12), rgba(255, 255, 255, 0.96));
}

.message-detail-callout__copy {
  min-width: 0;
}

.message-detail-callout__eyebrow {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.message-detail-callout__title {
  margin-top: 8px;
  font-size: 20px;
  line-height: 1.4;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.message-detail-callout__desc {
  margin-top: 8px;
  font-size: 14px;
  line-height: 1.75;
  color: var(--el-text-color-regular);
}

.message-detail-callout__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  min-width: 120px;
}

.message-detail-panel {
  padding: 18px;
}

.message-detail-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.message-detail-panel__title {
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.message-detail-panel__desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.message-detail-overview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.message-detail-overview__item {
  padding: 14px;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff, #f6f8fb);
  border: 1px solid var(--el-border-color-extra-light);
}

.message-detail-overview__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.message-detail-overview__value {
  margin-top: 8px;
  font-size: 15px;
  line-height: 1.65;
  font-weight: 600;
  color: var(--el-text-color-primary);
  word-break: break-word;
}

.message-detail-emphasis {
  margin-top: 14px;
  padding: 16px;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.08), rgba(255, 255, 255, 0.96));
  border: 1px solid rgba(64, 158, 255, 0.14);
  font-size: 14px;
  line-height: 1.85;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
}

.message-detail-native-timeline {
  margin-top: 14px;
  padding-left: 2px;
}

.message-detail-native-timeline :deep(.el-timeline-item__wrapper) {
  padding-left: 24px;
}

.message-detail-native-timeline :deep(.el-timeline-item__timestamp) {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.message-detail-native-timeline :deep(.el-timeline-item__tail) {
  border-left-color: rgba(64, 158, 255, 0.16);
}

.message-detail-timeline-card {
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--el-border-color-extra-light);
  background: linear-gradient(180deg, #ffffff, #f8fbff);
}

.message-detail-timeline-card__label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.message-detail-timeline-card__value {
  margin-top: 8px;
  font-size: 14px;
  line-height: 1.7;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

@media (max-width: 900px) {
  .message-detail-overview {
    grid-template-columns: 1fr;
  }

  .message-detail-callout {
    flex-direction: column;
  }

  .message-detail-callout__actions {
    justify-content: flex-start;
    min-width: 0;
  }
}
</style>
