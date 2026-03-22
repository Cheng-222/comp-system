<script setup>
import { DocumentAdd, Download, EditPen, Finished, Medal, Plus, Refresh, Search, Tickets, View } from '@element-plus/icons-vue'
import { computed, getCurrentInstance, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listContests } from '@/api/competition/contest'
import { addResult, getResult, importResults, listResults, updateResult, uploadCertificate } from '@/api/competition/result'
import { createStatisticsExportRecord } from '@/api/competition/statistics'
import { listStudents } from '@/api/competition/student'
import CompetitionFilePreviewDialog from '@/components/CompetitionFilePreviewDialog.vue'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import CompetitionMaterialTable from '@/components/CompetitionMaterialTable.vue'
import CompetitionStatusTag from '@/components/CompetitionStatusTag.vue'
import UploadDropzone from '@/components/UploadDropzone.vue'
import useUserStore from '@/store/modules/user'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const userStore = useUserStore()
const { proxy } = getCurrentInstance()

const activeTab = ref('scores')
const loading = ref(false)
const detailLoading = ref(false)
const submitting = ref(false)
const importSubmitting = ref(false)
const certificateSubmitting = ref(false)
const archiveTaskSubmitting = ref(false)
const importOpen = ref(false)
const certificateOpen = ref(false)
const editOpen = ref(false)
const detailOpen = ref(false)
const editTitle = ref('新增成绩')
const total = ref(0)
const resultList = ref([])
const detail = ref({ registration: null })
const contestOptions = ref([])
const studentOptions = ref([])
const importFiles = ref([])
const certificateFiles = ref([])
const previewRef = ref()
const editFormRef = ref()
const scoreQuery = reactive({ keyword: '', contestId: undefined, resultStatus: '', awardLevel: '', pageNum: 1, pageSize: 10 })
const certificateQuery = reactive({ keyword: '', contestId: undefined, resultStatus: '', hasCertificate: undefined, pageNum: 1, pageSize: 10 })
const archiveQuery = reactive({ keyword: '', contestId: undefined, resultStatus: '', hasCertificate: undefined, pageNum: 1, pageSize: 10 })
const importForm = reactive({ overwrite: true })
const certificateForm = reactive({ resultId: undefined, resultLabel: '' })
const editForm = reactive({ id: undefined, contestId: undefined, studentId: undefined, awardLevel: '', resultStatus: 'pending', score: '', ranking: '', certificateNo: '', archiveRemark: '', confirmedAt: '' })
const importFileTypes = ['xlsx', 'csv']
const certificateFileTypes = ['pdf', 'jpg', 'jpeg', 'png']

const canEdit = computed(() => Boolean(userStore.capabilities.manageResults))
const canImport = computed(() => Boolean(userStore.capabilities.manageResults))
const canExportArchive = computed(() => Boolean(userStore.capabilities.exportArchives))
const isStudentView = computed(() => userStore.roles.includes('student') && !canEdit.value)
const isReadOnlyView = computed(() => !canEdit.value)
const showStudentColumns = computed(() => !isStudentView.value)
const pageTitle = computed(() => {
  if (canEdit.value) return '赛后管理'
  return isStudentView.value ? '我的赛后结果' : '赛后结果'
})
const visibleTabs = computed(() => {
  const tabs = [
    { label: canEdit.value ? '成绩管理' : (isStudentView.value ? '我的成绩' : '成绩查询'), name: 'scores' },
    { label: canEdit.value ? '证书管理' : (isStudentView.value ? '我的证书' : '证书查询'), name: 'certificates' },
  ]
  if (canExportArchive.value) {
    tabs.push({ label: '归档资料', name: 'archives' })
  }
  return tabs
})
const currentQuery = computed(() => {
  if (activeTab.value === 'certificates') return certificateQuery
  if (activeTab.value === 'archives') return archiveQuery
  return scoreQuery
})

const editRules = {
  contestId: [{ required: true, message: '请选择赛事', trigger: 'change' }],
  studentId: [{ required: true, message: '请选择学生', trigger: 'change' }],
  resultStatus: [{ required: true, message: '请选择结果状态', trigger: 'change' }],
  score: [{ validator: validateScore, trigger: 'blur' }],
  ranking: [{ validator: validateRanking, trigger: 'blur' }],
}

function validateScore(_rule, value, callback) {
  if (value === '' || value === null || value === undefined) {
    callback()
    return
  }
  if (!Number.isNaN(Number(value))) {
    callback()
    return
  }
  callback(new Error('成绩分数必须是数字'))
}

function validateRanking(_rule, value, callback) {
  if (value === '' || value === null || value === undefined) {
    callback()
    return
  }
  if (/^\d+$/.test(String(value))) {
    callback()
    return
  }
  callback(new Error('名次必须是正整数'))
}

const pageSubtitle = computed(() => {
  if (activeTab.value === 'certificates') return canEdit.value ? '处理证书上传、下载和归档完整性。' : '查看证书归档和下载状态。'
  if (activeTab.value === 'archives') return '查看归档信息并导出资料。'
  if (canEdit.value) return '维护成绩、名次、获奖等级和结果状态。'
  return isStudentView.value ? '查看我的成绩、获奖等级和确认状态。' : '查看成绩、获奖等级和确认状态。'
})
const pageScopeNote = computed(() => {
  if (activeTab.value === 'archives') return '注意：归档页是赛后资料出口，导出前先确认赛事筛选和证书完整性。'
  if (activeTab.value === 'certificates') return canEdit.value ? '注意：证书管理只处理上传、下载和归档完整性，不负责改成绩结论。' : '注意：这里查看证书归档情况，成绩结论请回到成绩页确认。'
  return canEdit.value
    ? '注意：成绩页负责录入和维护结果，证书上传与正式归档分别在另外两个标签页处理。'
    : '注意：这里主要看结果和确认状态，证书文件请去“证书管理”查看。'
})
const pageGuide = computed(() => {
  if (activeTab.value === 'archives') {
    return {
      eyebrow: '归档入口',
      title: '先核对缺失项，再导出正式归档资料',
      desc: '归档页不只是下载文件，更重要的是先确认成绩、证书和备注是否已经补完整。',
      steps: [
        { step: '1', title: '先筛出赛事范围', desc: '导出前先限定赛事，避免不同批次资料混在一起。' },
        { step: '2', title: '再查证书和备注', desc: '重点看证书是否齐全、归档说明是否补完。' },
        { step: '3', title: '最后导出归档', desc: '确认口径一致后再导出，减少二次整理成本。' },
      ],
    }
  }
  if (activeTab.value === 'certificates') {
    return {
      eyebrow: '证书入口',
      title: canEdit.value ? '先补证书，再回头检查归档完整性' : '先看证书是否已归档，再决定是否下载',
      desc: canEdit.value
        ? '证书页只处理上传、下载和归档完整性，不建议在这里回头改成绩本身。'
        : '如果这里没有证书文件，通常说明赛后归档还没完成，不代表结果无效。',
      steps: [
        { step: '1', title: '先筛选要查的赛事', desc: '按赛事和状态快速缩小证书处理范围。' },
        { step: '2', title: '再看证书归档状态', desc: '优先处理未上传证书或编号待补的记录。' },
        { step: '3', title: '最后补传或下载', desc: '管理端补传证书，查看端按权限直接下载文件。' },
      ],
    }
  }
  return {
    eyebrow: '成绩入口',
    title: canEdit.value ? '先确认结果，再补成绩细节和后续归档' : '先看成绩结果，再关注证书和确认状态',
    desc: canEdit.value
      ? '成绩页负责录入结果、分数、名次和获奖等级，后续证书与归档分别去对应标签页处理。'
      : '这页最适合先确认自己的结果状态，证书和归档状态在后续标签页继续看。',
    steps: [
      { step: '1', title: canEdit.value ? '先录入或导入结果' : '先筛出自己的结果', desc: canEdit.value ? '先把赛事结果录进系统，保证赛后链路有起点。' : '先按赛事和状态找到需要确认的比赛结果。' },
      { step: '2', title: canEdit.value ? '再补成绩细节' : '再看获奖和确认时间', desc: canEdit.value ? '把获奖等级、分数、名次等关键字段补完整。' : '重点核对获奖等级、名次和确认时间是否已经记录。' },
      { step: '3', title: canEdit.value ? '最后进入证书和归档' : '需要文件时去证书管理', desc: canEdit.value ? '成绩结论稳定后，再推进证书上传和正式归档。' : '成绩确认后，再去证书管理查看是否已经归档。' },
    ],
  }
})
const guideActions = computed(() => {
  if (activeTab.value === 'archives') {
    return canExportArchive.value
      ? [{ key: 'export-archive', label: '导出归档', type: 'success', plain: false }]
      : []
  }
  if (activeTab.value === 'scores' && canEdit.value) {
    return [
      { key: 'add', label: '新增成绩', type: 'primary', plain: false },
      { key: 'import', label: '批量导入', type: 'warning' },
    ]
  }
  return []
})

const metricCards = computed(() => {
  const awardedCount = resultList.value.filter(item => item.awardLevel).length
  const certificateCount = resultList.value.filter(item => item.certificateAttachmentName).length
  const confirmedCount = resultList.value.filter(item => item.confirmedAt).length
  if (activeTab.value === 'certificates') {
    if (canEdit.value) {
      return [
        { title: '成绩记录', value: total.value, desc: '当前证书视图记录数', icon: Tickets },
        { title: '已归档证书', value: certificateCount, desc: '当前页已上传证书', icon: Finished },
        { title: '待归档证书', value: resultList.value.filter(item => !item.certificateAttachmentName).length, desc: '当前页仍未上传', icon: DocumentAdd },
        { title: '可下载证书', value: resultList.value.filter(item => item.permissions?.canDownloadCertificate).length, desc: '当前页可直接下载', icon: Download },
      ]
    }
    return [
      { title: isStudentView.value ? '我的证书' : '证书记录', value: total.value, desc: '当前证书视图记录数', icon: Tickets },
      { title: '已归档', value: certificateCount, desc: '已上传证书文件', icon: Finished },
      { title: '待归档', value: resultList.value.filter(item => !item.certificateAttachmentName).length, desc: '暂无证书文件', icon: DocumentAdd },
      { title: '可下载', value: resultList.value.filter(item => item.permissions?.canDownloadCertificate).length, desc: '当前页可下载证书', icon: Download },
    ]
  }
  if (activeTab.value === 'archives') {
    return [
      { title: '归档记录', value: total.value, desc: '当前归档视图记录数', icon: Finished },
      { title: '证书齐全', value: certificateCount, desc: '已附证书文件', icon: Download },
      { title: '已填备注', value: resultList.value.filter(item => item.archiveRemark).length, desc: '已有归档说明', icon: DocumentAdd },
      { title: '已确认成绩', value: confirmedCount, desc: '已确认时间的记录', icon: Medal },
    ]
  }
  if (canEdit.value) {
    return [
      { title: '成绩记录', value: total.value, desc: '按筛选条件统计', icon: Tickets },
      { title: '获奖人数', value: awardedCount, desc: '当前页已填写获奖等级', icon: Medal },
      { title: '证书归档', value: certificateCount, desc: '当前页已归档证书', icon: Finished },
      { title: '手工维护', value: resultList.value.filter(item => item.score || item.ranking || item.certificateNo).length, desc: '当前页已补细字段', icon: DocumentAdd },
    ]
  }
  return [
    { title: isStudentView.value ? '我的成绩' : '成绩记录', value: total.value, desc: '按筛选条件统计', icon: Tickets },
    { title: '获奖记录', value: awardedCount, desc: '当前页已填写获奖等级', icon: Medal },
    { title: '证书归档', value: certificateCount, desc: '当前页已归档证书', icon: Finished },
    { title: '已确认', value: confirmedCount, desc: '当前页已确认结果', icon: DocumentAdd },
  ]
})

function formatDateTime(value, options = {}) {
  const { withTime = true, fallback = '待补充' } = options
  return formatBeijingDateTime(value, { fallback, withTime, withSeconds: false })
}

function resetImportForm() {
  importForm.overwrite = true
  importFiles.value = []
}

function resetEditForm() {
  Object.assign(editForm, { id: undefined, contestId: undefined, studentId: undefined, awardLevel: '', resultStatus: 'pending', score: '', ranking: '', certificateNo: '', archiveRemark: '', confirmedAt: '' })
  nextTick(() => editFormRef.value?.clearValidate())
}

async function loadOptions() {
  const contestRes = await listContests({ pageSize: 200 })
  contestOptions.value = contestRes.data.list || []
  if (canEdit.value) {
    const studentRes = await listStudents({ pageSize: 200 })
    studentOptions.value = studentRes.data.list || []
  } else {
    studentOptions.value = []
  }
}

async function getList() {
  loading.value = true
  try {
    const res = await listResults(currentQuery.value)
    resultList.value = res.data.list || []
    total.value = Number(res.data.total || 0)
    currentQuery.value.pageNum = Number(res.data.pageNum || currentQuery.value.pageNum)
    currentQuery.value.pageSize = Number(res.data.pageSize || currentQuery.value.pageSize)
  } finally {
    loading.value = false
  }
}

async function openDetail(row) {
  detailOpen.value = true
  detailLoading.value = true
  try {
    const res = await getResult(row.id)
    detail.value = res.data || { registration: null }
  } finally {
    detailLoading.value = false
  }
}

function resetQuery() {
  Object.assign(currentQuery.value, { keyword: '', contestId: undefined, resultStatus: '', awardLevel: '', hasCertificate: undefined, pageNum: 1, pageSize: currentQuery.value.pageSize })
  getList()
}

function handleTabChange(name) {
  activeTab.value = name
  getList()
}

function handleImportOpen() {
  resetImportForm()
  importOpen.value = true
}

function handleAdd() {
  resetEditForm()
  editTitle.value = '新增成绩'
  editOpen.value = true
}

function handleEdit(row) {
  resetEditForm()
  Object.assign(editForm, {
    id: row.id,
    contestId: row.contestId,
    studentId: row.studentId,
    awardLevel: row.awardLevel || '',
    resultStatus: row.resultStatus || 'pending',
    score: row.score ?? '',
    ranking: row.ranking ?? '',
    certificateNo: row.certificateNo || '',
    archiveRemark: row.archiveRemark || '',
    confirmedAt: row.confirmedAt || '',
  })
  editTitle.value = '编辑成绩'
  editOpen.value = true
}

function handleImportTemplate() {
  proxy.download('/api/v1/results/import-template', {}, `成绩导入模板_${new Date().getTime()}.xlsx`)
}

async function handleArchiveExport() {
  archiveTaskSubmitting.value = true
  try {
    await createStatisticsExportRecord({ taskType: 'archive_export', contestId: currentQuery.value.contestId })
    ElMessage.success('归档导出任务已创建，请到统计报表 > 导出中心下载')
  } finally {
    archiveTaskSubmitting.value = false
  }
}

function handleGuideAction(action) {
  if (action.key === 'add') {
    handleAdd()
    return
  }
  if (action.key === 'import') {
    handleImportOpen()
    return
  }
  if (action.key === 'export-archive') {
    handleArchiveExport()
  }
}

async function submitImport() {
  const importFile = importFiles.value[0]?.raw
  if (!importFile) {
    ElMessage.warning('请先选择导入文件')
    return
  }
  importSubmitting.value = true
  try {
    const payload = new FormData()
    payload.append('file', importFile)
    payload.append('overwrite', importForm.overwrite)
    const res = await importResults(payload)
    ElMessage.success(`导入完成：成功 ${res.data.successCount} 条，失败 ${res.data.failCount} 条`)
    if (res.data.failCount) {
      await ElMessageBox.alert(res.data.errors.map(item => `第 ${item.row} 行：${item.message}`).join('<br/>'), '导入失败明细', { dangerouslyUseHTMLString: true })
    }
    importOpen.value = false
    currentQuery.value.pageNum = 1
    await getList()
  } finally {
    importSubmitting.value = false
  }
}

async function submitEdit() {
  await editFormRef.value?.validate()
  submitting.value = true
  try {
    if (editForm.id) {
      await updateResult(editForm)
      ElMessage.success('成绩更新成功')
    } else {
      await addResult(editForm)
      ElMessage.success('成绩创建成功')
    }
    editOpen.value = false
    await getList()
  } finally {
    submitting.value = false
  }
}

function handleCertificate(row) {
  certificateForm.resultId = row.id
  certificateForm.resultLabel = `${row.contestName} / ${row.studentName}`
  certificateFiles.value = []
  certificateOpen.value = true
}

async function submitCertificate() {
  if (!certificateForm.resultId) return
  const certificateFile = certificateFiles.value[0]?.raw
  if (!certificateFile) {
    ElMessage.warning('请先选择证书文件')
    return
  }
  certificateSubmitting.value = true
  try {
    const payload = new FormData()
    payload.append('resultId', certificateForm.resultId)
    payload.append('file', certificateFile)
    await uploadCertificate(payload)
    ElMessage.success('证书归档成功')
    certificateOpen.value = false
    if (detailOpen.value && detail.value.id === certificateForm.resultId) {
      await openDetail({ id: certificateForm.resultId })
    }
    await getList()
  } finally {
    certificateSubmitting.value = false
  }
}

function handleCertificateDownload(row) {
  if (!row.certificateAttachmentName) {
    ElMessage.warning('当前记录还没有证书文件')
    return
  }
  if (!row.permissions?.canDownloadCertificate) {
    ElMessage.warning('当前账号无权下载该证书')
    return
  }
  proxy.download('/api/v1/certificates/download', { resultId: row.id }, row.certificateAttachmentName)
}

function handleCertificatePreview(row) {
  if (!row.certificateAttachmentName) {
    ElMessage.warning('当前记录还没有证书文件')
    return
  }
  if (!row.permissions?.canPreviewCertificate) {
    ElMessage.warning('当前账号无权查看该证书')
    return
  }
  previewRef.value?.open({
    url: '/api/v1/certificates/preview',
    params: { resultId: row.id },
    fileName: row.certificateAttachmentName,
  })
}

onMounted(async () => {
  if (!visibleTabs.value.some(item => item.name === activeTab.value)) {
    activeTab.value = visibleTabs.value[0].name
  }
  await loadOptions()
  await getList()
})
</script>

<template>
  <div class="competition-page">
    <el-card class="competition-control-card" shadow="never">
      <template #header>
        <div class="competition-control-head">
          <div class="competition-control-copy">
            <div class="competition-control-eyebrow">Post Contest Archive</div>
            <div class="competition-control-title">{{ pageTitle }}</div>
            <div class="competition-control-subtitle">{{ pageSubtitle }}</div>
          </div>
          <div class="competition-control-actions">
            <el-button v-if="canEdit && activeTab === 'scores'" type="primary" :icon="Plus" @click="handleAdd">新增成绩</el-button>
            <el-button v-if="canImport && activeTab === 'scores'" plain :icon="DocumentAdd" @click="handleImportOpen">批量导入</el-button>
            <el-button v-if="activeTab === 'scores' && canEdit" plain :icon="Download" @click="handleImportTemplate">模板下载</el-button>
            <el-button v-if="activeTab === 'archives' && canExportArchive" plain :icon="Download" :loading="archiveTaskSubmitting" @click="handleArchiveExport">创建归档导出</el-button>
            <el-button plain :icon="Refresh" @click="getList">刷新列表</el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane v-for="item in visibleTabs" :key="item.name" :label="item.label" :name="item.name" />
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

      <el-form :model="currentQuery" :inline="true" class="competition-filter-form">
        <el-form-item label="关键字"><el-input v-model="currentQuery.keyword" placeholder="赛事/学生/学院" clearable @keyup.enter="getList" /></el-form-item>
        <el-form-item label="赛事">
          <el-select v-model="currentQuery.contestId" clearable style="width: 180px">
            <el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="结果状态">
          <el-select v-model="currentQuery.resultStatus" clearable style="width: 140px">
            <el-option label="待确认" value="pending" />
            <el-option label="已获奖" value="awarded" />
            <el-option label="已参赛" value="participated" />
            <el-option label="已归档" value="archived" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="activeTab === 'scores'" label="获奖等级"><el-input v-model="currentQuery.awardLevel" placeholder="如 一等奖" clearable /></el-form-item>
        <el-form-item v-else label="证书归档">
          <el-select v-model="currentQuery.hasCertificate" clearable style="width: 130px">
            <el-option label="已归档" :value="true" />
            <el-option label="未归档" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="getList">搜索</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
          <el-button v-if="activeTab === 'archives' && canExportArchive" type="success" plain :icon="Download" :loading="archiveTaskSubmitting" @click="handleArchiveExport">创建归档导出</el-button>
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
              <div class="competition-panel__title">{{ visibleTabs.find(item => item.name === activeTab)?.label }}</div>
              <div class="competition-panel__desc">{{ pageSubtitle }}</div>
            </div>
          </div>
          <div class="competition-toolbar__right">
            <el-button v-if="activeTab === 'scores' && canEdit" type="primary" plain :icon="Plus" @click="handleAdd">新增</el-button>
            <el-button v-if="activeTab === 'scores' && canEdit" plain :icon="Download" @click="handleImportTemplate">模板</el-button>
            <el-button v-if="activeTab === 'scores' && canImport" plain :icon="DocumentAdd" @click="handleImportOpen">导入</el-button>
            <el-button v-if="activeTab === 'archives' && canExportArchive" type="warning" plain :icon="Download" :loading="archiveTaskSubmitting" @click="handleArchiveExport">创建归档导出</el-button>
          </div>
        </div>
      </template>
      <div class="competition-empty-fix">
        <el-table v-loading="loading" :data="resultList" border row-key="id">
          <template v-if="activeTab === 'scores'">
            <el-table-column label="赛事" prop="contestName" min-width="180" />
            <el-table-column v-if="showStudentColumns" label="学生" prop="studentName" min-width="100" />
            <el-table-column v-if="showStudentColumns" label="学号" prop="studentNo" min-width="120" />
            <el-table-column label="获奖等级" prop="awardLevel" min-width="110" />
            <el-table-column label="分数" prop="score" width="90" />
            <el-table-column label="名次" prop="ranking" width="90" />
            <el-table-column label="结果状态" width="120"><template #default="scope"><competition-status-tag :value="scope.row.resultStatus" /></template></el-table-column>
            <el-table-column label="确认时间" min-width="160">
              <template #default="scope">{{ formatDateTime(scope.row.confirmedAt, { fallback: '未确认' }) }}</template>
            </el-table-column>
            <el-table-column label="操作" min-width="220" fixed="right">
              <template #default="scope">
                <div class="competition-row-actions">
                  <el-button link type="primary" :icon="View" @click="openDetail(scope.row)">详情</el-button>
                  <el-button v-if="scope.row.permissions?.canEdit" link type="primary" :icon="EditPen" @click="handleEdit(scope.row)">编辑</el-button>
                </div>
              </template>
            </el-table-column>
          </template>

          <template v-else-if="activeTab === 'certificates'">
            <el-table-column label="赛事" prop="contestName" min-width="180" />
            <el-table-column v-if="showStudentColumns" label="学生" prop="studentName" min-width="100" />
            <el-table-column v-if="showStudentColumns" label="学号" prop="studentNo" min-width="120" />
            <el-table-column label="结果状态" width="120"><template #default="scope"><competition-status-tag :value="scope.row.resultStatus" /></template></el-table-column>
            <el-table-column label="证书编号" prop="certificateNo" min-width="160" />
            <el-table-column label="证书归档" min-width="160"><template #default="scope">{{ scope.row.certificateAttachmentName ? '已上传' : '未上传' }}</template></el-table-column>
            <el-table-column label="确认时间" min-width="160">
              <template #default="scope">{{ formatDateTime(scope.row.confirmedAt, { fallback: '未确认' }) }}</template>
            </el-table-column>
            <el-table-column label="操作" min-width="280" fixed="right">
              <template #default="scope">
                <div class="competition-row-actions">
                  <el-button link type="primary" :icon="View" @click="openDetail(scope.row)">详情</el-button>
                  <el-button v-if="scope.row.permissions?.canUploadCertificate" link type="primary" @click="handleCertificate(scope.row)">上传证书</el-button>
                  <el-button v-if="scope.row.permissions?.canPreviewCertificate" link type="primary" @click="handleCertificatePreview(scope.row)">查看证书</el-button>
                  <el-button v-if="scope.row.permissions?.canDownloadCertificate" link type="success" @click="handleCertificateDownload(scope.row)">下载证书</el-button>
                </div>
              </template>
            </el-table-column>
          </template>

          <template v-else>
            <el-table-column label="赛事" prop="contestName" min-width="180" />
            <el-table-column v-if="showStudentColumns" label="学生" prop="studentName" min-width="100" />
            <el-table-column label="结果状态" width="120"><template #default="scope"><competition-status-tag :value="scope.row.resultStatus" /></template></el-table-column>
            <el-table-column label="证书归档" min-width="160"><template #default="scope">{{ scope.row.certificateAttachmentName ? '已上传' : '未上传' }}</template></el-table-column>
            <el-table-column label="确认时间" min-width="160">
              <template #default="scope">{{ formatDateTime(scope.row.confirmedAt, { fallback: '未确认' }) }}</template>
            </el-table-column>
            <el-table-column label="操作" min-width="220" fixed="right">
              <template #default="scope">
                <div class="competition-row-actions">
                  <el-button link type="primary" :icon="View" @click="openDetail(scope.row)">详情</el-button>
                  <el-button v-if="scope.row.permissions?.canPreviewCertificate" link type="primary" @click="handleCertificatePreview(scope.row)">查看证书</el-button>
                  <el-button v-if="scope.row.permissions?.canDownloadCertificate" link type="success" @click="handleCertificateDownload(scope.row)">下载证书</el-button>
                </div>
              </template>
            </el-table-column>
          </template>
        </el-table>
      </div>
      <div class="competition-pagination">
        <pagination v-show="total > 0" :total="total" v-model:page="currentQuery.pageNum" v-model:limit="currentQuery.pageSize" @pagination="getList" />
      </div>
    </el-card>

    <el-dialog v-model="editOpen" :title="editTitle" width="820px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="赛事" prop="contestId"><el-select v-model="editForm.contestId" :disabled="Boolean(editForm.id)" style="width: 100%" filterable><el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="学生" prop="studentId"><el-select v-model="editForm.studentId" :disabled="Boolean(editForm.id)" style="width: 100%" filterable><el-option v-for="item in studentOptions" :key="item.id" :label="`${item.name}（${item.studentNo}）`" :value="item.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="获奖等级"><el-input v-model="editForm.awardLevel" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="结果状态" prop="resultStatus"><el-select v-model="editForm.resultStatus" style="width: 100%"><el-option label="待确认" value="pending" /><el-option label="已获奖" value="awarded" /><el-option label="已参赛" value="participated" /><el-option label="已归档" value="archived" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="成绩分数" prop="score"><el-input v-model="editForm.score" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="名次" prop="ranking"><el-input v-model="editForm.ranking" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="证书编号"><el-input v-model="editForm.certificateNo" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="确认时间"><el-date-picker v-model="editForm.confirmedAt" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="归档备注"><el-input v-model="editForm.archiveRemark" type="textarea" :rows="3" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitEdit">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importOpen" title="批量导入成绩" width="620px" destroy-on-close>
      <el-alert class="competition-dialog-tip" type="info" :closable="false" show-icon title="请先下载模板，按模板列顺序填写后上传 .xlsx 或 .csv 文件。" />
      <el-form :model="importForm" label-width="90px">
        <el-form-item label="模板下载">
          <el-button type="primary" link @click="handleImportTemplate">下载成绩导入模板</el-button>
        </el-form-item>
        <el-form-item label="覆盖已有">
          <el-switch v-model="importForm.overwrite" />
        </el-form-item>
        <el-form-item label="导入文件">
          <upload-dropzone
            v-model="importFiles"
            accept=".xlsx,.csv"
            :file-types="importFileTypes"
            :limit="1"
            title="拖入成绩导入文件，或点击选择"
            description="支持 .xlsx / .csv，导入前请先确认模板列顺序。"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importOpen = false">取消</el-button>
        <el-button type="primary" :loading="importSubmitting" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="certificateOpen" title="证书归档" width="620px" destroy-on-close>
      <el-form :model="certificateForm" label-width="90px">
        <el-form-item label="成绩记录">
          <el-input v-model="certificateForm.resultLabel" disabled />
        </el-form-item>
        <el-form-item label="证书文件" required>
          <upload-dropzone
            v-model="certificateFiles"
            accept=".pdf,.jpg,.jpeg,.png"
            :file-types="certificateFileTypes"
            :limit="1"
            title="拖入证书文件，或点击选择"
            description="支持 PDF、JPG、PNG，上传后会直接进入证书归档。"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="certificateOpen = false">取消</el-button>
        <el-button type="primary" :loading="certificateSubmitting" @click="submitCertificate">确定上传</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailOpen" title="成绩详情" size="54%">
      <div v-loading="detailLoading" class="competition-detail-drawer">
        <div class="competition-status-board" style="margin-bottom: 12px">
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">结果状态</div>
            <div class="competition-status-board__value"><competition-status-tag :value="detail.resultStatus" /></div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">获奖等级</div>
            <div class="competition-status-board__value">{{ detail.awardLevel || '未填写' }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">证书归档</div>
            <div class="competition-status-board__value">{{ detail.certificateAttachmentName ? '已上传' : '未上传' }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">确认时间</div>
            <div class="competition-status-board__value">{{ formatDateTime(detail.confirmedAt, { fallback: '未填写' }) }}</div>
          </div>
        </div>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="赛事">{{ detail.contestName || '—' }}</el-descriptions-item>
          <el-descriptions-item v-if="showStudentColumns" label="学生">{{ detail.studentName || '—' }}</el-descriptions-item>
          <el-descriptions-item v-if="showStudentColumns" label="学号">{{ detail.studentNo || '—' }}</el-descriptions-item>
          <el-descriptions-item v-if="showStudentColumns" label="学院 / 专业">{{ detail.college || '—' }} / {{ detail.major || '—' }}</el-descriptions-item>
          <el-descriptions-item label="获奖等级">{{ detail.awardLevel || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="成绩分数">{{ detail.score ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="名次">{{ detail.ranking ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="证书编号">{{ detail.certificateNo || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatDateTime(detail.updatedAt, { fallback: '未记录' }) }}</el-descriptions-item>
        </el-descriptions>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">证书归档</div>
                <div class="competition-panel__desc">查看证书编号、文件和下载动作</div>
              </div>
            </div>
          </template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="证书编号">{{ detail.certificateNo || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="证书文件">{{ detail.certificateAttachmentName || '未上传' }}</el-descriptions-item>
            <el-descriptions-item label="文件信息">
              {{ detail.certificateAttachmentExt ? `${String(detail.certificateAttachmentExt).toUpperCase()} / ` : '' }}{{ detail.certificateAttachmentSize ? `${Math.max(detail.certificateAttachmentSize / 1024, 1).toFixed(detail.certificateAttachmentSize >= 10 * 1024 ? 0 : 1)} KB` : '大小未记录' }}
              / {{ formatDateTime(detail.certificateUploadedAt, { fallback: '未记录' }) }}
            </el-descriptions-item>
          </el-descriptions>
          <div class="competition-row-actions" style="margin-top: 12px">
            <el-button v-if="detail.permissions?.canUploadCertificate" type="primary" plain @click="handleCertificate(detail)">上传证书</el-button>
            <el-button v-if="detail.permissions?.canPreviewCertificate" type="primary" plain @click="handleCertificatePreview(detail)">查看证书</el-button>
            <el-button v-if="detail.permissions?.canDownloadCertificate" type="success" plain @click="handleCertificateDownload(detail)">下载证书</el-button>
            <el-button v-if="detail.permissions?.canEdit" type="primary" plain @click="handleEdit(detail)">编辑成绩</el-button>
          </div>
        </el-card>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">归档备注</div>
                <div class="competition-panel__desc">补充赛后归档说明</div>
              </div>
            </div>
          </template>
          <div class="competition-detail-text">{{ detail.archiveRemark || '未填写' }}</div>
        </el-card>

        <el-card v-if="detail.registration && canEdit" class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">关联报名</div>
                <div class="competition-panel__desc">赛后记录对应的报名与材料信息</div>
              </div>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="项目名称">{{ detail.registration.projectName || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="报名方向">{{ detail.registration.direction || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="指导老师">{{ detail.registration.instructorName || '未填写' }}</el-descriptions-item>
            <el-descriptions-item label="报名状态"><competition-status-tag :value="detail.registration.finalStatus" /></el-descriptions-item>
            <el-descriptions-item label="材料数">{{ detail.registration.materialCount || 0 }}</el-descriptions-item>
            <el-descriptions-item label="最新审核意见">{{ detail.registration.latestReviewComment || '无' }}</el-descriptions-item>
          </el-descriptions>

          <competition-material-table :materials="detail.registration.materials || []" style="margin-top: 12px" />

          <el-table :data="detail.registration.flowLogs || []" border style="margin-top: 12px">
            <el-table-column label="动作" prop="actionType" min-width="120" />
            <el-table-column label="变更前" prop="beforeStatus" min-width="120" />
            <el-table-column label="变更后" prop="afterStatus" min-width="120" />
            <el-table-column label="原因" prop="reason" min-width="180" show-overflow-tooltip />
            <el-table-column label="操作人" prop="operatorName" min-width="100" />
            <el-table-column label="操作时间" prop="operatedAt" min-width="160" />
          </el-table>
        </el-card>
      </div>
    </el-drawer>
    <competition-file-preview-dialog ref="previewRef" />
  </div>
</template>
