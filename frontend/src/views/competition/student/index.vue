<script setup>
import { Collection, Download, EditPen, Files, OfficeBuilding, Plus, Refresh, School, Search, SwitchButton, User, View } from '@element-plus/icons-vue'
import { computed, getCurrentInstance, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { addStudent, getStudent, importStudents, listStudentImportRecords, listStudents, updateStudent, updateStudentStatus } from '@/api/competition/student'
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
const importSubmitting = ref(false)
const importRecordLoading = ref(false)
const open = ref(false)
const detailOpen = ref(false)
const importOpen = ref(false)
const importRecordOpen = ref(false)
const title = ref('新增学生')
const total = ref(0)
const importTotal = ref(0)
const studentList = ref([])
const importRecordList = ref([])
const detail = ref({ recentRegistrations: [], recentResults: [] })
const importFiles = ref([])
const formRef = ref()
const queryParams = reactive({ keyword: '', college: '', grade: '', hasExperience: undefined, status: undefined, pageNum: 1, pageSize: 10 })
const importQueryParams = reactive({ pageNum: 1, pageSize: 8 })
const importForm = reactive({ overwrite: true })
const form = reactive({
  id: undefined,
  studentNo: '',
  name: '',
  gender: '未知',
  college: '',
  major: '',
  className: '',
  grade: '',
  advisorName: '',
  mobile: '',
  email: '',
  historyExperience: '',
  remark: '',
  status: 1,
})

const mobilePattern = /^1\d{10}$/
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const importFileTypes = ['xlsx', 'csv']

const canManageStudents = computed(() => userStore.roles.includes('admin'))

const formRules = {
  studentNo: [{ required: true, message: '请填写学号', trigger: 'blur' }],
  name: [{ required: true, message: '请填写姓名', trigger: 'blur' }],
  college: [{ required: true, message: '请填写学院', trigger: 'blur' }],
  major: [{ required: true, message: '请填写专业', trigger: 'blur' }],
  className: [{ required: true, message: '请填写班级', trigger: 'blur' }],
  mobile: [{ validator: validateMobile, trigger: 'blur' }],
  email: [{ validator: validateEmail, trigger: 'blur' }],
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

function validateEmail(_rule, value, callback) {
  if (!value) {
    callback()
    return
  }
  if (emailPattern.test(value)) {
    callback()
    return
  }
  callback(new Error('请输入正确邮箱'))
}

const metricCards = computed(() => {
  const colleges = new Set(studentList.value.map(item => item.college).filter(Boolean))
  return [
    { title: '学生总数', value: total.value, desc: '按筛选条件统计', icon: User },
    { title: '学院覆盖', value: colleges.size, desc: '当前页学院数量', icon: OfficeBuilding },
    { title: '已建账号', value: studentList.value.filter(item => item.hasLoginAccount).length, desc: '当前页已生成登录账号', icon: Collection },
    { title: '有参赛经历', value: studentList.value.filter(item => item.hasHistoryExperience).length, desc: '当前页有履历学生', icon: School },
  ]
})

const pageScopeNote = computed(() => (
  canManageStudents.value
    ? '注意：这里维护的是参赛学生档案，支持单条维护和批量导入；学生档案一旦创建，系统会自动生成对应学生账号。'
    : '注意：这里展示的是参赛学生档案，不在这页创建报名。档案信息会被报名、审核和赛后归档反复复用。'
))

const studentGuide = computed(() => {
  if (canManageStudents.value) {
    return {
      eyebrow: '档案入口',
      title: '先建单条档案或批量导入，再回头核对联动记录',
      desc: '学生档案是报名、审核、成绩归档和统计的公共底座，学号、学院、专业和联系方式最好一开始就录准。',
      steps: [
        { step: '1', title: '先新增或批量导入', desc: '少量档案直接新增，整批学生优先用模板导入，减少重复手填。' },
        { step: '2', title: '系统自动生成学生账号', desc: '学生账号用户名默认就是学号，状态会跟着学生档案同步。' },
        { step: '3', title: '最后回看详情和联动', desc: '详情里可以直接看到登录账号、最近报名和赛后记录。' },
      ],
    }
  }
  return {
    eyebrow: '档案入口',
    title: '先看清学生档案，再回到报名和赛后流程',
    desc: '这页更适合查档案完整度和学生联动记录，不适合直接做报名或审核动作。',
    steps: [
      { step: '1', title: '先查学生基础信息', desc: '优先确认学号、学院、专业和班级是否准确。' },
      { step: '2', title: '再看履历和联系方式', desc: '联系方式和历史经历能帮助判断后续跟进方式。' },
      { step: '3', title: '最后看联动记录', desc: '详情里可以继续追踪最近报名和赛后结果。' },
    ],
  }
})

const guideActions = computed(() => {
  if (!canManageStudents.value) return []
  return [
    { key: 'create', label: '新增学生', type: 'primary', plain: false },
    { key: 'import', label: '批量导入', type: 'warning' },
    { key: 'records', label: '导入记录', type: 'info' },
  ]
})

const collegeOptions = computed(() => [...new Set(studentList.value.map(item => item.college).filter(Boolean))])
const gradeOptions = computed(() => [...new Set(studentList.value.map(item => item.grade).filter(Boolean))])

function statusLabel(value) {
  return Number(value) === 1 ? '启用' : '停用'
}

function formatDateTime(value, options = {}) {
  const { withTime = true, fallback = '待补充' } = options
  return formatBeijingDateTime(value, { fallback, withTime, withSeconds: false })
}

function formatFileSize(size = 0) {
  if (!size) return '未记录大小'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function resetForm() {
  Object.assign(form, {
    id: undefined,
    studentNo: '',
    name: '',
    gender: '未知',
    college: '',
    major: '',
    className: '',
    grade: '',
    advisorName: '',
    mobile: '',
    email: '',
    historyExperience: '',
    remark: '',
    status: 1,
  })
  nextTick(() => formRef.value?.clearValidate())
}

function resetImportForm() {
  importForm.overwrite = true
  importFiles.value = []
}

async function getList() {
  loading.value = true
  try {
    const res = await listStudents(queryParams)
    studentList.value = res.data.list || []
    total.value = Number(res.data.total || 0)
    queryParams.pageNum = Number(res.data.pageNum || queryParams.pageNum)
    queryParams.pageSize = Number(res.data.pageSize || queryParams.pageSize)
  } finally {
    loading.value = false
  }
}

async function getImportRecords() {
  if (!canManageStudents.value) return
  importRecordLoading.value = true
  try {
    const res = await listStudentImportRecords(importQueryParams)
    importRecordList.value = res.data.list || []
    importTotal.value = Number(res.data.total || 0)
    importQueryParams.pageNum = Number(res.data.pageNum || importQueryParams.pageNum)
    importQueryParams.pageSize = Number(res.data.pageSize || importQueryParams.pageSize)
  } finally {
    importRecordLoading.value = false
  }
}

async function openDetail(row) {
  detailOpen.value = true
  detailLoading.value = true
  try {
    const res = await getStudent(row.id)
    detail.value = res.data || { recentRegistrations: [], recentResults: [] }
  } finally {
    detailLoading.value = false
  }
}

function handleAdd() {
  resetForm()
  title.value = '新增学生'
  open.value = true
}

function handleImportOpen() {
  resetImportForm()
  importOpen.value = true
}

async function handleOpenImportRecords() {
  importRecordOpen.value = true
  importQueryParams.pageNum = 1
  await getImportRecords()
}

function handleGuideAction(action) {
  if (action.key === 'create') {
    handleAdd()
    return
  }
  if (action.key === 'import') {
    handleImportOpen()
    return
  }
  if (action.key === 'records') {
    handleOpenImportRecords()
  }
}

function handleUpdate(row) {
  resetForm()
  Object.assign(form, {
    id: row.id,
    studentNo: row.studentNo,
    name: row.name,
    gender: row.gender || '未知',
    college: row.college || '',
    major: row.major || '',
    className: row.className || '',
    grade: row.grade || '',
    advisorName: row.advisorName || '',
    mobile: row.mobile || '',
    email: row.email || '',
    historyExperience: row.historyExperience || '',
    remark: row.remark || '',
    status: Number(row.status ?? 1),
  })
  title.value = '编辑学生'
  open.value = true
}

function resetQuery() {
  queryParams.keyword = ''
  queryParams.college = ''
  queryParams.grade = ''
  queryParams.hasExperience = undefined
  queryParams.status = undefined
  queryParams.pageNum = 1
  getList()
}

function handleImportTemplate() {
  proxy.download('/api/v1/students/import-template', {}, `学生导入模板_${new Date().getTime()}.xlsx`)
}

async function handleStatus(row, status) {
  const actionLabel = Number(status) === 1 ? '启用' : '停用'
  await ElMessageBox.confirm(`确认${actionLabel}学生“${row.name}”吗？`, '状态确认', { type: 'warning' })
  await updateStudentStatus(row.id, { status })
  ElMessage.success(`学生已${actionLabel}`)
  if (detailOpen.value && detail.value.id === row.id) {
    await openDetail(row)
  }
  await getList()
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
    const res = await importStudents(payload)
    ElMessage.success(`导入完成：成功 ${res.data.successCount} 条，失败 ${res.data.failCount} 条`)
    if (res.data.failCount) {
      await ElMessageBox.alert(res.data.errors.map(item => `第 ${item.row} 行：${item.message}`).join('<br/>'), '导入失败明细', { dangerouslyUseHTMLString: true })
    }
    importOpen.value = false
    queryParams.pageNum = 1
    importQueryParams.pageNum = 1
    await Promise.all([getList(), getImportRecords()])
  } finally {
    importSubmitting.value = false
  }
}

async function submitForm() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    if (form.id) {
      const res = await updateStudent(form)
      ElMessage.success(res.data?.loginAccount ? `学生更新成功，账号同步为 ${res.data.loginAccount}` : '学生更新成功')
    } else {
      const res = await addStudent(form)
      ElMessage.success(res.data?.loginAccount ? `学生新增成功，已自动生成账号 ${res.data.loginAccount}` : '学生新增成功')
    }
    open.value = false
    await getList()
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await getList()
})
</script>

<template>
  <div class="competition-page">
    <el-card class="competition-control-card" shadow="never">
      <template #header>
        <div class="competition-control-head">
          <div class="competition-control-copy">
            <div class="competition-control-eyebrow">Student Directory</div>
            <div class="competition-control-title">学生管理</div>
            <div class="competition-control-subtitle">维护学生档案信息，用于报名、审核、赛后归档和统计分析。</div>
          </div>
          <div class="competition-control-actions">
            <el-button v-if="canManageStudents" type="primary" :icon="Plus" @click="handleAdd">新增学生</el-button>
            <el-button v-if="canManageStudents" plain :icon="Files" @click="handleImportOpen">批量导入</el-button>
            <el-button v-if="canManageStudents" plain :icon="Collection" @click="handleOpenImportRecords">导入记录</el-button>
            <el-button plain :icon="Refresh" @click="getList">刷新列表</el-button>
          </div>
        </div>
      </template>

      <competition-guide-panel
        :note="pageScopeNote"
        :eyebrow="studentGuide.eyebrow"
        :title="studentGuide.title"
        :description="studentGuide.desc"
        :steps="studentGuide.steps"
        :actions="guideActions"
        @action="handleGuideAction"
      />

      <el-form :model="queryParams" :inline="true" class="competition-filter-form">
        <el-form-item label="关键字">
          <el-input v-model="queryParams.keyword" placeholder="学号/姓名/专业" clearable @keyup.enter="getList" />
        </el-form-item>
        <el-form-item label="学院">
          <el-select v-model="queryParams.college" clearable style="width: 180px">
            <el-option v-for="item in collegeOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级">
          <el-select v-model="queryParams.grade" clearable style="width: 140px">
            <el-option v-for="item in gradeOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="经历">
          <el-select v-model="queryParams.hasExperience" clearable style="width: 150px">
            <el-option label="有参赛经历" :value="true" />
            <el-option label="无参赛经历" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="queryParams.status" clearable style="width: 140px">
            <el-option label="启用" :value="1" />
            <el-option label="停用" :value="0" />
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
              <div class="competition-panel__title">学生档案列表</div>
              <div class="competition-panel__desc">共 {{ total }} 条记录</div>
            </div>
          </div>
          <div class="competition-toolbar__right">
            <el-button v-if="canManageStudents" type="primary" plain :icon="Plus" @click="handleAdd">新增</el-button>
            <el-button v-if="canManageStudents" plain :icon="Files" @click="handleImportOpen">批量导入</el-button>
          </div>
        </div>
      </template>
      <div class="competition-empty-fix">
        <el-table v-loading="loading" :data="studentList" border row-key="id">
          <el-table-column label="学号" prop="studentNo" min-width="120" />
          <el-table-column label="姓名" prop="name" min-width="90" />
          <el-table-column label="登录账号" min-width="150">
            <template #default="scope">
              <div>{{ scope.row.loginAccount || '未生成' }}</div>
              <div class="competition-panel__desc">{{ scope.row.accountSourceLabel || '等待同步' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="学院" prop="college" min-width="140" />
          <el-table-column label="专业" prop="major" min-width="140" />
          <el-table-column label="班级" prop="className" min-width="140" />
          <el-table-column label="年级" prop="grade" min-width="100" />
          <el-table-column label="状态" width="100">
            <template #default="scope">
              <competition-status-tag :value="Number(scope.row.status) === 1 ? 'enabled' : 'disabled'">{{ statusLabel(scope.row.status) }}</competition-status-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="230" fixed="right">
            <template #default="scope">
              <div class="competition-row-actions">
                <el-button link type="primary" :icon="View" @click="openDetail(scope.row)">详情</el-button>
                <el-button v-if="scope.row.permissions?.canEdit" link type="primary" :icon="EditPen" @click="handleUpdate(scope.row)">修改</el-button>
                <el-button v-if="scope.row.permissions?.canEnable" link type="success" :icon="SwitchButton" @click="handleStatus(scope.row, 1)">启用</el-button>
                <el-button v-if="scope.row.permissions?.canDisable" link type="warning" :icon="SwitchButton" @click="handleStatus(scope.row, 0)">停用</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="competition-pagination">
        <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
      </div>
    </el-card>

    <el-dialog v-model="open" :title="title" width="860px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="学号" prop="studentNo"><el-input v-model="form.studentNo" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="姓名" prop="name"><el-input v-model="form.name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="性别"><el-select v-model="form.gender" style="width: 100%"><el-option label="男" value="男" /><el-option label="女" value="女" /><el-option label="未知" value="未知" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="学院" prop="college"><el-input v-model="form.college" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="专业" prop="major"><el-input v-model="form.major" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="班级" prop="className"><el-input v-model="form.className" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="年级"><el-input v-model="form.grade" placeholder="如 2022级" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="导师"><el-input v-model="form.advisorName" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="手机" prop="mobile"><el-input v-model="form.mobile" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="邮箱" prop="email"><el-input v-model="form.email" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="状态"><el-select v-model="form.status" style="width: 100%"><el-option label="启用" :value="1" /><el-option label="停用" :value="0" /></el-select></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="历史经历"><el-input v-model="form.historyExperience" type="textarea" :rows="3" placeholder="填写历史参赛或获奖情况" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="open = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importOpen" title="批量导入学生" width="620px" destroy-on-close>
      <el-alert class="competition-dialog-tip" type="info" :closable="false" show-icon title="请先下载模板，按模板列顺序填写后上传 .xlsx 或 .csv 文件。" />
      <div class="competition-row-actions" style="margin: 12px 0 0">
        <el-button plain :icon="Download" @click="handleImportTemplate">下载导入模板</el-button>
      </div>
      <el-form :model="importForm" label-width="90px" style="margin-top: 16px">
        <el-form-item label="覆盖同学号">
          <el-switch v-model="importForm.overwrite" active-text="允许覆盖已有档案" inactive-text="已有档案时报错" />
        </el-form-item>
        <el-form-item label="导入文件">
          <upload-dropzone
            v-model="importFiles"
            :file-types="importFileTypes"
            title="拖入学生档案文件，或点击选择"
            description="支持 .xlsx 和 .csv。建议先用模板整理学号、学院、专业、班级这些核心字段。"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importOpen = false">取消</el-button>
        <el-button type="primary" :loading="importSubmitting" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="importRecordOpen" title="学生导入记录" size="52%">
      <div class="competition-detail-drawer">
        <el-card class="competition-page__panel" shadow="never">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">导入任务列表</div>
                <div class="competition-panel__desc">回看每次学生批量导入的源文件、结果和执行时间。</div>
              </div>
              <div class="competition-row-actions">
                <el-button plain :icon="Refresh" @click="getImportRecords">刷新记录</el-button>
              </div>
            </div>
          </template>
          <div class="competition-empty-fix">
            <el-table v-loading="importRecordLoading" :data="importRecordList" border>
              <el-table-column label="任务状态" width="120">
                <template #default="scope">
                  <competition-status-tag :value="scope.row.status" />
                </template>
              </el-table-column>
              <el-table-column label="源文件" min-width="220">
                <template #default="scope">
                  <div>{{ scope.row.sourceFileName || '未记录源文件' }}</div>
                  <div class="competition-panel__desc">{{ formatFileSize(scope.row.sourceFileSize) }}</div>
                </template>
              </el-table-column>
              <el-table-column label="导入结果" min-width="160">
                <template #default="scope">成功 {{ scope.row.successCount || 0 }} 条 / 失败 {{ scope.row.failCount || 0 }} 条</template>
              </el-table-column>
              <el-table-column label="操作人" prop="createdByName" min-width="120" />
              <el-table-column label="导入时间" min-width="160">
                <template #default="scope">{{ formatDateTime(scope.row.createdAt, { fallback: '未记录' }) }}</template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!importRecordLoading && !importRecordList.length" description="还没有学生导入记录" />
          </div>
          <div class="competition-pagination">
            <pagination v-show="importTotal > 0" :total="importTotal" v-model:page="importQueryParams.pageNum" v-model:limit="importQueryParams.pageSize" @pagination="getImportRecords" />
          </div>
        </el-card>
      </div>
    </el-drawer>

    <el-drawer v-model="detailOpen" title="学生详情" size="48%">
      <div v-loading="detailLoading" class="competition-detail-drawer">
        <div class="competition-status-board" style="margin-bottom: 12px">
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">档案状态</div>
            <div class="competition-status-board__value">{{ statusLabel(detail.status) }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">参赛次数</div>
            <div class="competition-status-board__value">{{ detail.participationCount || 0 }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">获奖次数</div>
            <div class="competition-status-board__value">{{ detail.awardCount || 0 }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">履历状态</div>
            <div class="competition-status-board__value">{{ detail.historyExperience ? '已填写' : '未填写' }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">账号状态</div>
            <div class="competition-status-board__value">{{ detail.accountStatusLabel || '未生成' }}</div>
          </div>
        </div>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="学号">{{ detail.studentNo || '—' }}</el-descriptions-item>
          <el-descriptions-item label="姓名">{{ detail.name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="登录账号">{{ detail.loginAccount || '—' }}</el-descriptions-item>
          <el-descriptions-item label="账号来源">{{ detail.accountSourceLabel || '—' }}</el-descriptions-item>
          <el-descriptions-item label="性别">{{ detail.gender || '—' }}</el-descriptions-item>
          <el-descriptions-item label="学院">{{ detail.college || '—' }}</el-descriptions-item>
          <el-descriptions-item label="专业">{{ detail.major || '—' }}</el-descriptions-item>
          <el-descriptions-item label="班级">{{ detail.className || '—' }}</el-descriptions-item>
          <el-descriptions-item label="年级">{{ detail.grade || '—' }}</el-descriptions-item>
          <el-descriptions-item label="指导老师">{{ detail.advisorName || '—' }}</el-descriptions-item>
          <el-descriptions-item label="联系方式">{{ detail.mobile || '—' }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ detail.email || '—' }}</el-descriptions-item>
        </el-descriptions>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">参赛履历</div>
                <div class="competition-panel__desc">记录历史参赛和获奖说明</div>
              </div>
            </div>
          </template>
          <div class="competition-detail-text">{{ detail.historyExperience || '未填写' }}</div>
        </el-card>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">备注</div>
                <div class="competition-panel__desc">用于补充档案维护说明</div>
              </div>
            </div>
          </template>
          <div class="competition-detail-text">{{ detail.remark || '未填写' }}</div>
        </el-card>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">最近报名</div>
                <div class="competition-panel__desc">最近 5 条报名记录</div>
              </div>
            </div>
          </template>
          <el-table :data="detail.recentRegistrations || []" border>
            <el-table-column label="赛事" prop="contestName" min-width="180" />
            <el-table-column label="项目" prop="projectName" min-width="140" show-overflow-tooltip />
            <el-table-column label="审核状态" min-width="120">
              <template #default="scope"><competition-status-tag :value="scope.row.reviewStatus" /></template>
            </el-table-column>
            <el-table-column label="当前状态" min-width="120">
              <template #default="scope"><competition-status-tag :value="scope.row.finalStatus" /></template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">最近成绩</div>
                <div class="competition-panel__desc">最近 5 条赛后记录</div>
              </div>
            </div>
          </template>
          <el-table :data="detail.recentResults || []" border>
            <el-table-column label="赛事" min-width="160">
              <template #default="scope">{{ scope.row.contestName || `赛事 #${scope.row.contestId}` }}</template>
            </el-table-column>
            <el-table-column label="获奖等级" prop="awardLevel" min-width="120" />
            <el-table-column label="结果状态" min-width="120">
              <template #default="scope"><competition-status-tag :value="scope.row.resultStatus" /></template>
            </el-table-column>
            <el-table-column label="证书编号" prop="certificateNo" min-width="160" />
          </el-table>
        </el-card>
      </div>
    </el-drawer>
  </div>
</template>
