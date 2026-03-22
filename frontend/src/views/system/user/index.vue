<script setup name="User">
import { Delete, Download, EditPen, Key, Plus, Refresh, Search, SwitchButton, Upload, User } from '@element-plus/icons-vue'
import { computed, getCurrentInstance, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listStudents } from '@/api/competition/student'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import CompetitionStatusTag from '@/components/CompetitionStatusTag.vue'
import UploadDropzone from '@/components/UploadDropzone.vue'
import { addUser, changeUserStatus, delUser, getUser, importUsers, listUser, resetUserPwd, updateUser } from '@/api/system/user'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const { proxy } = getCurrentInstance()

const loading = ref(false)
const open = ref(false)
const importOpen = ref(false)
const submitting = ref(false)
const importSubmitting = ref(false)
const total = ref(0)
const userList = ref([])
const roleOptions = ref([])
const studentOptions = ref([])
const uploadFiles = ref([])
const title = ref('新增账号')
const initPassword = ref('Demo123!')
const formRef = ref()

const queryParams = reactive({
  keyword: '',
  roleCode: '',
  status: '',
  pageNum: 1,
  pageSize: 10,
})

const importForm = reactive({
  overwrite: false,
})

const form = reactive({
  userId: undefined,
  userName: '',
  nickName: '',
  password: '',
  phonenumber: '',
  email: '',
  status: '0',
  roleIds: [],
  studentId: undefined,
  studentNo: '',
})

const mobilePattern = /^1\d{10}$/
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const formRules = {
  userName: [{ required: true, message: '请填写登录账号', trigger: 'blur' }],
  nickName: [{ required: true, message: '请填写姓名', trigger: 'blur' }],
  password: [{ validator: validatePassword, trigger: 'blur' }],
  roleIds: [{ required: true, message: '请至少选择一个角色', trigger: 'change' }],
  phonenumber: [{ validator: validateMobile, trigger: 'blur' }],
  email: [{ validator: validateEmail, trigger: 'blur' }],
}

const studentRoleId = computed(() => roleOptions.value.find(item => item.roleKey === 'student')?.roleId)
const isStudentLinkedForm = computed(() => form.roleIds.includes(studentRoleId.value))

const metricCards = computed(() => {
  const currentRows = userList.value
  return [
    { title: '账号总数', value: total.value, desc: '按当前筛选条件统计' },
    { title: '学生账号', value: currentRows.filter(item => item.roleCodes?.includes('student')).length, desc: '由学生档案自动联动' },
    { title: '教师/审核员', value: currentRows.filter(item => item.roleCodes?.some(role => ['teacher', 'reviewer'].includes(role))).length, desc: '手工维护并分配赛事' },
    { title: '停用账号', value: currentRows.filter(item => item.status !== '0').length, desc: '当前页停用数量' },
  ]
})

const pageGuide = computed(() => ({
  eyebrow: 'Account Center',
  title: '学生账号跟学生档案走，教师和审核员在这里统一维护',
  description: '学生新增或导入后会自动生成登录账号；教师和审核员账号在这页维护；赛事页只负责给已有账号分配赛事权限，不再现场造人。',
  note: '注意：学生账号的学号、姓名、手机号和邮箱以“学生档案”为准。要改学生登录信息，请先改学生档案。',
  steps: [
    { step: '1', title: '学生先建档', desc: '在学生管理新增或导入档案后，系统会自动生成学生账号，用户名默认就是学号。' },
    { step: '2', title: '教师和审核员在这里建号', desc: '账号创建时直接给角色，后续赛事页只做负责人和审核人的授权分配。' },
    { step: '3', title: '角色和状态统一在这管理', desc: '停用、重置密码、角色调整都在这里处理，避免散落到各业务页。' },
  ],
  actions: [
    { key: 'create', label: '新增账号', type: 'primary', plain: false },
    { key: 'import', label: '批量导入', type: 'warning' },
    { key: 'export', label: '导出账号', type: 'info' },
  ],
}))

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

function validatePassword(_rule, value, callback) {
  if (form.userId || isStudentLinkedForm.value) {
    callback()
    return
  }
  if (!value) {
    callback(new Error('请填写初始密码'))
    return
  }
  if (String(value).length < 5) {
    callback(new Error('密码长度不能少于 5 位'))
    return
  }
  callback()
}

function formatDateTime(value, fallback = '待补充') {
  return formatBeijingDateTime(value, { fallback, withTime: true, withSeconds: false })
}

function accountStatusLabel(value) {
  return value === '0' ? '启用' : '停用'
}

function roleLabel(row) {
  return row.roleLabel || row.roleNames?.join('、') || '未分配'
}

function resetForm() {
  Object.assign(form, {
    userId: undefined,
    userName: '',
    nickName: '',
    password: initPassword.value,
    phonenumber: '',
    email: '',
    status: '0',
    roleIds: [],
    studentId: undefined,
    studentNo: '',
  })
  nextTick(() => formRef.value?.clearValidate())
}

async function loadStudentOptions() {
  const res = await listStudents({ pageNum: 1, pageSize: 500 })
  studentOptions.value = (res.data.list || []).map(item => ({
    id: item.id,
    studentNo: item.studentNo,
    name: item.name,
    mobile: item.mobile,
    email: item.email,
    status: Number(item.status ?? 1),
    label: `${item.studentNo} / ${item.name}`,
  }))
}

function syncStudentFields(studentId) {
  if (!isStudentLinkedForm.value) return
  const student = studentOptions.value.find(item => item.id === studentId)
  if (!student) return
  form.userName = student.studentNo
  form.nickName = student.name
  form.phonenumber = student.mobile || ''
  form.email = student.email || ''
  form.studentNo = student.studentNo
}

watch(() => form.studentId, (value) => {
  if (!value) return
  syncStudentFields(value)
})

watch(() => [...form.roleIds], (value) => {
  if (!value.includes(studentRoleId.value)) {
    form.studentId = undefined
    form.studentNo = ''
    return
  }
  if (form.studentId) {
    syncStudentFields(form.studentId)
    return
  }
  const firstStudent = studentOptions.value[0]
  if (firstStudent) {
    form.studentId = firstStudent.id
    syncStudentFields(firstStudent.id)
  }
})

async function getList() {
  loading.value = true
  try {
    const res = await listUser({
      pageNum: queryParams.pageNum,
      pageSize: queryParams.pageSize,
      keyword: queryParams.keyword,
      roleCode: queryParams.roleCode,
      status: queryParams.status,
    })
    userList.value = res.rows || []
    total.value = Number(res.total || 0)
  } finally {
    loading.value = false
  }
}

async function loadRoleOptions() {
  const res = await getUser()
  roleOptions.value = res.roles || []
  initPassword.value = res.initPassword || initPassword.value
}

function resetQuery() {
  queryParams.keyword = ''
  queryParams.roleCode = ''
  queryParams.status = ''
  queryParams.pageNum = 1
  getList()
}

async function openDialog(userId) {
  const [userRes] = await Promise.all([
    getUser(userId),
    !studentOptions.value.length ? loadStudentOptions() : Promise.resolve(),
  ])
  roleOptions.value = userRes.roles || []
  initPassword.value = userRes.initPassword || initPassword.value
  resetForm()
  if (userId) {
    const detail = userRes.data || {}
    Object.assign(form, {
      userId: detail.userId,
      userName: detail.userName || '',
      nickName: detail.nickName || '',
      password: '',
      phonenumber: detail.phonenumber || '',
      email: detail.email || '',
      status: detail.status || '0',
      roleIds: detail.roleIds || [],
      studentId: detail.studentId || undefined,
      studentNo: detail.studentNo || '',
    })
    title.value = '编辑账号'
  } else {
    title.value = '新增账号'
    form.password = initPassword.value
  }
  open.value = true
}

function handleAdd() {
  openDialog()
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
  if (action.key === 'export') {
    handleExport()
  }
}

function handleImportOpen() {
  uploadFiles.value = []
  importForm.overwrite = false
  importOpen.value = true
}

function handleExport() {
  proxy.download('system/user/export', {
    keyword: queryParams.keyword,
    roleCode: queryParams.roleCode,
    status: queryParams.status,
  }, `账号列表_${new Date().getTime()}.xlsx`)
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除账号“${row.userName}”吗？`, '删除确认', { type: 'warning' })
  await delUser(row.userId)
  ElMessage.success('账号已删除')
  await getList()
}

async function handleStatus(row) {
  const nextStatus = row.status === '0' ? '1' : '0'
  const actionLabel = nextStatus === '0' ? '启用' : '停用'
  await ElMessageBox.confirm(`确认${actionLabel}账号“${row.userName}”吗？`, '状态确认', { type: 'warning' })
  await changeUserStatus(row.userId, nextStatus)
  ElMessage.success(`账号已${actionLabel}`)
  await getList()
}

async function handleResetPwd(row) {
  const { value } = await ElMessageBox.prompt(`请输入“${row.userName}”的新密码`, '重置密码', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    closeOnClickModal: false,
    inputValue: initPassword.value,
    inputPattern: /^.{5,20}$/,
    inputErrorMessage: '密码长度必须介于 5 和 20 之间',
  })
  await resetUserPwd(row.userId, value)
  ElMessage.success(`密码已重置为：${value}`)
}

async function submitImport() {
  const file = uploadFiles.value[0]?.raw
  if (!file) {
    ElMessage.warning('请先选择导入文件')
    return
  }
  importSubmitting.value = true
  try {
    const payload = new FormData()
    payload.append('file', file)
    const res = await importUsers(payload, importForm.overwrite)
    ElMessage.success('账号导入完成')
    if (res.msg) {
      await ElMessageBox.alert(res.msg, '导入结果', { dangerouslyUseHTMLString: true })
    }
    importOpen.value = false
    await getList()
  } finally {
    importSubmitting.value = false
  }
}

async function submitForm() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    const payload = {
      userId: form.userId,
      userName: form.userName,
      nickName: form.nickName,
      password: form.password || undefined,
      phonenumber: form.phonenumber,
      email: form.email,
      status: form.status,
      roleIds: form.roleIds,
      studentId: form.studentId,
      studentNo: form.studentNo,
    }
    if (form.userId) {
      await updateUser(payload)
      ElMessage.success('账号更新成功')
    } else {
      await addUser(payload)
      ElMessage.success(isStudentLinkedForm.value ? `学生账号已创建，初始密码为 ${initPassword.value}` : '账号创建成功')
    }
    open.value = false
    await getList()
  } finally {
    submitting.value = false
  }
}

function isStudentRow(row) {
  return row.roleCodes?.includes('student')
}

onMounted(async () => {
  await Promise.all([getList(), loadStudentOptions(), loadRoleOptions()])
})
</script>

<template>
  <div class="competition-page">
    <el-card class="competition-control-card" shadow="never">
      <template #header>
        <div class="competition-control-head">
          <div class="competition-control-copy">
            <div class="competition-control-eyebrow">ACCOUNT CENTER</div>
            <div class="competition-control-title">账号管理</div>
            <div class="competition-control-subtitle">统一维护学生、教师和审核员账号，避免在学生页和赛事页重复造人。</div>
          </div>
          <div class="competition-control-actions">
            <el-button type="primary" :icon="Plus" @click="handleAdd">新增账号</el-button>
            <el-button plain :icon="Upload" @click="handleImportOpen">批量导入</el-button>
            <el-button plain :icon="Download" @click="handleExport">导出</el-button>
            <el-button plain :icon="Refresh" @click="getList">刷新</el-button>
          </div>
        </div>
      </template>

      <competition-guide-panel
        :eyebrow="pageGuide.eyebrow"
        :title="pageGuide.title"
        :description="pageGuide.description"
        :note="pageGuide.note"
        :steps="pageGuide.steps"
        :actions="pageGuide.actions"
        @action="handleGuideAction"
      />

      <el-form :model="queryParams" :inline="true" class="competition-filter-form">
        <el-form-item label="关键字">
          <el-input v-model="queryParams.keyword" placeholder="账号/姓名/手机号" clearable @keyup.enter="getList" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="queryParams.roleCode" clearable style="width: 160px">
            <el-option v-for="item in roleOptions" :key="item.roleId" :label="item.roleName" :value="item.roleKey" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="queryParams.status" clearable style="width: 140px">
            <el-option label="启用" value="0" />
            <el-option label="停用" value="1" />
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
              <div class="competition-panel__title">账号列表</div>
              <div class="competition-panel__desc">共 {{ total }} 条记录</div>
            </div>
          </div>
        </div>
      </template>

      <div class="competition-empty-fix">
        <el-table v-loading="loading" :data="userList" border row-key="userId">
          <el-table-column label="登录账号" prop="userName" min-width="140">
            <template #default="scope">
              <div class="account-name">{{ scope.row.userName }}</div>
              <div class="account-subtext">{{ scope.row.accountSourceLabel }}</div>
            </template>
          </el-table-column>
          <el-table-column label="姓名" prop="nickName" min-width="120" />
          <el-table-column label="角色" min-width="180">
            <template #default="scope">
              <div class="account-role-list">
                <el-tag v-for="item in scope.row.roleNames || []" :key="item" size="small" effect="plain">{{ item }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="关联学生" min-width="160">
            <template #default="scope">{{ scope.row.studentNo ? `${scope.row.studentNo} / ${scope.row.studentName}` : '—' }}</template>
          </el-table-column>
          <el-table-column label="联系方式" min-width="180">
            <template #default="scope">
              <div>{{ scope.row.phonenumber || '未填写手机' }}</div>
              <div class="account-subtext">{{ scope.row.email || '未填写邮箱' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="scope">
              <competition-status-tag :value="scope.row.status === '0' ? 'enabled' : 'disabled'">{{ accountStatusLabel(scope.row.status) }}</competition-status-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="160">
            <template #default="scope">{{ formatDateTime(scope.row.createTime) }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="260" fixed="right">
            <template #default="scope">
              <div class="competition-row-actions">
                <el-button link type="primary" :icon="EditPen" @click="openDialog(scope.row.userId)">编辑</el-button>
                <el-button link type="primary" :icon="Key" @click="handleResetPwd(scope.row)">重置密码</el-button>
                <el-button link :type="scope.row.status === '0' ? 'warning' : 'success'" :icon="SwitchButton" @click="handleStatus(scope.row)">
                  {{ scope.row.status === '0' ? '停用' : '启用' }}
                </el-button>
                <el-button v-if="!isStudentRow(scope.row)" link type="danger" :icon="Delete" @click="handleDelete(scope.row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="competition-pagination">
        <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
      </div>
    </el-card>

    <el-dialog v-model="open" :title="title" width="760px" destroy-on-close>
      <el-alert
        class="competition-dialog-tip"
        :title="isStudentLinkedForm ? '学生账号由学生档案驱动，账号名固定为学号；要改姓名、手机号、邮箱，请回到学生管理。' : '教师和审核员账号在这里维护，赛事页只负责从已有账号里分配负责人或审核人。'"
        type="info"
        :closable="false"
        show-icon
      />

      <el-form ref="formRef" :model="form" :rules="formRules" label-width="96px" style="margin-top: 16px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="账号角色" prop="roleIds">
              <el-select v-model="form.roleIds" multiple collapse-tags collapse-tags-tooltip style="width: 100%" placeholder="选择角色">
                <el-option v-for="item in roleOptions" :key="item.roleId" :label="item.roleName" :value="item.roleId" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col v-if="isStudentLinkedForm" :span="12">
            <el-form-item label="关联学生">
              <el-select v-model="form.studentId" filterable style="width: 100%" placeholder="选择学生档案">
                <el-option v-for="item in studentOptions" :key="item.id" :label="item.label" :value="item.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="登录账号" prop="userName">
              <el-input v-model="form.userName" :disabled="isStudentLinkedForm" placeholder="教师/审核员可自定义账号名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓名" prop="nickName">
              <el-input v-model="form.nickName" :disabled="isStudentLinkedForm" />
            </el-form-item>
          </el-col>
          <el-col v-if="!form.userId && !isStudentLinkedForm" :span="12">
            <el-form-item label="初始密码" prop="password">
              <el-input v-model="form.password" show-password />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机号" prop="phonenumber">
              <el-input v-model="form.phonenumber" :disabled="isStudentLinkedForm" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="form.email" :disabled="isStudentLinkedForm" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="账号状态">
              <el-select v-model="form.status" style="width: 100%" :disabled="isStudentLinkedForm">
                <el-option label="启用" value="0" />
                <el-option label="停用" value="1" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col v-if="!form.userId" :span="24">
            <div class="account-dialog-note">默认初始密码：{{ initPassword }}。学生账号新增后会自动与学生档案绑定。</div>
          </el-col>
        </el-row>
      </el-form>

      <template #footer>
        <el-button @click="open = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importOpen" title="批量导入账号" width="620px" destroy-on-close>
      <el-alert
        class="competition-dialog-tip"
        title="教师和审核员账号建议在这里批量导入；学生账号通常随学生档案自动生成。"
        type="info"
        :closable="false"
        show-icon
      />
      <div class="competition-row-actions" style="margin-top: 12px">
        <el-button plain :icon="Download" @click="proxy.download('system/user/importTemplate', {}, `账号导入模板_${new Date().getTime()}.xlsx`)">下载模板</el-button>
      </div>
      <el-form :model="importForm" label-width="90px" style="margin-top: 16px">
        <el-form-item label="覆盖同账号">
          <el-switch v-model="importForm.overwrite" active-text="允许覆盖已有账号" inactive-text="账号重复时报错" />
        </el-form-item>
        <el-form-item label="导入文件">
          <upload-dropzone
            v-model="uploadFiles"
            :file-types="['xlsx', 'xls']"
            title="拖入账号导入文件，或点击选择"
            description="支持 .xlsx 和 .xls。角色列可填写 admin / teacher / reviewer / student。"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importOpen = false">取消</el-button>
        <el-button type="primary" :loading="importSubmitting" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.account-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.account-subtext {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.account-role-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.account-dialog-note {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(64, 158, 255, 0.08);
  color: var(--el-text-color-regular);
  font-size: 13px;
}
</style>
