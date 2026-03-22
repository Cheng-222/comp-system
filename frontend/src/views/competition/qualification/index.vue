<script setup>
import { EditPen, Refresh, Search, Switch, UserFilled, View, WarningFilled } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listContests } from '@/api/competition/contest'
import { getRegistration, listRegistrations, replaceRegistration, supplementRegistration, withdrawRegistration } from '@/api/competition/registration'
import CompetitionMaterialTable from '@/components/CompetitionMaterialTable.vue'
import { listStudents } from '@/api/competition/student'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import CompetitionStatusTag from '@/components/CompetitionStatusTag.vue'
import useUserStore from '@/store/modules/user'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const userStore = useUserStore()
const loading = ref(false)
const detailLoading = ref(false)
const total = ref(0)
const registrationList = ref([])
const contestOptions = ref([])
const studentOptions = ref([])
const detail = ref({ materials: [], flowLogs: [] })
const detailOpen = ref(false)
const queryParams = reactive({ keyword: '', contestId: undefined, reviewStatus: '', finalStatus: '', qualificationOnly: true, pageNum: 1, pageSize: 10 })

const canOperate = computed(() => Boolean(userStore.capabilities.manageQualifications))

const metricCards = computed(() => ([
  { title: '有效名单', value: registrationList.value.filter(item => item.finalStatus === 'approved').length, desc: '当前页最终通过记录', icon: UserFilled },
  { title: '待补录', value: registrationList.value.filter(item => ['rejected', 'withdrawn', 'replaced'].includes(item.finalStatus)).length, desc: '可进入补录的记录', icon: EditPen },
  { title: '补录中', value: registrationList.value.filter(item => item.finalStatus === 'supplemented').length, desc: '等待再次审核的流转记录', icon: Switch },
  { title: '待处理状态', value: registrationList.value.filter(item => ['submitted', 'reviewing', 'correction_required'].includes(item.finalStatus)).length, desc: '仍在主流程中的记录', icon: WarningFilled },
]))

const pageScopeNote = '注意：这页处理的是退赛、换人、补录等资格变更，不负责主审核结论。'
const qualificationGuide = {
  eyebrow: '资格工作台',
  title: '先确认主流程状态，再处理退赛、换人或补录',
  desc: '资格动作会直接影响最终名单，操作前先看最近意见、材料和流转记录，避免在主审核未结束时提前变更。',
  steps: [
    { step: '1', title: '先筛出要变更的记录', desc: '优先看已通过、已驳回、已退赛、已替换和补录中的报名。' },
    { step: '2', title: '打开详情确认上下文', desc: '核对最近审核意见、材料范围和历史流转，确认为什么要变更。' },
    { step: '3', title: '再执行资格动作', desc: '退赛、换人、补录都要写明原因，方便后续名单追溯。' },
  ],
}

function formatDateTime(value, options = {}) {
  const { withTime = true, fallback = '待补充' } = options
  return formatBeijingDateTime(value, { fallback, withTime, withSeconds: false })
}

async function loadOptions() {
  const [contestRes, studentRes] = await Promise.all([
    listContests({ pageSize: 200 }),
    listStudents({ pageSize: 200 }),
  ])
  contestOptions.value = contestRes.data.list || []
  studentOptions.value = studentRes.data.list || []
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
  queryParams.pageNum = 1
  getList()
}

async function openDetail(row) {
  detailOpen.value = true
  detailLoading.value = true
  try {
    const res = await getRegistration(row.id)
    detail.value = res.data || { materials: [], flowLogs: [] }
  } finally {
    detailLoading.value = false
  }
}

async function handleWithdraw(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入退赛原因', '退赛处理', { inputPlaceholder: '例如：时间冲突' })
    if (!value) return
    await withdrawRegistration(row.id, { reason: value })
    ElMessage.success('退赛处理成功')
    await getList()
  } catch {
    return
  }
}

async function handleSupplement(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入补录说明', '补录处理', { inputPlaceholder: '例如：候补转正' })
    if (!value) return
    await supplementRegistration(row.id, { reason: value })
    ElMessage.success('补录处理成功')
    await getList()
  } catch {
    return
  }
}

async function handleReplace(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入替换学生学号', '换人处理', { inputPlaceholder: '例如：20260002' })
    if (!value) return
    const replacement = studentOptions.value.find(item => item.studentNo === value.trim())
    if (!replacement) {
      ElMessage.warning('未找到对应学号的学生')
      return
    }
    if (replacement.id === row.studentId) {
      ElMessage.warning('替换学生不能与当前学生相同')
      return
    }
    await replaceRegistration(row.id, { replacementStudentId: replacement.id, reason: `换人为 ${replacement.name}` })
    ElMessage.success('换人处理成功')
    await getList()
  } catch {
    return
  }
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
            <div class="competition-control-eyebrow">Qualification Flow</div>
            <div class="competition-control-title">资格管理</div>
            <div class="competition-control-subtitle">处理退赛、换人、补录、有效名单和状态流转记录。</div>
          </div>
          <div class="competition-control-actions">
            <el-button plain :icon="Refresh" @click="getList">刷新列表</el-button>
          </div>
        </div>
      </template>

      <competition-guide-panel
        :note="pageScopeNote"
        :eyebrow="qualificationGuide.eyebrow"
        :title="qualificationGuide.title"
        :description="qualificationGuide.desc"
        :steps="qualificationGuide.steps"
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
              <div class="competition-panel__title">资格流转列表</div>
              <div class="competition-panel__desc">共 {{ total }} 条记录</div>
            </div>
          </div>
        </div>
      </template>
      <div class="competition-empty-fix">
        <el-table v-loading="loading" :data="registrationList" border row-key="id">
          <el-table-column label="赛事" prop="contestName" min-width="180" />
          <el-table-column label="学生" prop="studentName" min-width="100" />
          <el-table-column label="项目名称" prop="projectName" min-width="180" show-overflow-tooltip />
          <el-table-column label="当前状态" width="120"><template #default="scope"><competition-status-tag :value="scope.row.finalStatus" /></template></el-table-column>
          <el-table-column label="审核状态" width="120"><template #default="scope"><competition-status-tag :value="scope.row.reviewStatus" /></template></el-table-column>
          <el-table-column label="最近意见" min-width="180" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.latestReviewComment || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="260" fixed="right">
            <template #default="scope">
              <div class="competition-row-actions">
                <el-button link type="primary" :icon="View" @click="openDetail(scope.row)">详情</el-button>
                <el-button v-if="canOperate && scope.row.permissions?.canWithdraw" link type="warning" @click="handleWithdraw(scope.row)">退赛</el-button>
                <el-button v-if="canOperate && scope.row.permissions?.canReplace" link type="danger" @click="handleReplace(scope.row)">换人</el-button>
                <el-button v-if="canOperate && scope.row.permissions?.canSupplement" link type="success" @click="handleSupplement(scope.row)">补录</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="competition-pagination">
        <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
      </div>
    </el-card>

    <el-drawer v-model="detailOpen" title="资格详情" size="52%">
      <div v-loading="detailLoading" class="competition-detail-drawer">
        <div class="competition-status-board" style="margin-bottom: 12px">
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">当前状态</div>
            <div class="competition-status-board__value"><competition-status-tag :value="detail.finalStatus" /></div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">审核状态</div>
            <div class="competition-status-board__value"><competition-status-tag :value="detail.reviewStatus" /></div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">材料数量</div>
            <div class="competition-status-board__value">{{ (detail.materials || []).length }}</div>
          </div>
          <div class="competition-status-board__item">
            <div class="competition-status-board__label">流转次数</div>
            <div class="competition-status-board__value">{{ (detail.flowLogs || []).length }}</div>
          </div>
        </div>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="赛事">{{ detail.contestName }}</el-descriptions-item>
          <el-descriptions-item label="学生">{{ detail.studentName }}</el-descriptions-item>
          <el-descriptions-item label="学号">{{ detail.studentNo || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="项目名称">{{ detail.projectName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="队伍名称">{{ detail.teamName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="指导老师">{{ detail.instructorName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="最近意见" :span="2">{{ detail.latestReviewComment || '无' }}</el-descriptions-item>
        </el-descriptions>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">材料列表</div>
                <div class="competition-panel__desc">辅助判断退赛、换人、补录影响范围</div>
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
                <div class="competition-panel__desc">查看资格变更历史</div>
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
