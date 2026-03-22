<script setup>
import {
  CircleCheck,
  Collection,
  Document,
  Download,
  FolderOpened,
  Plus,
  Refresh,
  Search,
  Setting,
  Timer,
  Upload,
  View,
  Warning,
} from '@element-plus/icons-vue'
import { computed, getCurrentInstance, onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'

import {
  addDeliveryChannel,
  addFileExportPolicy,
  beginDeliveryChannelOauth,
  deleteDeliveryChannel,
  deleteFileExportPolicy,
  getDeliveryChannel,
  getFileCategories,
  getFileExportBatch,
  getFileExportMetadata,
  getFileExportPolicy,
  listDeliveryChannels,
  listFileExportBatches,
  listFileExportPolicies,
  listFiles,
  retryFileExportBatch,
  runDueFileExportPolicies,
  runFileExportPolicy,
  updateDeliveryChannel,
  updateFileExportPolicy,
  validateDeliveryChannel,
} from '@/api/competition/file'
import { listContests } from '@/api/competition/contest'
import CompetitionFilePreviewDialog from '@/components/CompetitionFilePreviewDialog.vue'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import useUserStore from '@/store/modules/user'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const { proxy } = getCurrentInstance()
const userStore = useUserStore()

const activeTab = ref('overview')
const loading = ref(false)
const categoryLoading = ref(false)
const total = ref(0)
const contestOptions = ref([])
const fileRows = ref([])
const categoryTree = ref({ id: 'all', label: '全部文件（0）', count: 0, children: [] })
const categorySummary = ref({ totalFiles: 0, totalSize: 0, categoryCount: 0, exportCount: 0 })
const listSummary = ref({ totalFiles: 0, totalSize: 0, categoryCount: 0, exportCount: 0 })
const selectedCategoryId = ref('all')
const previewRef = ref()

const metadataLoading = ref(false)
const exportMetadata = ref({
  categoryOptions: [],
  contestOptions: [],
  collegeOptions: [],
  channelOptions: [],
  templateVariables: [],
})

const policyLoading = ref(false)
const policyRows = ref([])
const policyTotal = ref(0)
const savingPolicy = ref(false)
const runningPolicyId = ref(0)
const scanningDueRules = ref(false)
const policyDialogVisible = ref(false)

const batchLoading = ref(false)
const batchRows = ref([])
const batchTotal = ref(0)
const downloadingBatchId = ref(0)
const retryingBatchId = ref(0)
const batchDetailVisible = ref(false)
const batchDetailLoading = ref(false)
const batchDetail = ref({ manifest: { entries: [] }, deliveries: [] })

const channelLoading = ref(false)
const channelRows = ref([])
const channelTotal = ref(0)
const savingChannel = ref(false)
const validatingChannelId = ref(0)
const authorizingChannelId = ref(0)
const channelDialogVisible = ref(false)

const queryParams = reactive({
  keyword: '',
  contestId: undefined,
  pageNum: 1,
  pageSize: 10,
})

const policyQuery = reactive({
  keyword: '',
  status: '',
  scheduleType: '',
  pageNum: 1,
  pageSize: 10,
})

const batchQuery = reactive({
  keyword: '',
  status: '',
  policyId: undefined,
  pageNum: 1,
  pageSize: 10,
})

const channelQuery = reactive({
  keyword: '',
  status: '',
  channelType: '',
  pageNum: 1,
  pageSize: 10,
})

function defaultPolicyForm() {
  return {
    id: undefined,
    policyName: '',
    status: 'enabled',
    scheduleType: 'daily',
    scheduleTime: '02:00',
    incrementMode: 'full',
    scope: {
      categoryCodes: ['registration_material', 'certificate'],
      contestIds: [],
      collegeNames: [],
      keyword: '',
    },
    folderTemplate: '{categoryName}/{contestName}/{college}/{date}',
    fileNameTemplate: '{policyName}_{date}_{batchNo}.zip',
    includeManifest: true,
    deliveryChannelIds: [],
    remark: '',
  }
}

function defaultChannelForm() {
  return {
    id: undefined,
    channelName: '',
    channelType: 'local_folder',
    status: 'enabled',
    config: {
      rootPath: 'exports/deliveries',
      folderTemplate: '{policyName}/{date}',
      mockMode: false,
      mockRoot: 'mock_baidu_pan',
      accessToken: '',
      accessTokenMasked: '',
      refreshTokenMasked: '',
      authorizedAt: '',
      tokenExpiresAt: '',
      scope: '',
      authMode: '',
      oauthStatus: '',
      callbackUrl: '',
      conflictMode: 'overwrite',
    },
    remark: '',
  }
}

const policyForm = reactive(defaultPolicyForm())
const channelForm = reactive(defaultChannelForm())

const canManageExports = computed(() => Boolean(userStore.capabilities.manageFileExports))
const canViewBatches = computed(() => Boolean(userStore.capabilities.viewFileExportBatches))
const canManageChannels = computed(() => Boolean(userStore.capabilities.manageDeliveryChannels))
const visibleTabs = computed(() => {
  const items = [{ name: 'overview', label: '文件总览' }]
  if (canManageExports.value) items.push({ name: 'rules', label: '导出规则' })
  if (canViewBatches.value) items.push({ name: 'batches', label: '导出批次' })
  if (canManageChannels.value) items.push({ name: 'channels', label: '投递渠道' })
  return items
})

const selectedCategoryLabel = computed(() => findCategoryLabel(categoryTree.value, selectedCategoryId.value) || '全部文件')
const enabledChannelOptions = computed(() => (exportMetadata.value.channelOptions || []).filter(item => item.status === 'enabled'))
const metricCards = computed(() => ([
  { title: '当前结果', value: total.value, desc: '按当前筛选条件返回的文件数', icon: FolderOpened },
  { title: '文件总量', value: categorySummary.value.totalFiles || 0, desc: '当前账号在文件中心可见的全部文件', icon: Collection },
  { title: '分类数', value: categorySummary.value.categoryCount || 0, desc: '当前已出现数据的文件分类数量', icon: Search },
  { title: '导出产物', value: categorySummary.value.exportCount || 0, desc: '统计导出、归档包和自动批次产物', icon: Download },
]))

const pageTitle = computed(() => {
  if (activeTab.value === 'rules') return '按规则每天生成归档批次，目录模板和投递渠道都在这里配置。'
  if (activeTab.value === 'batches') return '查看每次自动或手工导出的批次、清单和投递结果。'
  if (activeTab.value === 'channels') return '管理本地目录和百度网盘投递渠道，统一给规则复用。'
  return '统一查看规则附件、报名材料、证书文件、导出产物和系统备份。'
})

const pageGuide = computed(() => {
  if (activeTab.value === 'rules') {
    return {
      eyebrow: 'Export Policies',
      title: '先定义导出范围，再决定目录模板和投递渠道',
      desc: '规则会按当前账号的数据权限生效。每日规则会自动进入调度扫描，手工执行则立即生成批次。',
      steps: [
        { step: '1', title: '先选范围', desc: '按文件分类、赛事、学院或关键字缩小导出范围。' },
        { step: '2', title: '再设模板', desc: '用目录模板和文件名模板控制归档结构，不再写死后端映射。' },
        { step: '3', title: '最后绑渠道', desc: '一个规则可以复用多个投递渠道，生成后统一回写状态。' },
      ],
    }
  }
  if (activeTab.value === 'batches') {
    return {
      eyebrow: 'Export Batches',
      title: '批次页看结果，详情页看清单和投递日志',
      desc: '自动导出、手工导出、失败重试都会落成批次记录。完成后可直接下载 ZIP 归档包。',
      steps: [
        { step: '1', title: '先看批次状态', desc: '处理中会更新进度，失败和部分成功会保留原因。' },
        { step: '2', title: '再看清单详情', desc: '详情里能看到每个文件最终被整理到哪个目录。' },
        { step: '3', title: '最后下载或重试', desc: '包已生成就能下载，渠道失败可以直接重试整个批次。' },
      ],
    }
  }
  if (activeTab.value === 'channels') {
    return {
      eyebrow: 'Delivery Channels',
      title: '把渠道先配稳，再交给规则复用',
      desc: '本地目录会直接复制归档包；百度网盘支持 OAuth 授权、mock 落地和 accessToken 兼容模式，并回写投递结果。',
      steps: [
        { step: '1', title: '先配根目录', desc: '本地目录和网盘根目录都在渠道里统一配置。' },
        { step: '2', title: '再校验渠道', desc: '创建后先校验一次，避免规则运行时才发现路径或凭证错误。' },
        { step: '3', title: '最后在规则里引用', desc: '渠道启用后就能在导出规则里反复复用。' },
      ],
    }
  }
  return {
    eyebrow: 'File Center',
    title: '先选分类，再按赛事和关键字缩小范围',
    desc: `当前聚合的是平台附件、任务产物和系统备份。选中“${selectedCategoryLabel.value}”后，右侧列表会按当前条件即时刷新。`,
    steps: [
      { step: '1', title: '先确定分类', desc: '左侧分类树已经按业务类别分层整理，先选定查找范围。' },
      { step: '2', title: '再补赛事或关键字', desc: '用赛事、学生、学院、文件名等关键词继续缩小结果。' },
      { step: '3', title: '最后预览或下载', desc: '支持在线预览的文件直接打开，其余文件走原件下载。' },
    ],
  }
})

const pageScopeNote = computed(() => {
  if (activeTab.value === 'rules') return '注意：导出规则不会绕开现有权限，教师只能导出自己有权查看的赛事与学院范围。'
  if (activeTab.value === 'batches') return '注意：批次详情里的目录清单就是最终归档结构，渠道失败不会影响平台内归档包生成。'
  if (activeTab.value === 'channels') return '注意：百度网盘建议作为投递渠道而不是主存储。真实环境优先走 OAuth 授权，手工 Access Token 只保留兼容模式。'
  return '注意：文件中心只做聚合查看和取件，不在这里改业务数据。备份包仅系统管理员可见。'
})

const guideActions = computed(() => {
  if (activeTab.value === 'rules' && canManageExports.value) {
    return [
      { key: 'createRule', label: '新增规则', type: 'primary', plain: false },
      { key: 'scanDue', label: '扫描到期规则', type: 'warning' },
    ]
  }
  if (activeTab.value === 'channels' && canManageChannels.value) {
    return [
      { key: 'createChannel', label: '新增渠道', type: 'primary', plain: false },
      { key: 'refresh', label: '刷新', type: 'info' },
    ]
  }
  return [{ key: 'refresh', label: '刷新', type: 'primary', plain: false }]
})

const policyStatusMap = {
  enabled: { label: '启用', type: 'success' },
  disabled: { label: '停用', type: 'info' },
}
const batchStatusMap = {
  pending: { label: '排队中', type: 'info' },
  processing: { label: '处理中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  partial_success: { label: '部分成功', type: 'warning' },
  failed: { label: '失败', type: 'danger' },
}
const deliveryStatusMap = {
  pending: { label: '待投递', type: 'info' },
  processing: { label: '投递中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}
const channelTypeMap = {
  local_folder: '本地目录',
  baidu_pan: '百度网盘',
}

function findCategoryLabel(node, targetId) {
  if (!node) return ''
  if (node.id === targetId) {
    return String(node.label || '').replace(/（\d+）$/, '')
  }
  for (const child of node.children || []) {
    const label = findCategoryLabel(child, targetId)
    if (label) return label
  }
  return ''
}

function formatDateTime(value, fallback = '未记录') {
  return formatBeijingDateTime(value, { fallback, withTime: true, withSeconds: false })
}

function formatFileSize(value) {
  const size = Number(value || 0)
  if (!size) return '大小未记录'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size >= 10 * 1024 ? 0 : 1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(size >= 10 * 1024 * 1024 ? 0 : 1)} MB`
  return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function statusMeta(map, key) {
  return map[key] || { label: key || '未知', type: 'info' }
}

function policyScopeLabel(row) {
  const scope = row.scope || {}
  const parts = []
  if (scope.categoryCodes?.length) parts.push(`分类 ${scope.categoryCodes.length} 项`)
  if (scope.contestIds?.length) parts.push(`赛事 ${scope.contestIds.length} 项`)
  if (scope.collegeNames?.length) parts.push(`学院 ${scope.collegeNames.length} 项`)
  if (scope.keyword) parts.push(`关键字 ${scope.keyword}`)
  return parts.length ? parts.join(' / ') : '全部可见文件'
}

function batchDeliveryLabel(row) {
  const summary = row.deliverySummary || {}
  if (!summary.total) return '未配置渠道'
  return `总 ${summary.total} / 成功 ${summary.completed || 0} / 失败 ${summary.failed || 0}`
}

function resetPolicyForm() {
  Object.assign(policyForm, defaultPolicyForm())
}

function resetChannelForm() {
  Object.assign(channelForm, defaultChannelForm())
}

async function loadContests() {
  const res = await listContests({ pageSize: 200 })
  contestOptions.value = res.data?.list || []
}

async function loadExportMetadata() {
  if (!canManageExports.value && !canManageChannels.value) return
  metadataLoading.value = true
  try {
    const res = await getFileExportMetadata()
    exportMetadata.value = res.data || { categoryOptions: [], contestOptions: [], collegeOptions: [], channelOptions: [], templateVariables: [] }
  } finally {
    metadataLoading.value = false
  }
}

async function loadCategories() {
  categoryLoading.value = true
  try {
    const res = await getFileCategories()
    const nextTree = res.data?.tree || { id: 'all', label: '全部文件（0）', count: 0, children: [] }
    categoryTree.value = nextTree
    if (selectedCategoryId.value !== 'all' && !findCategoryLabel(nextTree, selectedCategoryId.value)) {
      selectedCategoryId.value = 'all'
    }
    categorySummary.value = res.data?.summary || { totalFiles: 0, totalSize: 0, categoryCount: 0, exportCount: 0 }
  } finally {
    categoryLoading.value = false
  }
}

async function getList() {
  loading.value = true
  try {
    const res = await listFiles({
      ...queryParams,
      categoryCode: selectedCategoryId.value,
    })
    fileRows.value = res.data?.list || []
    total.value = res.data?.total || 0
    listSummary.value = res.data?.summary || { totalFiles: 0, totalSize: 0, categoryCount: 0, exportCount: 0 }
  } finally {
    loading.value = false
  }
}

async function loadPolicies() {
  if (!canManageExports.value) return
  policyLoading.value = true
  try {
    const res = await listFileExportPolicies(policyQuery)
    policyRows.value = res.data?.list || []
    policyTotal.value = res.data?.total || 0
  } finally {
    policyLoading.value = false
  }
}

async function loadBatches() {
  if (!canViewBatches.value) return
  batchLoading.value = true
  try {
    const res = await listFileExportBatches(batchQuery)
    batchRows.value = res.data?.list || []
    batchTotal.value = res.data?.total || 0
  } finally {
    batchLoading.value = false
  }
}

async function loadChannels() {
  if (!canManageChannels.value) return
  channelLoading.value = true
  try {
    const res = await listDeliveryChannels(channelQuery)
    channelRows.value = res.data?.list || []
    channelTotal.value = res.data?.total || 0
  } finally {
    channelLoading.value = false
  }
}

async function reloadOverview() {
  await Promise.all([loadCategories(), getList()])
}

async function reloadAll() {
  await Promise.all([
    loadContests(),
    reloadOverview(),
    loadExportMetadata(),
    loadPolicies(),
    loadBatches(),
    loadChannels(),
  ])
}

function resetQuery() {
  queryParams.keyword = ''
  queryParams.contestId = undefined
  queryParams.pageNum = 1
  getList()
}

function resetPolicyQuery() {
  policyQuery.keyword = ''
  policyQuery.status = ''
  policyQuery.scheduleType = ''
  policyQuery.pageNum = 1
  loadPolicies()
}

function resetBatchQuery() {
  batchQuery.keyword = ''
  batchQuery.status = ''
  batchQuery.policyId = undefined
  batchQuery.pageNum = 1
  loadBatches()
}

function resetChannelQuery() {
  channelQuery.keyword = ''
  channelQuery.status = ''
  channelQuery.channelType = ''
  channelQuery.pageNum = 1
  loadChannels()
}

function handleNodeClick(node) {
  selectedCategoryId.value = node.id || 'all'
  queryParams.pageNum = 1
  getList()
}

function handlePreview(row) {
  if (!row.previewable) {
    proxy.$modal.msgWarning('当前文件不支持在线预览，请直接下载原件')
    return
  }
  previewRef.value?.open({
    url: '/api/v1/files/preview',
    params: { assetType: row.assetType, assetId: row.assetId },
    fileName: row.fileName,
  })
}

function handleDownload(row) {
  proxy.download('/api/v1/files/download', { assetType: row.assetType, assetId: row.assetId }, row.fileName)
}

async function openPolicyDialog(row) {
  resetPolicyForm()
  if (row?.id) {
    const res = await getFileExportPolicy(row.id)
    const payload = res.data || {}
    Object.assign(policyForm, {
      id: payload.id,
      policyName: payload.policyName,
      status: payload.status,
      scheduleType: payload.scheduleType,
      scheduleTime: payload.scheduleTime || '02:00',
      incrementMode: payload.incrementMode,
      scope: {
        categoryCodes: payload.scope?.categoryCodes || [],
        contestIds: payload.scope?.contestIds || [],
        collegeNames: payload.scope?.collegeNames || [],
        keyword: payload.scope?.keyword || '',
      },
      folderTemplate: payload.folderTemplate,
      fileNameTemplate: payload.fileNameTemplate,
      includeManifest: payload.includeManifest,
      deliveryChannelIds: payload.deliveryChannelIds || [],
      remark: payload.remark || '',
    })
  }
  policyDialogVisible.value = true
}

async function submitPolicy() {
  const policyName = String(policyForm.policyName || '').trim()
  if (!policyName) {
    proxy.$modal.msgError('规则名称不能为空')
    return
  }
  if (policyForm.scheduleType === 'daily' && !String(policyForm.scheduleTime || '').trim()) {
    proxy.$modal.msgError('每日执行规则必须配置执行时间')
    return
  }
  savingPolicy.value = true
  try {
    const payload = {
      policyName,
      status: policyForm.status,
      scheduleType: policyForm.scheduleType,
      scheduleTime: policyForm.scheduleTime,
      incrementMode: policyForm.incrementMode,
      scope: {
        categoryCodes: policyForm.scope.categoryCodes,
        contestIds: policyForm.scope.contestIds,
        collegeNames: policyForm.scope.collegeNames,
        keyword: policyForm.scope.keyword,
      },
      folderTemplate: policyForm.folderTemplate,
      fileNameTemplate: policyForm.fileNameTemplate,
      includeManifest: policyForm.includeManifest,
      deliveryChannelIds: policyForm.deliveryChannelIds,
      remark: policyForm.remark,
    }
    if (policyForm.id) {
      await updateFileExportPolicy(policyForm.id, payload)
      proxy.$modal.msgSuccess('导出规则更新成功')
    } else {
      await addFileExportPolicy(payload)
      proxy.$modal.msgSuccess('导出规则创建成功')
    }
    policyDialogVisible.value = false
    await Promise.all([loadPolicies(), loadBatches()])
  } finally {
    savingPolicy.value = false
  }
}

async function handleDeletePolicy(row) {
  await ElMessageBox.confirm(`确认删除规则“${row.policyName}”吗？`, '系统提示', { type: 'warning' })
  await deleteFileExportPolicy(row.id)
  proxy.$modal.msgSuccess('导出规则删除成功')
  await loadPolicies()
}

async function handleRunPolicy(row) {
  runningPolicyId.value = row.id
  try {
    await runFileExportPolicy(row.id)
    proxy.$modal.msgSuccess('导出批次已创建')
    activeTab.value = canViewBatches.value ? 'batches' : 'rules'
    await loadBatches()
  } finally {
    runningPolicyId.value = 0
  }
}

async function handleScanDuePolicies() {
  scanningDueRules.value = true
  try {
    const res = await runDueFileExportPolicies()
    proxy.$modal.msgSuccess(`到期规则扫描完成，本次创建 ${res.data?.count || 0} 个批次`)
    await Promise.all([loadPolicies(), loadBatches()])
  } finally {
    scanningDueRules.value = false
  }
}

async function openBatchDetail(row) {
  batchDetailLoading.value = true
  batchDetailVisible.value = true
  try {
    const res = await getFileExportBatch(row.id)
    batchDetail.value = res.data || { manifest: { entries: [] }, deliveries: [] }
  } finally {
    batchDetailLoading.value = false
  }
}

async function handleDownloadBatch(row) {
  downloadingBatchId.value = row.id
  try {
    await proxy.download(`/api/v1/files/export-batches/${row.id}/download`, {}, row.fileName || `${row.batchNo}.zip`)
  } finally {
    downloadingBatchId.value = 0
  }
}

async function handleRetryBatch(row) {
  retryingBatchId.value = row.id
  try {
    await retryFileExportBatch(row.id)
    proxy.$modal.msgSuccess('导出批次已重新提交')
    await loadBatches()
  } finally {
    retryingBatchId.value = 0
  }
}

async function openChannelDialog(row) {
  resetChannelForm()
  if (row?.id) {
    const res = await getDeliveryChannel(row.id)
    const payload = res.data || {}
    Object.assign(channelForm, {
      id: payload.id,
      channelName: payload.channelName,
      channelType: payload.channelType,
      status: payload.status,
      config: {
        rootPath: payload.config?.rootPath || '',
        folderTemplate: payload.config?.folderTemplate || '{policyName}/{date}',
        mockMode: Boolean(payload.config?.mockMode),
        mockRoot: payload.config?.mockRoot || 'mock_baidu_pan',
        accessToken: '',
        accessTokenMasked: payload.config?.accessTokenMasked || '',
        refreshTokenMasked: payload.config?.refreshTokenMasked || '',
        authorizedAt: payload.config?.authorizedAt || '',
        tokenExpiresAt: payload.config?.tokenExpiresAt || '',
        scope: payload.config?.scope || '',
        authMode: payload.config?.authMode || '',
        oauthStatus: payload.config?.oauthStatus || '',
        callbackUrl: payload.config?.callbackUrl || '',
        conflictMode: payload.config?.conflictMode || 'overwrite',
      },
      remark: payload.remark || '',
    })
  }
  channelDialogVisible.value = true
}

async function submitChannel() {
  savingChannel.value = true
  try {
    const payload = {
      channelName: channelForm.channelName,
      channelType: channelForm.channelType,
      status: channelForm.status,
      config: {
        rootPath: channelForm.config.rootPath,
        folderTemplate: channelForm.config.folderTemplate,
        mockMode: channelForm.config.mockMode,
        mockRoot: channelForm.config.mockRoot,
        accessToken: channelForm.config.accessToken,
        conflictMode: channelForm.config.conflictMode,
      },
      remark: channelForm.remark,
    }
    if (channelForm.id) {
      await updateDeliveryChannel(channelForm.id, payload)
      proxy.$modal.msgSuccess('投递渠道更新成功')
    } else {
      await addDeliveryChannel(payload)
      proxy.$modal.msgSuccess('投递渠道创建成功')
    }
    channelDialogVisible.value = false
    await Promise.all([loadChannels(), loadExportMetadata()])
  } finally {
    savingChannel.value = false
  }
}

async function handleAuthorizeChannel(row) {
  const target = row?.id ? row : (channelForm.id ? { id: channelForm.id, channelName: channelForm.channelName } : null)
  if (!target?.id) {
    proxy.$modal.msgWarning('请先保存渠道，再发起百度网盘授权')
    return
  }
  const authWindow = window.open('', 'baiduPanOauth', 'width=980,height=760')
  authorizingChannelId.value = target.id
  try {
    const res = await beginDeliveryChannelOauth(target.id)
    const authorizeUrl = res.data?.authorizeUrl
    if (!authorizeUrl) {
      throw new Error('未返回授权链接')
    }
    if (authWindow && !authWindow.closed) {
      authWindow.location.href = authorizeUrl
      authWindow.focus?.()
    } else {
      window.open(authorizeUrl, '_blank')
    }
    proxy.$modal.msgSuccess('授权页已打开，完成授权后回到本页刷新或校验渠道')
  } catch (error) {
    authWindow?.close?.()
    proxy.$modal.msgError(error?.message || '百度网盘授权链接生成失败')
  } finally {
    authorizingChannelId.value = 0
  }
}

async function handleDeleteChannel(row) {
  await ElMessageBox.confirm(`确认删除渠道“${row.channelName}”吗？`, '系统提示', { type: 'warning' })
  await deleteDeliveryChannel(row.id)
  proxy.$modal.msgSuccess('投递渠道删除成功')
  await Promise.all([loadChannels(), loadExportMetadata()])
}

async function handleValidateChannel(row) {
  validatingChannelId.value = row.id
  try {
    const res = await validateDeliveryChannel(row.id)
    proxy.$modal.msgSuccess(res.message || '渠道校验成功')
    await loadChannels()
  } finally {
    validatingChannelId.value = 0
  }
}

async function handleGuideAction(action) {
  if (action.key === 'createRule') {
    openPolicyDialog()
    return
  }
  if (action.key === 'scanDue') {
    await handleScanDuePolicies()
    return
  }
  if (action.key === 'createChannel') {
    openChannelDialog()
    return
  }
  if (activeTab.value === 'rules') {
    await Promise.all([loadPolicies(), loadBatches()])
    return
  }
  if (activeTab.value === 'batches') {
    await loadBatches()
    return
  }
  if (activeTab.value === 'channels') {
    await Promise.all([loadChannels(), loadExportMetadata()])
    return
  }
  await reloadOverview()
}

onMounted(async () => {
  if (!visibleTabs.value.some(item => item.name === activeTab.value)) {
    activeTab.value = visibleTabs.value[0]?.name || 'overview'
  }
  await reloadAll()
})
</script>

<template>
  <div class="competition-page">
    <el-card class="competition-control-card" shadow="never">
      <template #header>
        <div class="competition-control-head">
          <div class="competition-control-copy">
            <div class="competition-control-eyebrow">File Center</div>
            <div class="competition-control-title">文件中心</div>
            <div class="competition-control-subtitle">{{ pageTitle }}</div>
          </div>
          <div class="competition-control-actions">
            <el-button plain :icon="Refresh" @click="handleGuideAction({ key: 'refresh' })">刷新当前页</el-button>
          </div>
        </div>
      </template>

      <competition-guide-panel
        :note="pageScopeNote"
        :eyebrow="pageGuide.eyebrow"
        :title="pageGuide.title"
        :description="pageGuide.desc"
        :steps="pageGuide.steps"
        :actions="guideActions"
        @action="handleGuideAction"
      />

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
              <div class="competition-panel__title">平台文件与导出中心</div>
              <div class="competition-panel__desc">聚合文件查看、规则配置、批次追踪和投递渠道管理都收在同一个模块里。</div>
            </div>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <el-tab-pane v-for="item in visibleTabs" :key="item.name" :label="item.label" :name="item.name">
          <template v-if="item.name === 'overview'">
            <el-form :model="queryParams" :inline="true" class="competition-filter-form">
              <el-form-item label="关键字">
                <el-input v-model="queryParams.keyword" placeholder="文件名/赛事/学生/学院" clearable @keyup.enter="getList" />
              </el-form-item>
              <el-form-item label="赛事">
                <el-select v-model="queryParams.contestId" clearable style="width: 220px">
                  <el-option v-for="contest in contestOptions" :key="contest.id" :label="contest.contestName" :value="contest.id" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :icon="Search" @click="getList">搜索</el-button>
                <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
              </el-form-item>
            </el-form>

            <div class="competition-file-layout">
              <el-card class="competition-file-layout__aside" shadow="never">
                <template #header>
                  <div class="competition-panel__head">
                    <div>
                      <div class="competition-panel__title">分类目录</div>
                      <div class="competition-panel__desc">按类别分级整理后的文件树</div>
                    </div>
                  </div>
                </template>
                <div v-loading="categoryLoading" class="competition-file-tree">
                  <el-tree
                    :data="[categoryTree]"
                    node-key="id"
                    default-expand-all
                    highlight-current
                    :current-node-key="selectedCategoryId"
                    :expand-on-click-node="false"
                    @node-click="handleNodeClick"
                  />
                </div>
                <div class="competition-file-runtime">
                  <div class="competition-file-runtime__item">
                    <span>当前分类</span>
                    <strong>{{ selectedCategoryLabel }}</strong>
                  </div>
                  <div class="competition-file-runtime__item">
                    <span>筛选结果</span>
                    <strong>{{ listSummary.totalFiles || 0 }} 个文件</strong>
                  </div>
                  <div class="competition-file-runtime__item">
                    <span>筛选体量</span>
                    <strong>{{ formatFileSize(listSummary.totalSize) }}</strong>
                  </div>
                </div>
              </el-card>

              <el-card class="competition-table-card competition-file-layout__main" shadow="never">
                <template #header>
                  <div class="competition-toolbar">
                    <div class="competition-toolbar__left">
                      <div>
                        <div class="competition-panel__title">文件列表</div>
                        <div class="competition-panel__desc">当前分类：{{ selectedCategoryLabel }}，支持直接预览和下载原件。</div>
                      </div>
                    </div>
                    <div class="competition-toolbar__right">
                      <el-button plain :icon="Refresh" @click="reloadOverview">刷新</el-button>
                    </div>
                  </div>
                </template>

                <div class="competition-empty-fix">
                  <el-table v-loading="loading" :data="fileRows" border :row-key="(row) => `${row.assetType}:${row.assetId}`">
                    <el-table-column label="文件名" prop="fileName" min-width="220" show-overflow-tooltip />
                    <el-table-column label="分类" min-width="120">
                      <template #default="scope">
                        <div>{{ scope.row.categoryName }}</div>
                        <div class="competition-panel__desc">{{ scope.row.groupName }}</div>
                      </template>
                    </el-table-column>
                    <el-table-column label="来源" prop="sourceName" min-width="240" show-overflow-tooltip />
                    <el-table-column label="赛事" prop="contestName" min-width="160" show-overflow-tooltip />
                    <el-table-column label="学生" min-width="140">
                      <template #default="scope">
                        <div>{{ scope.row.studentName || '—' }}</div>
                        <div class="competition-panel__desc">{{ scope.row.college || '无学院信息' }}</div>
                      </template>
                    </el-table-column>
                    <el-table-column label="上传人" prop="uploaderName" min-width="120" />
                    <el-table-column label="大小" width="110">
                      <template #default="scope">
                        {{ formatFileSize(scope.row.fileSize) }}
                      </template>
                    </el-table-column>
                    <el-table-column label="时间" min-width="160">
                      <template #default="scope">
                        {{ formatDateTime(scope.row.createdAt) }}
                      </template>
                    </el-table-column>
                    <el-table-column label="操作" width="160" fixed="right">
                      <template #default="scope">
                        <div class="competition-row-actions">
                          <el-button link type="primary" :icon="View" :disabled="!scope.row.previewable" @click="handlePreview(scope.row)">预览</el-button>
                          <el-button link type="primary" :icon="Download" @click="handleDownload(scope.row)">下载</el-button>
                        </div>
                      </template>
                    </el-table-column>
                  </el-table>
                  <el-empty v-if="!loading && !fileRows.length" description="当前条件下没有可展示的文件" />
                </div>

                <div class="competition-pagination">
                  <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
                </div>
              </el-card>
            </div>
          </template>

          <template v-else-if="item.name === 'rules'">
            <el-form :model="policyQuery" :inline="true" class="competition-filter-form">
              <el-form-item label="规则名称">
                <el-input v-model="policyQuery.keyword" placeholder="规则名" clearable @keyup.enter="loadPolicies" />
              </el-form-item>
              <el-form-item label="状态">
                <el-select v-model="policyQuery.status" clearable style="width: 160px">
                  <el-option label="启用" value="enabled" />
                  <el-option label="停用" value="disabled" />
                </el-select>
              </el-form-item>
              <el-form-item label="调度">
                <el-select v-model="policyQuery.scheduleType" clearable style="width: 160px">
                  <el-option label="手工" value="manual" />
                  <el-option label="每日" value="daily" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :icon="Search" @click="loadPolicies">搜索</el-button>
                <el-button :icon="Refresh" @click="resetPolicyQuery">重置</el-button>
                <el-button type="success" plain :icon="Plus" @click="openPolicyDialog()">新增规则</el-button>
                <el-button type="warning" plain :icon="Timer" :loading="scanningDueRules" @click="handleScanDuePolicies">扫描到期规则</el-button>
              </el-form-item>
            </el-form>

            <div class="competition-empty-fix">
              <el-table v-loading="policyLoading" :data="policyRows" border>
                <el-table-column label="规则名称" prop="policyName" min-width="180" />
                <el-table-column label="状态" width="100" align="center">
                  <template #default="scope">
                    <el-tag :type="statusMeta(policyStatusMap, scope.row.status).type">
                      {{ statusMeta(policyStatusMap, scope.row.status).label }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="调度" min-width="140">
                  <template #default="scope">
                    <div>{{ scope.row.scheduleType === 'daily' ? '每日' : '手工' }}</div>
                    <div class="competition-panel__desc">{{ scope.row.scheduleTime || '仅手工执行' }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="范围" min-width="220">
                  <template #default="scope">
                    <div>{{ policyScopeLabel(scope.row) }}</div>
                    <div class="competition-panel__desc">{{ scope.row.incrementMode === 'delta' ? '增量导出' : '全量导出' }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="模板" min-width="260" show-overflow-tooltip>
                  <template #default="scope">
                    <div>{{ scope.row.folderTemplate }}</div>
                    <div class="competition-panel__desc">{{ scope.row.fileNameTemplate }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="投递渠道" min-width="180">
                  <template #default="scope">
                    <div>{{ scope.row.deliveryChannelNames?.join(' / ') || '仅平台内归档' }}</div>
                    <div class="competition-panel__desc">下次执行：{{ formatDateTime(scope.row.nextRunAt, '未排期') }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="最近结果" min-width="180">
                  <template #default="scope">
                    <div>{{ scope.row.lastStatus || '尚未执行' }}</div>
                    <div class="competition-panel__desc">{{ scope.row.lastError || formatDateTime(scope.row.lastRunAt, '尚无记录') }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="220" fixed="right">
                  <template #default="scope">
                    <div class="competition-row-actions">
                      <el-button link type="primary" :loading="runningPolicyId === scope.row.id" @click="handleRunPolicy(scope.row)">执行</el-button>
                      <el-button link type="primary" @click="openPolicyDialog(scope.row)">编辑</el-button>
                      <el-button link type="danger" @click="handleDeletePolicy(scope.row)">删除</el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!policyLoading && !policyRows.length" description="当前还没有导出规则" />
            </div>

            <pagination v-show="policyTotal > 0" :total="policyTotal" v-model:page="policyQuery.pageNum" v-model:limit="policyQuery.pageSize" @pagination="loadPolicies" />
          </template>

          <template v-else-if="item.name === 'batches'">
            <el-form :model="batchQuery" :inline="true" class="competition-filter-form">
              <el-form-item label="关键字">
                <el-input v-model="batchQuery.keyword" placeholder="规则名/批次号/文件名" clearable @keyup.enter="loadBatches" />
              </el-form-item>
              <el-form-item label="状态">
                <el-select v-model="batchQuery.status" clearable style="width: 160px">
                  <el-option label="排队中" value="pending" />
                  <el-option label="处理中" value="processing" />
                  <el-option label="已完成" value="completed" />
                  <el-option label="部分成功" value="partial_success" />
                  <el-option label="失败" value="failed" />
                </el-select>
              </el-form-item>
              <el-form-item label="规则">
                <el-select v-model="batchQuery.policyId" clearable style="width: 220px">
                  <el-option v-for="policy in policyRows" :key="policy.id" :label="policy.policyName" :value="policy.id" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :icon="Search" @click="loadBatches">搜索</el-button>
                <el-button :icon="Refresh" @click="resetBatchQuery">重置</el-button>
              </el-form-item>
            </el-form>

            <div class="competition-empty-fix">
              <el-table v-loading="batchLoading" :data="batchRows" border>
                <el-table-column label="批次号" prop="batchNo" min-width="170" />
                <el-table-column label="规则名称" prop="policyName" min-width="180" />
                <el-table-column label="状态" width="110" align="center">
                  <template #default="scope">
                    <el-tag :type="statusMeta(batchStatusMap, scope.row.status).type">
                      {{ statusMeta(batchStatusMap, scope.row.status).label }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="进度" min-width="220">
                  <template #default="scope">
                    <div>
                      <el-progress :percentage="scope.row.progress || 0" :status="scope.row.status === 'failed' ? 'exception' : scope.row.status === 'completed' ? 'success' : ''" />
                      <div class="competition-panel__desc" style="margin-top: 4px">
                        {{ scope.row.currentStep || '等待执行' }}
                      </div>
                      <div v-if="scope.row.errorMessage" class="competition-file-danger">
                        {{ scope.row.errorMessage }}
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="文件数" width="100" align="center">
                  <template #default="scope">
                    {{ scope.row.sourceCount || 0 }}
                  </template>
                </el-table-column>
                <el-table-column label="归档包" prop="fileName" min-width="220" show-overflow-tooltip />
                <el-table-column label="投递结果" min-width="180">
                  <template #default="scope">
                    {{ batchDeliveryLabel(scope.row) }}
                  </template>
                </el-table-column>
                <el-table-column label="更新时间" min-width="170">
                  <template #default="scope">
                    {{ formatDateTime(scope.row.finishedAt || scope.row.updatedAt || scope.row.createdAt) }}
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="220" fixed="right">
                  <template #default="scope">
                    <div class="competition-row-actions">
                      <el-button link type="primary" @click="openBatchDetail(scope.row)">详情</el-button>
                      <el-button
                        link
                        type="primary"
                        :loading="downloadingBatchId === scope.row.id"
                        :disabled="!scope.row.fileName || !['completed', 'partial_success'].includes(scope.row.status)"
                        @click="handleDownloadBatch(scope.row)"
                      >
                        下载
                      </el-button>
                      <el-button
                        v-if="scope.row.canRetry"
                        link
                        type="warning"
                        :loading="retryingBatchId === scope.row.id"
                        @click="handleRetryBatch(scope.row)"
                      >
                        重试
                      </el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!batchLoading && !batchRows.length" description="当前还没有导出批次" />
            </div>

            <pagination v-show="batchTotal > 0" :total="batchTotal" v-model:page="batchQuery.pageNum" v-model:limit="batchQuery.pageSize" @pagination="loadBatches" />
          </template>

          <template v-else-if="item.name === 'channels'">
            <el-form :model="channelQuery" :inline="true" class="competition-filter-form">
              <el-form-item label="渠道名称">
                <el-input v-model="channelQuery.keyword" placeholder="渠道名" clearable @keyup.enter="loadChannels" />
              </el-form-item>
              <el-form-item label="状态">
                <el-select v-model="channelQuery.status" clearable style="width: 160px">
                  <el-option label="启用" value="enabled" />
                  <el-option label="停用" value="disabled" />
                </el-select>
              </el-form-item>
              <el-form-item label="类型">
                <el-select v-model="channelQuery.channelType" clearable style="width: 160px">
                  <el-option label="本地目录" value="local_folder" />
                  <el-option label="百度网盘" value="baidu_pan" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :icon="Search" @click="loadChannels">搜索</el-button>
                <el-button :icon="Refresh" @click="resetChannelQuery">重置</el-button>
                <el-button type="success" plain :icon="Plus" @click="openChannelDialog()">新增渠道</el-button>
              </el-form-item>
            </el-form>

            <div class="competition-empty-fix">
              <el-table v-loading="channelLoading" :data="channelRows" border>
                <el-table-column label="渠道名称" prop="channelName" min-width="180" />
                <el-table-column label="类型" width="120">
                  <template #default="scope">
                    {{ channelTypeMap[scope.row.channelType] || scope.row.channelType }}
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="100" align="center">
                  <template #default="scope">
                    <el-tag :type="statusMeta(policyStatusMap, scope.row.status).type">
                      {{ statusMeta(policyStatusMap, scope.row.status).label }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="目标目录" min-width="220" show-overflow-tooltip>
                  <template #default="scope">
                    <div>{{ scope.row.configPreview?.rootPath || '未配置' }}</div>
                    <div class="competition-panel__desc">{{ scope.row.configPreview?.folderTemplate || '未配置目录模板' }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="模式" min-width="160">
                  <template #default="scope">
                    <div>{{ scope.row.channelType === 'baidu_pan' && scope.row.configPreview?.mockMode ? '百度网盘 mock' : scope.row.configPreview?.authMode === 'oauth' ? 'OAuth 授权' : '正式投递' }}</div>
                    <div class="competition-panel__desc">{{ scope.row.configPreview?.mockRoot || scope.row.configPreview?.oauthStatus || scope.row.configPreview?.accessTokenMasked || '—' }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="最近校验" min-width="180">
                  <template #default="scope">
                    <div>{{ formatDateTime(scope.row.lastValidatedAt, '尚未校验') }}</div>
                    <div class="competition-panel__desc">{{ scope.row.lastError || scope.row.lastValidationStatus || '—' }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="220" fixed="right">
                  <template #default="scope">
                    <div class="competition-row-actions">
                      <el-button
                        v-if="scope.row.channelType === 'baidu_pan' && !scope.row.configPreview?.mockMode"
                        link
                        type="warning"
                        :loading="authorizingChannelId === scope.row.id"
                        @click="handleAuthorizeChannel(scope.row)"
                      >
                        授权
                      </el-button>
                      <el-button link type="primary" :loading="validatingChannelId === scope.row.id" @click="handleValidateChannel(scope.row)">校验</el-button>
                      <el-button link type="primary" @click="openChannelDialog(scope.row)">编辑</el-button>
                      <el-button link type="danger" @click="handleDeleteChannel(scope.row)">删除</el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!channelLoading && !channelRows.length" description="当前还没有投递渠道" />
            </div>

            <pagination v-show="channelTotal > 0" :total="channelTotal" v-model:page="channelQuery.pageNum" v-model:limit="channelQuery.pageSize" @pagination="loadChannels" />
          </template>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="policyDialogVisible" :title="policyForm.id ? '编辑导出规则' : '新增导出规则'" width="760px" append-to-body>
      <div v-loading="metadataLoading">
        <el-alert type="info" show-icon :closable="false" class="competition-page__panel">
          <template #title>
            模板变量：{{ exportMetadata.templateVariables.map(item => `${item.key}=${item.label}`).join('，') }}
          </template>
        </el-alert>
        <el-form label-width="110px">
          <el-form-item label="规则名称">
            <el-input v-model="policyForm.policyName" placeholder="例如：每日报名材料归档" />
          </el-form-item>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="状态">
                <el-select v-model="policyForm.status">
                  <el-option label="启用" value="enabled" />
                  <el-option label="停用" value="disabled" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="调度方式">
                <el-select v-model="policyForm.scheduleType">
                  <el-option label="每日" value="daily" />
                  <el-option label="手工" value="manual" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="执行时间">
                <el-time-picker v-model="policyForm.scheduleTime" value-format="HH:mm" format="HH:mm" placeholder="02:00" :disabled="policyForm.scheduleType !== 'daily'" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="增量模式">
            <el-radio-group v-model="policyForm.incrementMode">
              <el-radio label="full">全量导出</el-radio>
              <el-radio label="delta">仅导出新增/变更</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="文件分类">
            <el-select v-model="policyForm.scope.categoryCodes" multiple clearable collapse-tags style="width: 100%">
              <el-option v-for="option in exportMetadata.categoryOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="赛事范围">
            <el-select v-model="policyForm.scope.contestIds" multiple clearable collapse-tags style="width: 100%">
              <el-option v-for="contest in exportMetadata.contestOptions" :key="contest.id" :label="contest.contestName" :value="contest.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="学院范围">
            <el-select v-model="policyForm.scope.collegeNames" multiple clearable collapse-tags style="width: 100%">
              <el-option v-for="college in exportMetadata.collegeOptions" :key="college" :label="college" :value="college" />
            </el-select>
          </el-form-item>
          <el-form-item label="关键字补充">
            <el-input v-model="policyForm.scope.keyword" placeholder="文件名 / 来源名称 / 学生 / 学院" />
          </el-form-item>
          <el-form-item label="目录模板">
            <el-input v-model="policyForm.folderTemplate" placeholder="{categoryName}/{contestName}/{college}/{date}" />
          </el-form-item>
          <el-form-item label="文件名模板">
            <el-input v-model="policyForm.fileNameTemplate" placeholder="{policyName}_{date}_{batchNo}.zip" />
          </el-form-item>
          <el-form-item label="投递渠道">
            <el-select v-model="policyForm.deliveryChannelIds" multiple clearable collapse-tags style="width: 100%">
              <el-option v-for="channel in enabledChannelOptions" :key="channel.id" :label="channel.channelName" :value="channel.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="附带清单">
            <el-switch v-model="policyForm.includeManifest" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="policyForm.remark" type="textarea" :rows="3" placeholder="规则说明、场景备注" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="policyDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPolicy" @click="submitPolicy">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="channelDialogVisible" :title="channelForm.id ? '编辑投递渠道' : '新增投递渠道'" width="720px" append-to-body>
      <el-form label-width="120px">
        <el-form-item label="渠道名称">
          <el-input v-model="channelForm.channelName" placeholder="例如：平台归档目录 / 百度网盘-学院共享盘" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="渠道类型">
              <el-select v-model="channelForm.channelType">
                <el-option label="本地目录" value="local_folder" />
                <el-option label="百度网盘" value="baidu_pan" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select v-model="channelForm.status">
                <el-option label="启用" value="enabled" />
                <el-option label="停用" value="disabled" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="冲突策略" v-if="channelForm.channelType === 'baidu_pan'">
              <el-select v-model="channelForm.config.conflictMode">
                <el-option label="覆盖" value="overwrite" />
                <el-option label="保留新副本" value="newcopy" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="channelForm.channelType === 'baidu_pan' ? '网盘根目录' : '目标根目录'">
          <el-input v-model="channelForm.config.rootPath" :placeholder="channelForm.channelType === 'baidu_pan' ? '/competition/archive' : 'exports/deliveries'" />
        </el-form-item>
        <el-form-item label="目录模板">
          <el-input v-model="channelForm.config.folderTemplate" placeholder="{policyName}/{date}" />
        </el-form-item>
        <template v-if="channelForm.channelType === 'baidu_pan'">
          <el-form-item label="Mock 模式">
            <el-switch v-model="channelForm.config.mockMode" />
          </el-form-item>
          <el-form-item v-if="channelForm.config.mockMode" label="Mock 目录">
            <el-input v-model="channelForm.config.mockRoot" placeholder="mock_baidu_pan" />
          </el-form-item>
          <template v-else>
            <el-alert type="info" show-icon :closable="false" class="competition-page__panel">
              <template #title>推荐先保存渠道，再点击“发起授权”走百度网盘 OAuth；Access Token 仅保留兼容模式。</template>
            </el-alert>
            <el-form-item label="OAuth 回调">
              <div style="width: 100%">
                <div>{{ channelForm.config.callbackUrl || 'http://localhost:5002/api/integrations/baidu-pan/callback' }}</div>
                <div class="competition-panel__desc">授权状态：{{ channelForm.config.oauthStatus || '未授权' }}，模式：{{ channelForm.config.authMode || '待授权' }}</div>
                <div class="competition-panel__desc">最近授权：{{ formatDateTime(channelForm.config.authorizedAt, '未授权') }}，过期时间：{{ formatDateTime(channelForm.config.tokenExpiresAt, '未记录') }}</div>
                <div class="competition-panel__desc" v-if="channelForm.config.accessTokenMasked || channelForm.config.refreshTokenMasked">AccessToken：{{ channelForm.config.accessTokenMasked || '—' }}，RefreshToken：{{ channelForm.config.refreshTokenMasked || '—' }}</div>
                <div class="competition-panel__desc" v-if="channelForm.config.scope">授权范围：{{ channelForm.config.scope }}</div>
                <el-button type="warning" plain style="margin-top: 12px" :disabled="!channelForm.id" :loading="authorizingChannelId === channelForm.id" @click="handleAuthorizeChannel()">
                  {{ channelForm.id ? '发起授权' : '先保存后授权' }}
                </el-button>
              </div>
            </el-form-item>
            <el-form-item label="Access Token">
              <el-input v-model="channelForm.config.accessToken" show-password placeholder="留空则继续使用当前授权结果；需要手工兼容模式时再填写" />
            </el-form-item>
          </template>
        </template>
        <el-form-item label="备注">
          <el-input v-model="channelForm.remark" type="textarea" :rows="3" placeholder="说明用途、共享对象或账号信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="channelDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingChannel" @click="submitChannel">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="batchDetailVisible" title="批次详情" size="68%">
      <div v-loading="batchDetailLoading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="批次号">{{ batchDetail.batchNo || '-' }}</el-descriptions-item>
          <el-descriptions-item label="规则">{{ batchDetail.policyName || '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusMeta(batchStatusMap, batchDetail.status).type">
              {{ statusMeta(batchStatusMap, batchDetail.status).label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="归档包">{{ batchDetail.fileName || '-' }}</el-descriptions-item>
          <el-descriptions-item label="文件数">{{ batchDetail.sourceCount || 0 }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ formatDateTime(batchDetail.finishedAt, '-') }}</el-descriptions-item>
          <el-descriptions-item label="当前步骤">{{ batchDetail.currentStep || '-' }}</el-descriptions-item>
          <el-descriptions-item label="错误信息">{{ batchDetail.errorMessage || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">归档清单</div>
                <div class="competition-panel__desc">这里展示规则实际整理出来的目录结构</div>
              </div>
            </div>
          </template>
          <el-table :data="batchDetail.manifest?.entries || []" border max-height="320">
            <el-table-column label="目标路径" prop="packagePath" min-width="280" show-overflow-tooltip />
            <el-table-column label="分类" prop="categoryName" min-width="120" />
            <el-table-column label="赛事" prop="contestName" min-width="160" show-overflow-tooltip />
            <el-table-column label="学院" prop="college" min-width="140" />
            <el-table-column label="原文件" prop="fileName" min-width="220" show-overflow-tooltip />
            <el-table-column label="大小" width="110">
              <template #default="scope">
                {{ formatFileSize(scope.row.fileSize) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">投递记录</div>
                <div class="competition-panel__desc">本地目录和百度网盘渠道都会在这里回写结果</div>
              </div>
            </div>
          </template>
          <el-table :data="batchDetail.deliveries || []" border>
            <el-table-column label="渠道" prop="channelName" min-width="180" />
            <el-table-column label="类型" min-width="120">
              <template #default="scope">
                {{ channelTypeMap[scope.row.channelType] || scope.row.channelType }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110" align="center">
              <template #default="scope">
                <el-tag :type="statusMeta(deliveryStatusMap, scope.row.status).type">
                  {{ statusMeta(deliveryStatusMap, scope.row.status).label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="目标路径" prop="targetPath" min-width="260" show-overflow-tooltip />
            <el-table-column label="步骤" prop="currentStep" min-width="140" />
            <el-table-column label="错误信息" prop="errorMessage" min-width="180" show-overflow-tooltip />
          </el-table>
        </el-card>
      </div>
    </el-drawer>

    <competition-file-preview-dialog ref="previewRef" />
  </div>
</template>

<style scoped lang="scss">
.competition-file-layout {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}

.competition-file-layout__aside {
  position: sticky;
  top: 12px;
}

.competition-file-tree {
  min-height: 360px;
}

.competition-file-runtime {
  margin-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
  display: grid;
  gap: 10px;
}

.competition-file-runtime__item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.competition-file-runtime__item strong {
  color: var(--el-text-color-primary);
  font-weight: 600;
}

.competition-file-danger {
  font-size: 12px;
  color: var(--el-color-danger);
  margin-top: 4px;
}

@media (max-width: 1080px) {
  .competition-file-layout {
    grid-template-columns: 1fr;
  }

  .competition-file-layout__aside {
    position: static;
  }
}
</style>
