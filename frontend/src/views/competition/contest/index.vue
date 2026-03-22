<script setup>
import { Delete, Download, EditPen, Histogram, Plus, Promotion, Refresh, Search, Trophy, View } from '@element-plus/icons-vue'
import { computed, getCurrentInstance, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { addContest, getContest, listContestPermissionUsers, listContests, publishContest, removeContestRuleAttachment, updateContest, updateContestStatus, uploadContestRuleAttachment } from '@/api/competition/contest'
import CompetitionFilePreviewDialog from '@/components/CompetitionFilePreviewDialog.vue'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import CompetitionStatusTag from '@/components/CompetitionStatusTag.vue'
import UploadDropzone from '@/components/UploadDropzone.vue'
import useUserStore from '@/store/modules/user'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const { proxy } = getCurrentInstance()
const userStore = useUserStore()
const loading = ref(false)
const detailLoading = ref(false)
const submitting = ref(false)
const open = ref(false)
const detailOpen = ref(false)
const title = ref('新增赛事')
const total = ref(0)
const contestList = ref([])
const detail = ref({ recentRegistrations: [] })
const teacherOptions = ref([])
const reviewerOptions = ref([])
const attachmentFiles = ref([])
const ruleAttachmentRemoved = ref(false)
const previewRef = ref()
const formRef = ref()
const queryParams = reactive({ keyword: '', contestLevel: '', subjectCategory: '', contestYear: '', status: '', pageNum: 1, pageSize: 10 })
const form = reactive({
  id: undefined,
  contestName: '',
  contestLevel: '',
  organizer: '',
  subjectCategory: '',
  undertaker: '',
  targetStudents: '',
  contactName: '',
  contactMobile: '',
  location: '',
  description: '',
  contestYear: '',
  signUpStart: '',
  signUpEnd: '',
  contestDate: '',
  status: 'draft',
  materialRequirements: '',
  quotaLimit: 0,
  ruleAttachmentName: '',
  ruleAttachmentId: undefined,
  managerUserIds: [],
  reviewerUserIds: [],
})

const canCreate = computed(() => Boolean(userStore.capabilities.createContests))
const canAssignPermissions = computed(() => Boolean(userStore.capabilities.assignContestPermissions))
const pageScopeNote = '注意：这页维护的是赛事台账和开放状态，不负责学生报名、材料审核和资格变更。'
const contestGuide = {
  eyebrow: '赛事入口',
  title: '先把赛事建完整，再开放报名和权限',
  desc: '赛事页决定后续所有流程的边界。赛事信息、报名时间、材料要求和权限分工最好在这里一次说明白。',
  steps: [
    { step: '1', title: '先建赛事主档', desc: '填写赛事基本信息、报名时间、材料要求和名额限制。' },
    { step: '2', title: '再设置状态和权限', desc: '确认何时开放报名、谁负责管理、谁参与审核。' },
    { step: '3', title: '最后去跟进报名', desc: '赛事发布后，报名和审核流程分别去对应模块推进。' },
  ],
}
const guideActions = computed(() => (
  canCreate.value
    ? [{ key: 'create', label: '新增赛事', type: 'primary', plain: false }]
    : []
))

const mobilePattern = /^1\d{10}$/
const yearPattern = /^\d{4}$/
const attachmentFileTypes = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg', 'zip', 'rar']

const formRules = {
  contestName: [{ required: true, message: '请填写赛事名称', trigger: 'blur' }],
  contestLevel: [{ required: true, message: '请填写赛事级别', trigger: 'blur' }],
  organizer: [{ required: true, message: '请填写主办单位', trigger: 'blur' }],
  contactMobile: [{ validator: validateMobile, trigger: 'blur' }],
  contestYear: [{ validator: validateYear, trigger: 'blur' }],
  quotaLimit: [{ validator: validateQuota, trigger: 'change' }],
}

function validateMobile(_rule, value, callback) {
  if (!value) {
    callback()
    return
  }
  if (mobilePattern.test(value)) {
    callback()
    return
  }
  callback(new Error('请输入 11 位手机号'))
}

function validateYear(_rule, value, callback) {
  if (!value) {
    callback()
    return
  }
  if (yearPattern.test(String(value))) {
    callback()
    return
  }
  callback(new Error('请输入 4 位年份'))
}

function validateQuota(_rule, value, callback) {
  if (value === '' || value === null || value === undefined) {
    callback(new Error('请填写名额上限'))
    return
  }
  if (Number(value) >= 0) {
    callback()
    return
  }
  callback(new Error('名额上限不能小于 0'))
}

const metricCards = computed(() => ([
  { title: '赛事总数', value: total.value, desc: '按筛选条件统计', icon: Trophy },
  { title: '报名中赛事', value: contestList.value.filter(item => item.status === 'signing_up').length, desc: '当前页开放报名', icon: Promotion },
  { title: '待维护赛事', value: contestList.value.filter(item => ['draft', 'pending_publish', 'reviewing'].includes(item.status)).length, desc: '当前页需进一步处理', icon: EditPen },
  { title: '总名额', value: contestList.value.reduce((sum, item) => sum + Number(item.quotaLimit || 0), 0), desc: '当前页名额汇总', icon: Histogram },
]))

const contestLevels = computed(() => [...new Set(contestList.value.map(item => item.contestLevel).filter(Boolean))])
const categoryOptions = computed(() => [...new Set(contestList.value.map(item => item.subjectCategory).filter(Boolean))])
const yearOptions = computed(() => [...new Set(contestList.value.map(item => item.contestYear).filter(Boolean))])

const hasExistingRuleAttachment = computed(() => Boolean(form.ruleAttachmentId && form.ruleAttachmentName && !ruleAttachmentRemoved.value))

function resetForm() {
  Object.assign(form, {
    id: undefined,
    contestName: '',
    contestLevel: '',
    organizer: '',
    subjectCategory: '',
    undertaker: '',
    targetStudents: '',
    contactName: '',
    contactMobile: '',
    location: '',
    description: '',
    contestYear: '',
    signUpStart: '',
    signUpEnd: '',
    contestDate: '',
    status: 'draft',
    materialRequirements: '',
    quotaLimit: 0,
    ruleAttachmentName: '',
    ruleAttachmentId: undefined,
    managerUserIds: [],
    reviewerUserIds: [],
  })
  attachmentFiles.value = []
  ruleAttachmentRemoved.value = false
  nextTick(() => formRef.value?.clearValidate())
}

async function loadPermissionUsers() {
  if (!canAssignPermissions.value) {
    teacherOptions.value = []
    reviewerOptions.value = []
    return
  }
  const res = await listContestPermissionUsers()
  teacherOptions.value = res.data.teachers || []
  reviewerOptions.value = res.data.reviewers || []
}

async function getList() {
  loading.value = true
  try {
    const res = await listContests(queryParams)
    contestList.value = res.data.list || []
    total.value = Number(res.data.total || 0)
    queryParams.pageNum = Number(res.data.pageNum || queryParams.pageNum)
    queryParams.pageSize = Number(res.data.pageSize || queryParams.pageSize)
  } finally {
    loading.value = false
  }
}

async function openDetail(row) {
  detailOpen.value = true
  detailLoading.value = true
  try {
    const res = await getContest(row.id)
    detail.value = res.data || { recentRegistrations: [] }
  } finally {
    detailLoading.value = false
  }
}

function handleAdd() {
  resetForm()
  title.value = '新增赛事'
  open.value = true
}

function handleGuideAction(action) {
  if (action.key === 'create') {
    handleAdd()
  }
}

function handleUpdate(row) {
  resetForm()
  Object.assign(form, {
    id: row.id,
    contestName: row.contestName || '',
    contestLevel: row.contestLevel || '',
    organizer: row.organizer || '',
    subjectCategory: row.subjectCategory || '',
    undertaker: row.undertaker || '',
    targetStudents: row.targetStudents || '',
    contactName: row.contactName || '',
    contactMobile: row.contactMobile || '',
    location: row.location || '',
    description: row.description || '',
    contestYear: row.contestYear || '',
    signUpStart: row.signUpStart || '',
    signUpEnd: row.signUpEnd || '',
    contestDate: row.contestDate || '',
    status: row.status || 'draft',
    materialRequirements: row.materialRequirements || '',
    quotaLimit: Number(row.quotaLimit || 0),
    ruleAttachmentName: row.ruleAttachmentName || '',
    ruleAttachmentId: row.ruleAttachmentId,
    managerUserIds: row.managerUserIds || [],
    reviewerUserIds: row.reviewerUserIds || [],
  })
  title.value = '编辑赛事'
  open.value = true
}

function resetQuery() {
  queryParams.keyword = ''
  queryParams.contestLevel = ''
  queryParams.subjectCategory = ''
  queryParams.contestYear = ''
  queryParams.status = ''
  queryParams.pageNum = 1
  getList()
}

function formatDateTime(value, fallback = '未记录') {
  return formatBeijingDateTime(value, { fallback, withTime: true, withSeconds: false })
}

function formatFileSize(value) {
  const size = Number(value || 0)
  if (!size) return '大小未记录'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size >= 10 * 1024 ? 0 : 1)} KB`
  return `${(size / (1024 * 1024)).toFixed(size >= 10 * 1024 * 1024 ? 0 : 1)} MB`
}

function markRuleAttachmentRemoved() {
  attachmentFiles.value = []
  ruleAttachmentRemoved.value = true
  form.ruleAttachmentId = undefined
  form.ruleAttachmentName = ''
}

function handleRuleAttachmentDownload(target) {
  const contestId = target?.id || form.id
  const fileName = target?.ruleAttachmentName || form.ruleAttachmentName
  if (!contestId || !fileName) {
    ElMessage.warning('当前赛事还没有规则附件')
    return
  }
  proxy.download(`/api/v1/contests/${contestId}/rule-attachment/download`, {}, fileName)
}

function handleRuleAttachmentPreview(target) {
  const contestId = target?.id || form.id
  const fileName = target?.ruleAttachmentName || form.ruleAttachmentName
  if (!contestId || !fileName) {
    ElMessage.warning('当前赛事还没有规则附件')
    return
  }
  previewRef.value?.open({
    url: `/api/v1/contests/${contestId}/rule-attachment/preview`,
    params: {},
    fileName,
  })
}

async function syncRuleAttachment(contestId) {
  const nextFile = attachmentFiles.value[0]?.raw
  if (nextFile) {
    const payload = new FormData()
    payload.append('file', nextFile)
    await uploadContestRuleAttachment(contestId, payload)
    return
  }
  if (ruleAttachmentRemoved.value) {
    await removeContestRuleAttachment(contestId)
  }
}

async function submitForm() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    const payload = { ...form }
    delete payload.ruleAttachmentName
    delete payload.ruleAttachmentId
    if (!canAssignPermissions.value) {
      delete payload.managerUserIds
      delete payload.reviewerUserIds
    }

    let savedContestId = form.id
    if (form.id) {
      const res = await updateContest(payload)
      savedContestId = res.data.id
    } else {
      const res = await addContest(payload)
      savedContestId = res.data.id
    }

    await syncRuleAttachment(savedContestId)
    ElMessage.success(form.id ? '赛事更新成功' : '赛事新增成功')
    open.value = false
    await getList()
    if (detailOpen.value && detail.value.id === savedContestId) {
      await openDetail({ id: savedContestId })
    }
  } finally {
    submitting.value = false
  }
}

async function handlePublish(row) {
  await ElMessageBox.confirm(`确认发布赛事“${row.contestName}”？`, '发布确认', { type: 'warning' })
  await publishContest(row.id)
  ElMessage.success('赛事发布成功')
  if (detailOpen.value && detail.value.id === row.id) {
    await openDetail(row)
  }
  await getList()
}

async function handleStatus(row, status) {
  const labelMap = { closed: '截止', archived: '归档' }
  await ElMessageBox.confirm(`确认将“${row.contestName}”标记为${labelMap[status]}？`, '状态确认', { type: 'warning' })
  await updateContestStatus(row.id, { status })
  ElMessage.success('赛事状态更新成功')
  if (detailOpen.value && detail.value.id === row.id) {
    await openDetail(row)
  }
  await getList()
}

onMounted(async () => {
  await loadPermissionUsers()
  await getList()
})
</script>

<template>
  <div class="competition-page">
    <el-card class="competition-control-card" shadow="never">
      <template #header>
        <div class="competition-control-head">
          <div class="competition-control-copy">
            <div class="competition-control-eyebrow">Contest Setup</div>
            <div class="competition-control-title">赛事管理</div>
            <div class="competition-control-subtitle">维护赛事配置、授权教师和审核人，教师仅能处理被分配赛事。</div>
          </div>
          <div class="competition-control-actions">
            <el-button v-if="canCreate" type="primary" :icon="Plus" @click="handleAdd">新增赛事</el-button>
            <el-button plain :icon="Refresh" @click="getList">刷新列表</el-button>
          </div>
        </div>
      </template>

      <competition-guide-panel
        :note="pageScopeNote"
        :eyebrow="contestGuide.eyebrow"
        :title="contestGuide.title"
        :description="contestGuide.desc"
        :steps="contestGuide.steps"
        :actions="guideActions"
        @action="handleGuideAction"
      />

      <el-form :model="queryParams" :inline="true" class="competition-filter-form">
        <el-form-item label="关键字"><el-input v-model="queryParams.keyword" placeholder="赛事/主办单位" clearable @keyup.enter="getList" /></el-form-item>
        <el-form-item label="级别">
          <el-select v-model="queryParams.contestLevel" clearable style="width: 140px">
            <el-option v-for="item in contestLevels" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="queryParams.subjectCategory" clearable style="width: 160px">
            <el-option v-for="item in categoryOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="年度">
          <el-select v-model="queryParams.contestYear" clearable style="width: 120px">
            <el-option v-for="item in yearOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="queryParams.status" clearable style="width: 140px">
            <el-option label="草稿" value="draft" />
            <el-option label="待发布" value="pending_publish" />
            <el-option label="报名中" value="signing_up" />
            <el-option label="审核中" value="reviewing" />
            <el-option label="已截止" value="closed" />
            <el-option label="已归档" value="archived" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="getList">搜索</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
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
              <div class="competition-panel__title">赛事列表</div>
              <div class="competition-panel__desc">共 {{ total }} 项赛事</div>
            </div>
          </div>
          <div v-if="canCreate" class="competition-toolbar__right">
            <el-button type="primary" plain :icon="Plus" @click="handleAdd">新增</el-button>
          </div>
        </div>
      </template>
      <div class="competition-empty-fix">
        <el-table v-loading="loading" :data="contestList" border row-key="id">
          <el-table-column label="赛事名称" prop="contestName" min-width="220" />
          <el-table-column label="级别" prop="contestLevel" min-width="100" />
          <el-table-column label="分类" prop="subjectCategory" min-width="120" />
          <el-table-column label="年度" prop="contestYear" width="90" />
          <el-table-column label="负责教师" min-width="180" show-overflow-tooltip>
            <template #default="scope">{{ (scope.row.managerUsers || []).map(item => item.realName).join('、') || '未分配' }}</template>
          </el-table-column>
          <el-table-column label="审核人" min-width="180" show-overflow-tooltip>
            <template #default="scope">{{ (scope.row.reviewerUsers || []).map(item => item.realName).join('、') || '未分配' }}</template>
          </el-table-column>
          <el-table-column label="报名截止" min-width="150">
            <template #default="scope">{{ scope.row.signUpEnd || '未设置' }}</template>
          </el-table-column>
          <el-table-column label="名额上限" prop="quotaLimit" width="100" />
          <el-table-column label="状态" width="120">
            <template #default="scope"><competition-status-tag :value="scope.row.status" /></template>
          </el-table-column>
          <el-table-column label="操作" min-width="300" fixed="right">
            <template #default="scope">
              <div class="competition-row-actions">
                <el-button link type="primary" :icon="View" @click="openDetail(scope.row)">详情</el-button>
                <el-button v-if="scope.row.permissions?.canEdit" link type="primary" :icon="EditPen" @click="handleUpdate(scope.row)">修改</el-button>
                <el-button v-if="scope.row.permissions?.canPublish" link type="success" :icon="Promotion" @click="handlePublish(scope.row)">发布</el-button>
                <el-button v-if="scope.row.permissions?.canClose" link type="warning" @click="handleStatus(scope.row, 'closed')">截止</el-button>
                <el-button v-if="scope.row.permissions?.canArchive" link type="info" @click="handleStatus(scope.row, 'archived')">归档</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="competition-pagination">
        <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
      </div>
    </el-card>

    <el-dialog v-model="open" :title="title" width="920px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="赛事名称" prop="contestName"><el-input v-model="form.contestName" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="赛事级别" prop="contestLevel"><el-input v-model="form.contestLevel" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="赛事分类"><el-input v-model="form.subjectCategory" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="赛事年度" prop="contestYear"><el-input v-model="form.contestYear" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="主办单位" prop="organizer"><el-input v-model="form.organizer" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="承办单位"><el-input v-model="form.undertaker" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="面向对象"><el-input v-model="form.targetStudents" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="比赛地点"><el-input v-model="form.location" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="联系人"><el-input v-model="form.contactName" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="联系电话" prop="contactMobile"><el-input v-model="form.contactMobile" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="报名开始"><el-date-picker v-model="form.signUpStart" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="报名结束"><el-date-picker v-model="form.signUpEnd" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="比赛时间"><el-date-picker v-model="form.contestDate" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="状态"><el-select v-model="form.status" style="width: 100%"><el-option label="草稿" value="draft" /><el-option label="待发布" value="pending_publish" /><el-option label="报名中" value="signing_up" /><el-option label="审核中" value="reviewing" /><el-option label="已截止" value="closed" /><el-option label="已归档" value="archived" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="名额上限" prop="quotaLimit"><el-input-number v-model="form.quotaLimit" :min="0" style="width: 100%" /></el-form-item></el-col>
          <el-col v-if="canAssignPermissions" :span="12">
            <el-form-item label="负责教师">
              <el-select v-model="form.managerUserIds" multiple collapse-tags collapse-tags-tooltip style="width: 100%" placeholder="选择负责教师">
                <el-option v-for="item in teacherOptions" :key="item.userId" :label="item.realName" :value="item.userId" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col v-if="canAssignPermissions" :span="12">
            <el-form-item label="审核人">
              <el-select v-model="form.reviewerUserIds" multiple collapse-tags collapse-tags-tooltip style="width: 100%" placeholder="选择审核人">
                <el-option v-for="item in reviewerOptions" :key="item.userId" :label="item.realName" :value="item.userId" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="规则附件">
              <div style="display: flex; width: 100%; flex-direction: column; gap: 12px;">
                <div v-if="hasExistingRuleAttachment" style="display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border: 1px solid var(--el-border-color-extra-light); border-radius: 12px; background: #f8fbff;">
                  <div style="min-width: 0;">
                    <div class="competition-panel__desc">当前规则附件</div>
                    <div style="margin-top: 4px; font-weight: 600; word-break: break-all;">{{ form.ruleAttachmentName }}</div>
                  </div>
                  <div class="competition-row-actions">
                    <el-button link type="primary" :icon="View" @click="handleRuleAttachmentPreview(form)">查看</el-button>
                    <el-button link type="primary" :icon="Download" @click="handleRuleAttachmentDownload(form)">下载</el-button>
                    <el-button link type="danger" :icon="Delete" @click="markRuleAttachmentRemoved">移除</el-button>
                  </div>
                </div>
                <el-alert v-if="attachmentFiles.length" type="warning" :closable="false" show-icon title="保存后会用新文件替换当前规则附件。" />
                <upload-dropzone
                  v-model="attachmentFiles"
                  :file-types="attachmentFileTypes"
                  title="拖入规则附件，或点击选择"
                  description="支持 PDF、Office 文档、图片和压缩包。保存赛事后会自动上传到规则附件。"
                />
              </div>
            </el-form-item>
          </el-col>
          <el-col :span="24"><el-form-item label="赛事简介"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="材料要求"><el-input v-model="form.materialRequirements" type="textarea" :rows="4" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="open = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailOpen" title="赛事详情" size="52%">
      <div v-loading="detailLoading" class="competition-detail-drawer">
        <div class="competition-status-board" style="margin-bottom: 12px">
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">当前状态</div>
            <div class="competition-status-board__value"><competition-status-tag :value="detail.status" /></div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">名额上限</div>
            <div class="competition-status-board__value">{{ detail.quotaLimit || 0 }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">报名总数</div>
            <div class="competition-status-board__value">{{ detail.registrationCount || 0 }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">通过总数</div>
            <div class="competition-status-board__value">{{ detail.approvedCount || 0 }}</div>
          </div>
        </div>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="赛事名称">{{ detail.contestName || '—' }}</el-descriptions-item>
          <el-descriptions-item label="赛事级别">{{ detail.contestLevel || '—' }}</el-descriptions-item>
          <el-descriptions-item label="赛事分类">{{ detail.subjectCategory || '—' }}</el-descriptions-item>
          <el-descriptions-item label="赛事年度">{{ detail.contestYear || '—' }}</el-descriptions-item>
          <el-descriptions-item label="主办单位">{{ detail.organizer || '—' }}</el-descriptions-item>
          <el-descriptions-item label="承办单位">{{ detail.undertaker || '—' }}</el-descriptions-item>
          <el-descriptions-item label="面向对象">{{ detail.targetStudents || '—' }}</el-descriptions-item>
          <el-descriptions-item label="比赛地点">{{ detail.location || '—' }}</el-descriptions-item>
          <el-descriptions-item label="联系人">{{ detail.contactName || '—' }}</el-descriptions-item>
          <el-descriptions-item label="联系电话">{{ detail.contactMobile || '—' }}</el-descriptions-item>
          <el-descriptions-item label="报名开始">{{ detail.signUpStart || '—' }}</el-descriptions-item>
          <el-descriptions-item label="报名结束">{{ detail.signUpEnd || '—' }}</el-descriptions-item>
          <el-descriptions-item label="比赛时间">{{ detail.contestDate || '—' }}</el-descriptions-item>
          <el-descriptions-item label="负责教师">{{ (detail.managerUsers || []).map(item => item.realName).join('、') || '未分配' }}</el-descriptions-item>
          <el-descriptions-item label="审核人">{{ (detail.reviewerUsers || []).map(item => item.realName).join('、') || '未分配' }}</el-descriptions-item>
          <el-descriptions-item label="规则附件" :span="2">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">
              <div style="display: flex; flex-direction: column; gap: 4px;">
                <span>{{ detail.ruleAttachmentName || '未上传' }}</span>
                <span v-if="detail.ruleAttachmentId" style="font-size: 12px; color: var(--el-text-color-secondary);">
                  {{ detail.ruleAttachmentExt ? `${String(detail.ruleAttachmentExt).toUpperCase()} / ` : '' }}{{ formatFileSize(detail.ruleAttachmentSize) }} / {{ formatDateTime(detail.ruleAttachmentUploadedAt) }}
                </span>
              </div>
              <div style="display: flex; align-items: center; gap: 10px;">
                <el-button v-if="detail.ruleAttachmentId" link type="primary" :icon="View" @click="handleRuleAttachmentPreview(detail)">查看附件</el-button>
                <el-button v-if="detail.ruleAttachmentId" link type="primary" :icon="Download" @click="handleRuleAttachmentDownload(detail)">下载附件</el-button>
              </div>
            </div>
          </el-descriptions-item>
        </el-descriptions>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">赛事简介</div>
                <div class="competition-panel__desc">用于说明赛事背景和组织信息</div>
              </div>
            </div>
          </template>
          <div class="competition-detail-text">{{ detail.description || '未填写' }}</div>
        </el-card>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">材料要求</div>
                <div class="competition-panel__desc">报名阶段提交材料说明</div>
              </div>
            </div>
          </template>
          <div class="competition-detail-text">{{ detail.materialRequirements || '未填写' }}</div>
        </el-card>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">最近报名</div>
                <div class="competition-panel__desc">最近 8 条报名记录</div>
              </div>
            </div>
          </template>
          <el-table :data="detail.recentRegistrations || []" border>
            <el-table-column label="学生" prop="studentName" min-width="100" />
            <el-table-column label="学号" prop="studentNo" min-width="120" />
            <el-table-column label="项目" prop="projectName" min-width="180" show-overflow-tooltip />
            <el-table-column label="审核状态" min-width="120">
              <template #default="scope"><competition-status-tag :value="scope.row.reviewStatus" /></template>
            </el-table-column>
            <el-table-column label="当前状态" min-width="120">
              <template #default="scope"><competition-status-tag :value="scope.row.finalStatus" /></template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </el-drawer>
    <competition-file-preview-dialog ref="previewRef" />
  </div>
</template>
