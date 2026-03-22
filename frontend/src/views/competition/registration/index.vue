<script setup>
import { CircleCheck, DocumentAdd, EditPen, Files, Plus, Refresh, Search, Tickets, WarningFilled } from '@element-plus/icons-vue'
import { computed, getCurrentInstance, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import { listContests } from '@/api/competition/contest'
import { addRegistration, correctionRegistration, getRegistration, importRegistrations, listRegistrations, submitMaterials, updateRegistration, withdrawRegistration } from '@/api/competition/registration'
import { listStudents } from '@/api/competition/student'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import CompetitionMaterialTable from '@/components/CompetitionMaterialTable.vue'
import CompetitionStatusTag from '@/components/CompetitionStatusTag.vue'
import UploadDropzone from '@/components/UploadDropzone.vue'
import useUserStore from '@/store/modules/user'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const { proxy } = getCurrentInstance()
const userStore = useUserStore()
const router = useRouter()

const loading = ref(false)
const submitting = ref(false)
const importSubmitting = ref(false)
const detailLoading = ref(false)
const materialSubmitting = ref(false)
const open = ref(false)
const importOpen = ref(false)
const detailOpen = ref(false)
const materialOpen = ref(false)
const dialogTitle = ref('新增报名')
const total = ref(0)
const contestOptions = ref([])
const studentOptions = ref([])
const registrationList = ref([])
const detail = ref({ materials: [], flowLogs: [] })
const importFiles = ref([])
const materialFiles = ref([])
const materialMode = ref('submit')
const materialTarget = ref(null)
const formRef = ref()
const queryParams = reactive({ keyword: '', contestId: undefined, reviewStatus: '', finalStatus: '', dataQualityStatus: '', sourceType: '', pageNum: 1, pageSize: 10 })
const form = reactive({ id: undefined, contestId: undefined, studentId: undefined, projectName: '', direction: '', teamName: '', instructorName: '', instructorMobile: '', emergencyContact: '', emergencyMobile: '', sourceType: 'online', remark: '' })
const importForm = reactive({ overwrite: true })
const materialForm = reactive({ comment: '提交审核材料' })
const importFileTypes = ['xlsx', 'csv']
const materialFileTypes = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg', 'zip', 'rar']

const phonePattern = /^1\d{10}$/

const formRules = {
  contestId: [{ required: true, message: '请选择赛事', trigger: 'change' }],
  studentId: [{ required: true, message: '请选择学生', trigger: 'change' }],
  projectName: [{ required: true, message: '请填写项目名称', trigger: 'blur' }],
  sourceType: [{ required: true, message: '请选择报名来源', trigger: 'change' }],
  instructorMobile: [{ validator: validatePhone, trigger: 'blur' }],
  emergencyMobile: [{ validator: validatePhone, trigger: 'blur' }],
}

function validatePhone(_rule, value, callback) {
  if (!value) {
    callback()
    return
  }
  if (phonePattern.test(value)) {
    callback()
    return
  }
  callback(new Error('请输入 11 位手机号'))
}

const roleSet = computed(() => new Set(userStore.roles))
const isStudentRole = computed(() => roleSet.value.has('student') && !roleSet.value.has('admin') && !roleSet.value.has('teacher') && !roleSet.value.has('reviewer'))
const isReviewerRole = computed(() => roleSet.value.has('reviewer') && !roleSet.value.has('admin') && !roleSet.value.has('teacher'))
const isTeacherOnlyRole = computed(() => roleSet.value.has('teacher') && !roleSet.value.has('admin'))
const canManageRecords = computed(() => roleSet.value.has('admin') || roleSet.value.has('teacher'))
const canCreateRegistration = computed(() => canManageRecords.value || roleSet.value.has('student'))
const canImport = computed(() => canManageRecords.value)
const canExport = computed(() => canManageRecords.value || roleSet.value.has('reviewer'))
const canVisitReviewPage = computed(() => roleSet.value.has('admin') || roleSet.value.has('reviewer'))
const pageTitle = computed(() => {
  if (isStudentRole.value) return '我的报名'
  if (isReviewerRole.value) return '报名记录'
  return '报名管理'
})
const pageSubtitle = computed(() => {
  if (isStudentRole.value) {
    return '先建报名单，再提交材料；审核结果、补正要求和退赛动作都回到这张列表里处理。'
  }
  if (isReviewerRole.value) {
    return '这页主要用于查报名记录和导出；真正的审核处理请去材料审核。'
  }
  return '这页只负责报名记录、材料提交和导入导出；审核请去材料审核，退赛/换人/补录请去资格管理。'
})
const primaryActionLabel = computed(() => (isStudentRole.value ? '开始报名' : '新建报名记录'))
const tableTitle = computed(() => (isStudentRole.value ? '我的报名记录' : '报名记录总览'))
const tableDesc = computed(() => (isStudentRole.value ? `你当前共有 ${total.value} 条报名记录` : `共 ${total.value} 条报名记录`))
const pageScopeNote = computed(() => {
  if (isStudentRole.value) {
    return '注意：只“新增报名”还不算进入审核。创建记录后，还要回到列表点“提交材料”；如果中途不再参赛，也直接在这张列表里点“退赛”。'
  }
  if (isReviewerRole.value) {
    return '注意：这里看到的是报名台账，不是审核工作台。通过、驳回、退回补正都在“材料审核”页面完成。'
  }
  return '注意：这页只管建记录、补材料、查详情。审核动作在“材料审核”，退赛/换人/补录在“资格管理”。'
})

const roleGuide = computed(() => {
  if (isStudentRole.value) {
    return {
      eyebrow: '学生入口',
      title: '先创建报名，再把材料送进审核',
      desc: '这页对学生负责建单、提交材料、补正和退赛，不需要再单独去找资格管理入口。',
      steps: [
        { step: '1', title: '先建报名单', desc: '填写赛事、项目和联系人。建单后记录才会出现在列表里。' },
        { step: '2', title: '再提交材料', desc: '回到列表点“提交材料”，把这条报名真正送进审核流程。' },
        { step: '3', title: '看结果、补正或退赛', desc: '待补正时点“提交补正”；如果不再参赛，直接在列表里点“退赛”。' },
      ],
    }
  }
  if (isReviewerRole.value) {
    return {
      eyebrow: '审核入口',
      title: '先在这里查记录，真正处理去材料审核',
      desc: '报名管理更像台账。你可以先定位报名、看详情和导出，但审核结论不在这里提交。',
      steps: [
        { step: '1', title: '先筛选报名', desc: '用赛事、状态、关键字快速找到要处理的学生和项目。' },
        { step: '2', title: '打开详情核对材料', desc: '重点看材料列表、最近意见和流转日志，确认上下文。' },
        { step: '3', title: '去材料审核页处理', desc: '通过、驳回、退回补正都在材料审核页完成。' },
      ],
    }
  }
  return {
    eyebrow: '管理入口',
    title: '先建报名记录，再把后续流程分发到对应页面',
    desc: canVisitReviewPage.value
      ? '老师和管理员在这里负责建单、导入、补材料；审核和资格变更分别去对应模块完成。'
      : '教师在这里负责建单、导入和补材料；资格变更去资格管理，审核结论由管理员或审核员在材料审核页处理。',
    steps: [
      { step: '1', title: '建记录或批量导入', desc: '先把学生和赛事关联起来，形成可跟踪的报名记录。' },
      { step: '2', title: '缺材料时在这里补齐', desc: '这页可以编辑报名信息，也可以代学生提交材料和补正。' },
      { step: '3', title: '后续动作去专门页面', desc: canVisitReviewPage.value ? '审核去材料审核，退赛/换人/补录去资格管理。' : '退赛/换人/补录去资格管理；审核问题由管理员或审核员继续处理。' },
    ],
  }
})

const workflowLinks = computed(() => {
  if (canManageRecords.value) {
    const actions = []
    if (canVisitReviewPage.value) {
      actions.push({ label: '去材料审核', path: '/competition/reviews', type: 'primary' })
    }
    actions.push({ label: '去资格管理', path: '/competition/qualifications', type: canVisitReviewPage.value ? 'warning' : 'primary' })
    return actions
  }
  if (isReviewerRole.value) {
    return [
      { label: '去材料审核', path: '/competition/reviews', type: 'primary' },
    ]
  }
  return []
})

const metricCards = computed(() => {
  if (isStudentRole.value) {
    return [
      { title: '我的报名', value: total.value, desc: '你当前创建的报名记录', icon: Tickets },
      { title: '待交材料', value: registrationList.value.filter(item => item.finalStatus === 'submitted').length, desc: '先把材料送进审核', icon: DocumentAdd },
      { title: '待补正', value: registrationList.value.filter(item => item.finalStatus === 'correction_required').length, desc: '按意见补材料', icon: WarningFilled },
      { title: '已通过', value: registrationList.value.filter(item => item.finalStatus === 'approved').length, desc: '主审核流程已完成', icon: CircleCheck },
    ]
  }
  if (isReviewerRole.value) {
    return [
      { title: '记录总数', value: total.value, desc: '按筛选条件统计', icon: Tickets },
      { title: '待审核', value: registrationList.value.filter(item => ['submitted', 'reviewing', 'supplemented'].includes(item.finalStatus)).length, desc: '需要去材料审核继续处理', icon: WarningFilled },
      { title: '待补正', value: registrationList.value.filter(item => item.finalStatus === 'correction_required').length, desc: '等待报名人补材料', icon: EditPen },
      { title: '已结束', value: registrationList.value.filter(item => ['approved', 'rejected', 'withdrawn', 'replaced'].includes(item.finalStatus)).length, desc: '流程已出结论', icon: CircleCheck },
    ]
  }
  return [
    { title: '报名总数', value: total.value, desc: '按筛选条件统计', icon: Tickets },
    { title: '待交材料', value: registrationList.value.filter(item => item.finalStatus === 'submitted').length, desc: '只建了记录，还没送审', icon: DocumentAdd },
    { title: '审核中', value: registrationList.value.filter(item => item.finalStatus === 'reviewing').length, desc: '材料已进入审核流程', icon: WarningFilled },
    { title: '已通过', value: registrationList.value.filter(item => item.finalStatus === 'approved').length, desc: '可进入后续资格管理', icon: CircleCheck },
  ]
})

function formatDateTime(value, options = {}) {
  const { withTime = true, fallback = '待补充' } = options
  return formatBeijingDateTime(value, { fallback, withTime, withSeconds: false })
}

function sourceTypeLabel(value) {
  return { online: '在线填报', import: '批量导入' }[value] || value || '在线填报'
}

function toneTagType(value) {
  return { primary: 'primary', success: 'success', warning: 'warning', danger: 'danger', info: 'info' }[value] || 'info'
}

function registrationGuideInfo(row = {}) {
  const latestComment = row.latestReviewComment || ''
  const canReview = Boolean(row.permissions?.canReview)
  const canCorrection = Boolean(row.permissions?.canCorrection)
  const canSubmitMaterials = Boolean(row.permissions?.canSubmitMaterials)
  const hasRealAttachment = Number(row.attachmentCount || 0) > 0
  const hasMetadataOnlyMaterial = Number(row.metadataOnlyMaterialCount || 0) > 0
  const needsAttachmentRepair = Boolean(row.requiresAttachmentRepair) || hasMetadataOnlyMaterial
  const uploadActionLabel = needsAttachmentRepair ? '补传原件' : '提交材料'

  if (needsAttachmentRepair) {
    return {
      tone: 'danger',
      title: '历史材料缺少原件',
      desc: latestComment || '这条记录里有材料文件名，但后台缺少真实上传文件，当前按脏数据处理。',
      nextStep: canSubmitMaterials
        ? `下一步：点击“${uploadActionLabel}”，把缺失原件补齐后重新送审。`
        : canReview
          ? '下一步：不要直接通过，请先退回补正或驳回。'
          : '下一步：联系负责老师补齐原件后再继续流程。',
    }
  }

  switch (row.finalStatus) {
    case 'submitted':
      return {
        tone: 'warning',
        title: hasMetadataOnlyMaterial && !hasRealAttachment ? '材料名已登记，原件未上传' : '报名单已创建',
        desc: hasMetadataOnlyMaterial && !hasRealAttachment
          ? '这条记录里已经登记过材料文件名，但后台还没有真实原件。'
          : '基础信息已经保存，但这条记录还没进入正式审核。',
        nextStep: canSubmitMaterials ? `下一步：点击“${uploadActionLabel}”，把真实文件送进审核。` : '下一步：等待报名人补齐材料。',
      }
    case 'reviewing':
      return {
        tone: 'primary',
        title: '材料审核中',
        desc: '报名材料已经进入审核流程，当前主要是等待审核结论。',
        nextStep: canReview ? '下一步：去“材料审核”完成通过、驳回或退回补正。' : '下一步：暂时无需操作，等待审核结果。',
      }
    case 'correction_required':
      return {
        tone: 'danger',
        title: '已退回补正',
        desc: latestComment || '审核人要求补材料或修改信息后重新提交。',
        nextStep: canCorrection ? '下一步：点击“提交补正”，补齐材料后再次送审。' : '下一步：等待报名人完成补正后再继续处理。',
      }
    case 'approved':
      return {
        tone: 'success',
        title: '报名已通过',
        desc: '主审核流程已经结束，这条报名现在是有效记录。',
        nextStep: canManageRecords.value ? (isTeacherOnlyRole.value ? '下一步：如需退赛、换人或补录，请去“资格管理”；如需跟进审核上下文，请联系管理员或审核员。' : '下一步：如需退赛、换人或补录，请去“资格管理”。') : (row.permissions?.canWithdraw ? '下一步：等待赛事安排和后续通知；如果不再参赛，可直接点“退赛”。' : '下一步：等待赛事安排和后续通知。'),
      }
    case 'rejected':
      return {
        tone: 'info',
        title: '报名未通过',
        desc: latestComment || '审核已给出驳回结论，这条记录不会继续进入当前流程。',
        nextStep: canManageRecords.value ? '下一步：如需补录或调整人员，请去“资格管理”。' : '下一步：如有疑问，请联系负责老师确认后续安排。',
      }
    case 'supplemented':
      return {
        tone: 'warning',
        title: '补录处理中',
        desc: hasMetadataOnlyMaterial && !hasRealAttachment
          ? '这条补录记录已经登记过材料名，但还缺真实原件。'
          : '这条记录来自资格管理的补录动作，通常还需要补材料再送审。',
        nextStep: canSubmitMaterials ? `下一步：点击“${uploadActionLabel}”，把补录记录重新送进审核。` : canReview ? '下一步：去“材料审核”处理补录材料。' : '下一步：等待补录流程继续推进。',
      }
    case 'withdrawn':
      return {
        tone: 'info',
        title: '已退赛',
        desc: '这条报名记录已经退出当前赛事流程。',
        nextStep: '下一步：流程结束，无需继续在这里处理。',
      }
    case 'replaced':
      return {
        tone: 'info',
        title: '已换人',
        desc: '原报名名额已经转出，后续流程会在新的补录记录中继续。',
        nextStep: '下一步：如果要跟进新学生，请去资格管理查看承接记录。',
      }
    default:
      return {
        tone: 'info',
        title: '流程状态待确认',
        desc: '这条报名记录存在，但当前阶段没有被清晰识别。',
        nextStep: '下一步：先打开详情，核对材料、意见和流转日志。',
      }
  }
}

const tableRows = computed(() => registrationList.value.map(item => ({ ...item, flowGuide: registrationGuideInfo(item) })))
const detailGuide = computed(() => registrationGuideInfo(detail.value || {}))
const materialDialogTitle = computed(() => {
  if (materialMode.value === 'correction') return '提交补正材料'
  if (Boolean(materialTarget.value?.requiresAttachmentRepair) || Number(materialTarget.value?.metadataOnlyMaterialCount || 0) > 0) {
    return '补传报名材料原件'
  }
  return '提交报名材料'
})
const materialDialogDesc = computed(() => (
  materialMode.value === 'correction'
    ? '按审核意见补交文件，支持一次拖入多份补正材料。'
    : Boolean(materialTarget.value?.requiresAttachmentRepair) || Number(materialTarget.value?.metadataOnlyMaterialCount || 0) > 0
      ? `当前记录里仍有 ${Number(materialTarget.value?.metadataOnlyMaterialCount || 0)} 份仅登记文件名的材料；这一步是在补传原件。`
      : '把真实材料文件拖进来提交审核，不再只是手填一个文件名。'
))

function resetForm() {
  Object.assign(form, { id: undefined, contestId: undefined, studentId: undefined, projectName: '', direction: '', teamName: '', instructorName: '', instructorMobile: '', emergencyContact: '', emergencyMobile: '', sourceType: 'online', remark: '' })
  nextTick(() => formRef.value?.clearValidate())
}

function resetImportForm() {
  importForm.overwrite = true
  importFiles.value = []
}

function resetMaterialForm() {
  materialFiles.value = []
  materialTarget.value = null
  materialForm.comment = '提交审核材料'
}

async function loadOptions() {
  const [studentRes, contestRes] = await Promise.all([
    listStudents({ pageSize: 200 }),
    listContests({ pageSize: 200 })
  ])
  studentOptions.value = studentRes.data.list || []
  contestOptions.value = contestRes.data.list || []
  if (isStudentRole.value) {
    form.studentId = Number(userStore.studentId || studentOptions.value[0]?.id || '')
  }
}

async function getList() {
  loading.value = true
  try {
    const res = await listRegistrations(queryParams)
    registrationList.value = res.data.list || []
    total.value = Number(res.data.total || 0)
    queryParams.pageNum = Number(res.data.pageNum || queryParams.pageNum)
    queryParams.pageSize = Number(res.data.pageSize || queryParams.pageSize)
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  queryParams.keyword = ''
  queryParams.contestId = undefined
  queryParams.reviewStatus = ''
  queryParams.finalStatus = ''
  queryParams.dataQualityStatus = ''
  queryParams.sourceType = ''
  queryParams.pageNum = 1
  getList()
}

function go(path) {
  router.push(path)
}

function handleAdd() {
  resetForm()
  if (isStudentRole.value) {
    form.studentId = Number(userStore.studentId || studentOptions.value[0]?.id || '')
  }
  dialogTitle.value = isStudentRole.value ? '发起报名' : '新建报名记录'
  open.value = true
}

function handleEdit(row) {
  resetForm()
  Object.assign(form, {
    id: row.id,
    contestId: row.contestId,
    studentId: row.studentId,
    projectName: row.projectName || '',
    direction: row.direction || '',
    teamName: row.teamName || '',
    instructorName: row.instructorName || '',
    instructorMobile: row.instructorMobile || '',
    emergencyContact: row.emergencyContact || '',
    emergencyMobile: row.emergencyMobile || '',
    sourceType: row.sourceType || 'online',
    remark: row.remark || '',
  })
  dialogTitle.value = '编辑报名'
  open.value = true
}

function handleImportOpen() {
  resetImportForm()
  importOpen.value = true
}

function handleExport(scene, filename) {
  proxy.download('/api/v1/registrations/export', { ...queryParams, scene }, filename)
}

function handleTemplateDownload() {
  proxy.download('/api/v1/registrations/import-template', {}, `报名导入模板_${new Date().getTime()}.xlsx`)
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
    const res = await importRegistrations(payload)
    ElMessage.success(`导入完成：成功 ${res.data.successCount} 条，失败 ${res.data.failCount} 条`)
    if (res.data.failCount) {
      await ElMessageBox.alert(res.data.errors.map(item => `第 ${item.row} 行：${item.message}`).join('<br/>'), '导入失败明细', { dangerouslyUseHTMLString: true })
    }
    importOpen.value = false
    queryParams.pageNum = 1
    await getList()
  } finally {
    importSubmitting.value = false
  }
}

async function submitForm() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    if (form.id) {
      await updateRegistration(form)
      ElMessage.success('报名信息更新成功')
    } else {
      await addRegistration(form)
      ElMessage.success('报名提交成功')
    }
    open.value = false
    await getList()
  } finally {
    submitting.value = false
  }
}

async function handleDetail(row) {
  detailLoading.value = true
  detailOpen.value = true
  try {
    const res = await getRegistration(row.id)
    detail.value = res.data || { materials: [], flowLogs: [] }
  } finally {
    detailLoading.value = false
  }
}

async function handleMaterial(row) {
  resetMaterialForm()
  materialMode.value = 'submit'
  materialTarget.value = row
  materialForm.comment = '提交审核材料'
  materialOpen.value = true
}

async function handleCorrection(row) {
  resetMaterialForm()
  materialMode.value = 'correction'
  materialTarget.value = row
  materialForm.comment = '提交补正材料'
  materialOpen.value = true
}

async function handleWithdraw(row) {
  try {
    const { value } = await ElMessageBox.prompt('退赛后，这条报名会结束并自动通知相关老师。', '确认退赛', {
      inputValue: '主动退赛',
      inputPlaceholder: '请填写退赛原因',
      confirmButtonText: '确认退赛',
      cancelButtonText: '取消',
      inputValidator: (input) => (input && input.trim() ? true : '请填写退赛原因'),
    })
    await withdrawRegistration(row.id, { reason: value.trim() })
    ElMessage.success('退赛处理成功')
    if (detailOpen.value && detail.value.id === row.id) {
      await handleDetail({ id: row.id })
    }
    await getList()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    throw error
  }
}

async function submitMaterialForm() {
  if (!materialTarget.value?.id) return
  const files = materialFiles.value.map(item => item.raw).filter(Boolean)
  if (!files.length) {
    ElMessage.warning('请先上传材料文件')
    return
  }
  materialSubmitting.value = true
  try {
    const payload = new FormData()
    files.forEach(file => payload.append('files', file))
    payload.append('materialType', materialMode.value === 'correction' ? '补正材料' : '报名材料')
    payload.append('comment', materialForm.comment || (materialMode.value === 'correction' ? '提交补正材料' : '提交审核材料'))
    if (materialMode.value === 'correction') {
      await correctionRegistration(materialTarget.value.id, payload)
      ElMessage.success('补正提交成功')
    } else {
      await submitMaterials(materialTarget.value.id, payload)
      ElMessage.success('材料提交成功')
    }
    materialOpen.value = false
    if (detailOpen.value && detail.value.id === materialTarget.value.id) {
      await handleDetail(materialTarget.value)
    }
    await getList()
  } finally {
    materialSubmitting.value = false
  }
}

function canEditRow(row) {
  return Boolean(row.permissions?.canEdit)
}

function canSubmitMaterial(row) {
  return Boolean(row.permissions?.canSubmitMaterials)
}

function canCorrectionRow(row) {
  return Boolean(row.permissions?.canCorrection)
}

function canWithdrawRow(row) {
  return Boolean(row.permissions?.canWithdraw)
}

function materialActionLabel(row) {
  return Boolean(row.requiresAttachmentRepair) || Number(row.metadataOnlyMaterialCount || 0) > 0 ? '补传原件' : '提交材料'
}

onMounted(async () => {
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
            <div class="competition-control-eyebrow">Registration Flow</div>
            <div class="competition-control-title">{{ pageTitle }}</div>
            <div class="competition-control-subtitle">{{ pageSubtitle }}</div>
          </div>
          <div class="competition-control-actions">
            <el-button v-if="canCreateRegistration" type="primary" :icon="Plus" @click="handleAdd">{{ primaryActionLabel }}</el-button>
            <el-button v-if="canImport" plain :icon="DocumentAdd" @click="handleImportOpen">批量导入</el-button>
            <el-button plain :icon="Refresh" @click="getList">刷新列表</el-button>
          </div>
        </div>
      </template>

      <competition-guide-panel
        :note="pageScopeNote"
        :eyebrow="roleGuide.eyebrow"
        :title="roleGuide.title"
        :description="roleGuide.desc"
        :steps="roleGuide.steps"
        :actions="workflowLinks"
        @action="go($event.path)"
      />

      <el-form :model="queryParams" :inline="true" class="competition-filter-form">
        <el-form-item label="关键字"><el-input v-model="queryParams.keyword" placeholder="学生/赛事/项目名称" clearable @keyup.enter="getList" /></el-form-item>
        <el-form-item label="赛事">
          <el-select v-model="queryParams.contestId" clearable style="width: 180px">
            <el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="审核状态">
          <el-select v-model="queryParams.reviewStatus" clearable style="width: 140px">
            <el-option label="待处理" value="pending" />
            <el-option label="审核中" value="reviewing" />
            <el-option label="待补正" value="correction_required" />
            <el-option label="已通过" value="approved" />
            <el-option label="已驳回" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item label="当前状态">
          <el-select v-model="queryParams.finalStatus" clearable style="width: 140px">
            <el-option label="已提交" value="submitted" />
            <el-option label="审核中" value="reviewing" />
            <el-option label="待补正" value="correction_required" />
            <el-option label="已通过" value="approved" />
            <el-option label="已驳回" value="rejected" />
            <el-option label="已退赛" value="withdrawn" />
            <el-option label="已替换" value="replaced" />
            <el-option label="补录中" value="supplemented" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据质量">
          <el-select v-model="queryParams.dataQualityStatus" clearable style="width: 130px">
            <el-option label="正常" value="clean" />
            <el-option label="脏数据" value="dirty" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="queryParams.sourceType" clearable style="width: 120px">
            <el-option label="在线" value="online" />
            <el-option label="导入" value="import" />
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
              <div class="competition-panel__title">{{ tableTitle }}</div>
              <div class="competition-panel__desc">{{ tableDesc }}</div>
            </div>
          </div>
          <div class="competition-toolbar__right">
            <el-button v-if="canImport" plain :icon="DocumentAdd" @click="handleTemplateDownload">模板</el-button>
            <el-button v-if="canExport" type="warning" plain :icon="Files" @click="handleExport('registration_list', `报名名单_${new Date().getTime()}.xlsx`)">导出名单</el-button>
            <el-button v-if="canExport" type="warning" plain :icon="Files" @click="handleExport('review_results', `审核结果_${new Date().getTime()}.xlsx`)">导出审核</el-button>
            <el-button v-if="canExport" type="info" plain :icon="Files" @click="handleExport('pending_materials', `待补材料_${new Date().getTime()}.xlsx`)">待补清单</el-button>
          </div>
        </div>
      </template>
      <div class="competition-empty-fix">
        <el-table v-loading="loading" :data="tableRows" border row-key="id">
          <el-table-column label="赛事" prop="contestName" min-width="180" />
          <el-table-column v-if="!isStudentRole" label="学生" prop="studentName" min-width="110" />
          <el-table-column label="项目名称" prop="projectName" min-width="180" show-overflow-tooltip />
          <el-table-column v-if="!isStudentRole" label="来源" width="110">
            <template #default="scope">{{ sourceTypeLabel(scope.row.sourceType) }}</template>
          </el-table-column>
          <el-table-column label="材料数" width="90" align="center">
            <template #default="scope">{{ scope.row.materialCount || 0 }}</template>
          </el-table-column>
          <el-table-column label="当前进度" min-width="250">
            <template #default="scope">
              <div class="registration-process">
                <div class="registration-process__head">
                  <div class="registration-process__title">{{ scope.row.flowGuide.title }}</div>
                  <el-tag :type="toneTagType(scope.row.flowGuide.tone)" effect="light">{{ scope.row.flowGuide.tone === 'success' ? '已完成' : scope.row.flowGuide.tone === 'danger' ? '需处理' : scope.row.flowGuide.tone === 'warning' ? '待推进' : '处理中' }}</el-tag>
                </div>
                <div class="registration-process__tags">
                  <competition-status-tag :value="scope.row.reviewStatus" />
                  <competition-status-tag :value="scope.row.finalStatus" />
                  <el-tag v-if="scope.row.dataQualityStatus === 'dirty'" type="danger" effect="light">脏数据</el-tag>
                </div>
                <div class="registration-process__desc">{{ scope.row.flowGuide.desc }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="建议下一步" min-width="240">
            <template #default="scope">
              <div class="registration-next-step" :class="`is-${scope.row.flowGuide.tone}`">{{ scope.row.flowGuide.nextStep }}</div>
            </template>
          </el-table-column>
          <el-table-column label="提交时间" min-width="160">
            <template #default="scope">{{ formatDateTime(scope.row.submitTime, { fallback: '未提交' }) }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="320" fixed="right">
            <template #default="scope">
              <div class="competition-row-actions">
                <el-button link type="primary" @click="handleDetail(scope.row)">详情</el-button>
                <el-button v-if="canEditRow(scope.row)" link type="primary" :icon="EditPen" @click="handleEdit(scope.row)">编辑</el-button>
                <el-button v-if="canSubmitMaterial(scope.row)" link type="success" @click="handleMaterial(scope.row)">{{ materialActionLabel(scope.row) }}</el-button>
                <el-button v-if="canCorrectionRow(scope.row)" link type="warning" @click="handleCorrection(scope.row)">提交补正</el-button>
                <el-button v-if="canWithdrawRow(scope.row)" link type="danger" @click="handleWithdraw(scope.row)">退赛</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="competition-pagination">
        <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
      </div>
    </el-card>

    <el-dialog v-model="open" :title="dialogTitle" width="860px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="赛事" prop="contestId">
              <el-select v-model="form.contestId" :disabled="Boolean(form.id)" style="width: 100%" filterable>
                <el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="学生" prop="studentId">
              <el-select v-model="form.studentId" :disabled="Boolean(form.id) || isStudentRole" style="width: 100%" filterable>
                <el-option v-for="item in studentOptions" :key="item.id" :label="`${item.name}（${item.studentNo}）`" :value="item.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12"><el-form-item label="项目名称" prop="projectName"><el-input v-model="form.projectName" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="报名方向"><el-input v-model="form.direction" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="队伍名称"><el-input v-model="form.teamName" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="来源" prop="sourceType"><el-select v-model="form.sourceType" style="width: 100%"><el-option label="在线" value="online" /><el-option label="导入" value="import" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="指导老师"><el-input v-model="form.instructorName" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="导师电话" prop="instructorMobile"><el-input v-model="form.instructorMobile" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="紧急联系人"><el-input v-model="form.emergencyContact" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="紧急电话" prop="emergencyMobile"><el-input v-model="form.emergencyMobile" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="3" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="open = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importOpen" title="批量导入报名" width="620px" destroy-on-close>
      <el-alert class="competition-dialog-tip" type="info" :closable="false" show-icon title="请先下载模板，按模板列顺序填写后上传 .xlsx 或 .csv 文件。" />
      <el-form :model="importForm" label-width="90px">
        <el-form-item label="模板下载">
          <el-button type="primary" link @click="handleTemplateDownload">下载报名导入模板</el-button>
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
            title="拖入报名导入文件，或点击选择"
            description="支持 .xlsx / .csv，系统会按模板列顺序进行校验。"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importOpen = false">取消</el-button>
        <el-button type="primary" :loading="importSubmitting" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="materialOpen" :title="materialDialogTitle" width="620px" destroy-on-close>
      <el-alert
        class="competition-dialog-tip"
        type="info"
        :closable="false"
        show-icon
        :title="materialTarget ? `${materialTarget.studentName || '当前报名'} / ${materialTarget.contestName}` : materialDialogTitle"
      />
      <el-form :model="materialForm" label-width="90px">
        <el-form-item label="材料文件" required>
          <upload-dropzone
            v-model="materialFiles"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar"
            :file-types="materialFileTypes"
            :limit="5"
            multiple
            :title="materialDialogTitle"
            :description="materialDialogDesc"
          />
        </el-form-item>
        <el-form-item label="提交说明">
          <el-input
            v-model="materialForm.comment"
            type="textarea"
            :rows="3"
            :placeholder="materialMode === 'correction' ? '例如：按审核意见补交成绩单和证明材料' : '例如：首次提交报名材料'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="materialOpen = false">取消</el-button>
        <el-button type="primary" :loading="materialSubmitting" @click="submitMaterialForm">确认上传</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailOpen" title="报名详情" size="52%">
      <div v-loading="detailLoading" class="competition-detail-drawer">
        <div class="competition-status-board" style="margin-bottom: 12px">
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">审核状态</div>
            <div class="competition-status-board__value"><competition-status-tag :value="detail.reviewStatus" /></div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">当前状态</div>
            <div class="competition-status-board__value"><competition-status-tag :value="detail.finalStatus" /></div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">材料数量</div>
            <div class="competition-status-board__value">{{ (detail.materials || []).length }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">流转次数</div>
            <div class="competition-status-board__value">{{ (detail.flowLogs || []).length }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">数据质量</div>
            <div class="competition-status-board__value">
              <el-tag :type="detail.dataQualityStatus === 'dirty' ? 'danger' : 'success'" effect="light">
                {{ detail.dataQualityStatus === 'dirty' ? '脏数据' : '正常' }}
              </el-tag>
            </div>
          </div>
        </div>

        <el-alert
          class="registration-detail-alert"
          :type="detailGuide.tone === 'danger' ? 'error' : detailGuide.tone"
          :closable="false"
          show-icon
        >
          <template #title>{{ detailGuide.title }}</template>
          {{ detailGuide.nextStep }}
        </el-alert>

        <el-alert
          v-if="detail.dataQualityStatus === 'dirty'"
          style="margin-top: 12px"
          type="error"
          :closable="false"
          show-icon
          title="当前记录已按脏数据处理"
          :description="(detail.dataQualityIssues || []).map(item => item.message).join('；') || '存在仅登记文件名、未上传原件的材料。'"
        />

        <div v-if="canSubmitMaterial(detail) || canCorrectionRow(detail) || canWithdrawRow(detail)" class="registration-detail-actions">
          <el-button v-if="canSubmitMaterial(detail)" type="success" plain @click="handleMaterial(detail)">{{ materialActionLabel(detail) }}</el-button>
          <el-button v-if="canCorrectionRow(detail)" type="warning" plain @click="handleCorrection(detail)">提交补正</el-button>
          <el-button v-if="canWithdrawRow(detail)" type="danger" plain @click="handleWithdraw(detail)">退赛</el-button>
        </div>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="赛事">{{ detail.contestName }}</el-descriptions-item>
          <el-descriptions-item label="学生">{{ detail.studentName }}</el-descriptions-item>
          <el-descriptions-item label="学号">{{ detail.studentNo || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="项目名称">{{ detail.projectName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="报名方向">{{ detail.direction || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="队伍名称">{{ detail.teamName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="指导老师">{{ detail.instructorName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="导师电话">{{ detail.instructorMobile || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="紧急联系人">{{ detail.emergencyContact || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="紧急电话">{{ detail.emergencyMobile || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ sourceTypeLabel(detail.sourceType) }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ formatDateTime(detail.submitTime, { fallback: '未提交' }) }}</el-descriptions-item>
          <el-descriptions-item label="最近意见" :span="2">{{ detail.latestReviewComment || '无' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ detail.remark || '无' }}</el-descriptions-item>
        </el-descriptions>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">材料列表</div>
                <div class="competition-panel__desc">{{ detail.dataQualityStatus === 'dirty' ? '以下材料里有记录名，但并不是每份都有真实原件。' : '当前报名已提交材料。' }}</div>
              </div>
            </div>
          </template>
          <el-empty v-if="!(detail.materials || []).length" description="暂无材料" />
          <competition-material-table v-else :materials="detail.materials || []" />
        </el-card>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">流转日志</div>
                <div class="competition-panel__desc">保留状态变化和处理原因</div>
              </div>
            </div>
          </template>
          <el-empty v-if="!(detail.flowLogs || []).length" description="暂无流转记录" />
          <el-timeline v-else>
            <el-timeline-item v-for="item in detail.flowLogs || []" :key="item.id" :timestamp="formatDateTime(item.operatedAt, { fallback: '未记录' })">
              {{ item.actionType }}：{{ item.beforeStatus || '无' }} → {{ item.afterStatus || '无' }}
              <div>{{ item.reason || '无说明' }}</div>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.registration-process {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.registration-process__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.registration-process__title {
  min-width: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.registration-process__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.registration-process__desc {
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
}

.registration-next-step {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--el-border-color-extra-light);
  background: linear-gradient(180deg, #ffffff, #f7f9fc);
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.registration-next-step.is-primary {
  border-color: rgba(64, 158, 255, 0.18);
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.08), rgba(255, 255, 255, 0.96));
}

.registration-next-step.is-success {
  border-color: rgba(103, 194, 58, 0.18);
  background: linear-gradient(135deg, rgba(103, 194, 58, 0.08), rgba(255, 255, 255, 0.96));
}

.registration-next-step.is-warning {
  border-color: rgba(230, 162, 60, 0.22);
  background: linear-gradient(135deg, rgba(230, 162, 60, 0.09), rgba(255, 255, 255, 0.96));
}

.registration-next-step.is-danger {
  border-color: rgba(245, 108, 108, 0.22);
  background: linear-gradient(135deg, rgba(245, 108, 108, 0.09), rgba(255, 255, 255, 0.96));
}

.registration-next-step.is-info {
  border-color: rgba(144, 147, 153, 0.18);
  background: linear-gradient(135deg, rgba(144, 147, 153, 0.08), rgba(255, 255, 255, 0.96));
}

.registration-detail-alert {
  margin-bottom: 12px;
  border-radius: 14px;
}

.registration-detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0 0 12px;
}
</style>
