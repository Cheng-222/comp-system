<script setup>
import { CircleCheck, Document, EditPen, Refresh, Search, View, WarningFilled } from '@element-plus/icons-vue'
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { listContests } from '@/api/competition/contest'
import { getRegistration, listRegistrations, reviewRegistration } from '@/api/competition/registration'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import CompetitionMaterialTable from '@/components/CompetitionMaterialTable.vue'
import CompetitionStatusTag from '@/components/CompetitionStatusTag.vue'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const loading = ref(false)
const detailLoading = ref(false)
const submitting = ref(false)
const total = ref(0)
const registrationList = ref([])
const contestOptions = ref([])
const detailOpen = ref(false)
const reviewOpen = ref(false)
const reviewTitle = ref('审核处理')
const detail = ref({ materials: [], flowLogs: [] })
const currentRow = ref(null)
const reviewFormRef = ref()

const queryParams = reactive({
  keyword: '',
  contestId: undefined,
  reviewStatus: '',
  finalStatus: '',
  dataQualityStatus: '',
  pageNum: 1,
  pageSize: 10,
  queueOnly: true,
})

const reviewForm = reactive({
  registrationId: undefined,
  action: '',
  comment: '',
})

const reviewRules = {
  comment: [{ required: true, message: '请填写审核意见', trigger: 'blur' }],
}

const summaryCards = computed(() => ([
  { title: '审核队列', value: total.value, desc: '按服务端筛选后的任务总数', icon: Document, color: '#409EFF' },
  { title: '待处理', value: registrationList.value.filter(item => item.reviewStatus === 'pending').length, desc: '当前页待进入审核', icon: WarningFilled, color: '#E6A23C' },
  { title: '审核中', value: registrationList.value.filter(item => item.reviewStatus === 'reviewing').length, desc: '当前页审核进行中', icon: EditPen, color: '#8E44AD' },
  { title: '脏数据', value: registrationList.value.filter(item => item.dataQualityStatus === 'dirty').length, desc: '当前页缺少真实原件', icon: CircleCheck, color: '#F56C6C' },
]))

const pageScopeNote = '注意：这页只负责给出审核结论，不负责新建报名、补材料或处理退赛换人。'
const reviewGuide = {
  eyebrow: '审核工作台',
  title: '先核对材料，再给出通过、补正或驳回结论',
  desc: '审核前先打开详情看材料清单、最近意见和流转日志，避免只看状态标签就下结论。',
  steps: [
    { step: '1', title: '先定位任务', desc: '用赛事、审核状态和关键字筛出当前要处理的报名。' },
    { step: '2', title: '再看详情和材料', desc: '重点核对材料数量、审核意见和流转记录是否完整。' },
    { step: '3', title: '最后提交结论', desc: '通过、退回补正、驳回都在这页完成，意见要写清楚。' },
  ],
}

function formatDateTime(value, options = {}) {
  const { withTime = true, fallback = '待补充' } = options
  return formatBeijingDateTime(value, { fallback, withTime, withSeconds: false })
}

function resetQuery() {
  queryParams.keyword = ''
  queryParams.contestId = undefined
  queryParams.reviewStatus = ''
  queryParams.finalStatus = ''
  queryParams.dataQualityStatus = ''
  queryParams.pageNum = 1
  getList()
}

function resetReviewForm() {
  Object.assign(reviewForm, { registrationId: undefined, action: '', comment: '' })
  nextTick(() => reviewFormRef.value?.clearValidate())
}

async function loadContests() {
  const res = await listContests({ pageSize: 200 })
  contestOptions.value = res.data.list || []
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

async function openDetail(row) {
  detailOpen.value = true
  detailLoading.value = true
  currentRow.value = row
  try {
    const res = await getRegistration(row.id)
    detail.value = res.data || { materials: [], flowLogs: [] }
  } finally {
    detailLoading.value = false
  }
}

function canApprove(row) {
  return Boolean(row.permissions?.canApprove)
}

function canCorrection(row) {
  return Boolean(row.permissions?.canReview) && ['submitted', 'reviewing', 'correction_required', 'supplemented'].includes(row.finalStatus)
}

function canReject(row) {
  return Boolean(row.permissions?.canReview) && Number(row.materialCount || 0) > 0
}

function openReviewDialog(row, action) {
  resetReviewForm()
  currentRow.value = row
  reviewForm.registrationId = row.id
  reviewForm.action = action
  reviewTitle.value = { approve: '审核通过', reject: '审核驳回', correction_required: '退回补正' }[action] || '审核处理'
  reviewOpen.value = true
}

async function submitReview() {
  await reviewFormRef.value?.validate()
  submitting.value = true
  try {
    await reviewRegistration(reviewForm.registrationId, { action: reviewForm.action, comment: reviewForm.comment })
    ElMessage.success(`${reviewTitle.value}成功`)
    reviewOpen.value = false
    if (detailOpen.value && currentRow.value?.id === reviewForm.registrationId) {
      await openDetail(currentRow.value)
    }
    await getList()
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await loadContests()
  await getList()
})
</script>

<template>
  <div class="competition-page">
    <el-card class="competition-control-card" shadow="never">
      <template #header>
        <div class="competition-control-head">
          <div class="competition-control-copy">
            <div class="competition-control-eyebrow">Material Review</div>
            <div class="competition-control-title">材料审核</div>
            <div class="competition-control-subtitle">按审核队列分页处理报名材料、补正和驳回任务。</div>
          </div>
          <div class="competition-control-actions">
            <el-button type="primary" :icon="Refresh" @click="getList">刷新队列</el-button>
          </div>
        </div>
      </template>

      <competition-guide-panel
        :note="pageScopeNote"
        :eyebrow="reviewGuide.eyebrow"
        :title="reviewGuide.title"
        :description="reviewGuide.desc"
        :steps="reviewGuide.steps"
      />

      <el-form :model="queryParams" :inline="true" class="competition-filter-form">
        <el-form-item label="关键字">
          <el-input v-model="queryParams.keyword" placeholder="赛事/学生/学号/项目名称" clearable @keyup.enter="getList" />
        </el-form-item>
        <el-form-item label="赛事">
          <el-select v-model="queryParams.contestId" clearable style="width: 200px">
            <el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="审核状态">
          <el-select v-model="queryParams.reviewStatus" clearable style="width: 140px">
            <el-option label="待处理" value="pending" />
            <el-option label="审核中" value="reviewing" />
            <el-option label="待补正" value="correction_required" />
          </el-select>
        </el-form-item>
        <el-form-item label="当前状态">
          <el-select v-model="queryParams.finalStatus" clearable style="width: 140px">
            <el-option label="已提交" value="submitted" />
            <el-option label="审核中" value="reviewing" />
            <el-option label="待补正" value="correction_required" />
            <el-option label="补录中" value="supplemented" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据质量">
          <el-select v-model="queryParams.dataQualityStatus" clearable style="width: 130px">
            <el-option label="正常" value="clean" />
            <el-option label="脏数据" value="dirty" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="getList">筛选</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <div class="competition-summary-strip">
        <div v-for="item in summaryCards" :key="item.title" class="competition-summary-chip">
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
              <div class="competition-panel__title">审核任务列表</div>
              <div class="competition-panel__desc">服务端分页结果，共 {{ total }} 条任务</div>
            </div>
          </div>
        </div>
      </template>

      <div class="competition-empty-fix">
        <el-table v-loading="loading" :data="registrationList" border row-key="id">
          <el-table-column label="赛事" prop="contestName" min-width="180" />
          <el-table-column label="学生" prop="studentName" min-width="100" />
          <el-table-column label="学号" prop="studentNo" min-width="120" />
          <el-table-column label="项目名称" prop="projectName" min-width="180" show-overflow-tooltip />
          <el-table-column label="材料数" prop="materialCount" width="90" />
          <el-table-column label="审核状态" width="120">
            <template #default="scope"><competition-status-tag :value="scope.row.reviewStatus" /></template>
          </el-table-column>
          <el-table-column label="当前状态" width="120">
            <template #default="scope"><competition-status-tag :value="scope.row.finalStatus" /></template>
          </el-table-column>
          <el-table-column label="提交时间" min-width="160">
            <template #default="scope">{{ formatDateTime(scope.row.submitTime, { fallback: '未提交' }) }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="280" fixed="right">
            <template #default="scope">
              <div class="competition-row-actions">
                <el-button link type="primary" :icon="View" @click="openDetail(scope.row)">详情</el-button>
                <el-button v-if="canApprove(scope.row)" link type="success" @click="openReviewDialog(scope.row, 'approve')">通过</el-button>
                <el-button v-if="canCorrection(scope.row)" link type="warning" @click="openReviewDialog(scope.row, 'correction_required')">补正</el-button>
                <el-button v-if="canReject(scope.row)" link type="danger" @click="openReviewDialog(scope.row, 'reject')">驳回</el-button>
                <el-tag v-if="scope.row.dataQualityStatus === 'dirty'" type="danger" effect="light">缺原件</el-tag>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="competition-pagination">
        <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
      </div>
    </el-card>

    <el-drawer v-model="detailOpen" title="审核详情" size="52%">
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
          v-if="detail.dataQualityStatus === 'dirty'"
          type="error"
          style="margin-bottom: 12px"
          :closable="false"
          show-icon
          title="当前记录缺少真实材料原件"
          :description="(detail.dataQualityIssues || []).map(item => item.message).join('；') || '请先退回补正或等待补传原件，不要直接审核通过。'"
        />

        <el-descriptions :column="2" border>
          <el-descriptions-item label="赛事">{{ detail.contestName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="学生">{{ detail.studentName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="学号">{{ detail.studentNo || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="项目名称">{{ detail.projectName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="审核状态"><competition-status-tag :value="detail.reviewStatus" /></el-descriptions-item>
          <el-descriptions-item label="当前状态"><competition-status-tag :value="detail.finalStatus" /></el-descriptions-item>
          <el-descriptions-item label="指导老师">{{ detail.instructorName || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="最近意见">{{ detail.latestReviewComment || '无' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ detail.remark || '无' }}</el-descriptions-item>
        </el-descriptions>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">材料列表</div>
                <div class="competition-panel__desc">{{ detail.dataQualityStatus === 'dirty' ? '先确认哪些材料只是登记文件名，不能把这类记录直接审核通过。' : '审核前先核对材料状态和意见。' }}</div>
              </div>
            </div>
          </template>
          <el-empty v-if="!(detail.materials || []).length" description="暂无材料" />
          <competition-material-table v-else :materials="detail.materials || []" :show-reviewer="true" />
        </el-card>

        <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
          <template #header>
            <div class="competition-panel__head">
              <div>
                <div class="competition-panel__title">流转日志</div>
                <div class="competition-panel__desc">审核动作和状态变化留痕</div>
              </div>
            </div>
          </template>
          <el-empty v-if="!(detail.flowLogs || []).length" description="暂无流转记录" />
          <el-timeline v-else>
            <el-timeline-item v-for="item in detail.flowLogs || []" :key="item.id" :timestamp="formatDateTime(item.operatedAt, { fallback: '未记录' })">
              <div>{{ item.actionType }}：{{ item.beforeStatus || '无' }} → {{ item.afterStatus || '无' }}</div>
              <div>{{ item.reason || '无说明' }}</div>
              <div>{{ item.operatorName || '系统' }}</div>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </div>
    </el-drawer>

    <el-dialog v-model="reviewOpen" :title="reviewTitle" width="560px" destroy-on-close>
      <el-alert
        class="competition-dialog-tip"
        :type="currentRow?.dataQualityStatus === 'dirty' && reviewForm.action === 'approve' ? 'error' : 'info'"
        :closable="false"
        show-icon
        :title="currentRow ? `${currentRow.studentName} / ${currentRow.contestName}` : '审核任务'"
        :description="currentRow?.dataQualityStatus === 'dirty' && reviewForm.action === 'approve' ? '当前记录缺少真实原件，服务端也会拦截“审核通过”。' : ''"
      />
      <el-form ref="reviewFormRef" :model="reviewForm" :rules="reviewRules" label-width="90px" style="margin-top: 16px">
        <el-form-item label="审核动作">
          <el-tag>{{ reviewTitle }}</el-tag>
        </el-form-item>
        <el-form-item label="审核意见" prop="comment">
          <el-input v-model="reviewForm.comment" type="textarea" :rows="4" placeholder="请填写审核依据、补正要求或驳回原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewOpen = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitReview">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>
