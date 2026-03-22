<script setup>
import { DataAnalysis, Download, Finished, Medal, Refresh, Search, Tickets } from '@element-plus/icons-vue'
import { computed, getCurrentInstance, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { listContests } from '@/api/competition/contest'
import { createStatisticsExportRecord, getAwardStatistics, listStatisticsExportRecords, retryStatisticsExportRecord } from '@/api/competition/statistics'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import useUserStore from '@/store/modules/user'
import { parseTime } from '@/utils/ruoyi'

const userStore = useUserStore()
const { proxy } = getCurrentInstance()
const loading = ref(false)
const exportLoading = ref(false)
const archiveExportLoading = ref(false)
const exportRecordsLoading = ref(false)
const downloadingExportId = ref(0)
const retryingExportId = ref(0)
const activeTab = ref('overview')
const contestOptions = ref([])
const exportRecords = ref([])
const exportRecordTotal = ref(0)
const exportRecordQuery = reactive({ pageNum: 1, pageSize: 5 })
const queryParams = reactive({ contestId: undefined })
const statistics = ref({
  summary: { participantCount: 0, resultCount: 0, awardedCount: 0, unawardedCount: 0, certificateCount: 0 },
  awardLevels: [],
  contestStats: [],
  collegeStats: [],
  unawardedList: [],
})
const exportTaskTypeMap = {
  award_statistics_export: '获奖统计报表',
  archive_export: '赛后归档资料',
}
const exportStatusMap = {
  pending: { label: '排队中', type: 'info' },
  completed: { label: '已完成', type: 'success' },
  processing: { label: '处理中', type: 'warning' },
  failed: { label: '失败', type: 'danger' },
}
const activeExportStatuses = new Set(['pending', 'processing'])
let exportPollingTimer = 0

const metricCards = computed(() => ([
  { title: '参与人数', value: statistics.value.summary.participantCount, desc: '已进入统计口径的参与人数', icon: Tickets },
  { title: '成绩记录', value: statistics.value.summary.resultCount, desc: '已归档成绩条目', icon: DataAnalysis },
  { title: '获奖人数', value: statistics.value.summary.awardedCount, desc: '已明确获奖等级的记录', icon: Medal },
  { title: '证书归档', value: statistics.value.summary.certificateCount, desc: '已归档证书数量', icon: Finished },
]))

const pageSubtitle = computed(() => {
  if (activeTab.value === 'awards') return '查看获奖等级分布和未获奖名单。'
  if (activeTab.value === 'exports') return '创建导出任务，轮询进度，并在任务完成后下载正式文件。'
  return '查看赛事维度和学院维度的统计结果。'
})
const pageScopeNote = computed(() => {
  if (activeTab.value === 'exports') return '注意：导出中心现在按任务队列执行，处理中和失败任务会保留进度、错误信息和重试入口。'
  if (activeTab.value === 'awards') return '注意：获奖分析是统计视图，不是成绩维护入口。发现异常请回到赛后管理修正。'
  return '注意：统计概览只展示汇总结果，不在这里改业务数据。'
})
const pageGuide = computed(() => {
  if (activeTab.value === 'exports') {
    return {
      eyebrow: '报表入口',
      title: '先确认统计口径，再创建导出任务',
      desc: `当前口径是“${selectedContestName.value}”。导出前最好先回看概览和获奖分析，确保数据范围没有选错；任务创建后再在导出中心盯进度和下载。`,
      steps: [
        { step: '1', title: '先确定赛事范围', desc: '按赛事筛选统计口径，避免把不同比赛批次一起导出。' },
        { step: '2', title: '再创建导出任务', desc: '确认口径无误后创建任务，系统会后台生成正式文件。' },
        { step: '3', title: '最后跟进进度并下载', desc: '处理中任务会自动刷新，失败可重试，完成后直接下载。' },
      ],
    }
  }
  if (activeTab.value === 'awards') {
    return {
      eyebrow: '分析入口',
      title: '先看获奖分布，再定位未获奖名单',
      desc: '这页更适合做赛后复盘和异常核查，不适合直接改业务结果。',
      steps: [
        { step: '1', title: '先看等级分布', desc: '先判断各奖项数量是否符合预期。' },
        { step: '2', title: '再看未获奖名单', desc: '重点核对是否存在遗漏成绩或异常状态。' },
        { step: '3', title: '发现问题回到业务页', desc: '如果数据不对，回赛后管理或报名流程修正源数据。' },
      ],
    }
  }
  return {
    eyebrow: '概览入口',
    title: '先看赛事和学院总览，再决定要不要导出报表',
    desc: `当前查看范围是“${selectedContestName.value}”。概览适合先判断数据规模和分布，再决定后续分析动作。`,
    steps: [
      { step: '1', title: '先选统计范围', desc: '用赛事筛选锁定口径，确保后续图表和表格都在同一范围内。' },
      { step: '2', title: '再看赛事和学院汇总', desc: '优先判断参与数、获奖数和证书数是否符合预期。' },
      { step: '3', title: '最后切到分析或导出', desc: '要查异常去获奖分析，要出正式材料去导出中心。' },
    ],
  }
})
const guideActions = computed(() => {
  const actions = [{ key: 'refresh', label: '重新统计', type: 'primary', plain: false }]
  if (activeTab.value === 'exports') {
    actions.push({ key: 'export', label: '统计导出', type: 'warning' })
    if (canCreateArchiveExport.value) {
      actions.push({ key: 'archive', label: '归档导出', type: 'success' })
    }
  }
  return actions
})
const canCreateArchiveExport = computed(() => Boolean(userStore.capabilities.exportArchives))

const selectedContestName = computed(() => {
  const contest = contestOptions.value.find(item => item.id === queryParams.contestId)
  return contest?.contestName || '全部赛事'
})

async function loadContests() {
  const res = await listContests({ pageSize: 200 })
  contestOptions.value = res.data.list || []
}

async function getData() {
  loading.value = true
  try {
    const res = await getAwardStatistics(queryParams)
    statistics.value = { ...statistics.value, ...(res.data || {}) }
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  queryParams.contestId = undefined
  getData()
}

function formatFileSize(value) {
  const size = Number(value || 0)
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function exportTaskLabel(row) {
  return exportTaskTypeMap[row.taskType] || row.taskType || '未知任务'
}

function exportTaskTitle(row) {
  return row.taskName || exportTaskLabel(row)
}

function exportStatusMeta(status) {
  return exportStatusMap[status] || { label: status || '未知状态', type: 'info' }
}

function exportTimeLabel(value) {
  return value ? parseTime(value) : '-'
}

async function loadExportRecords() {
  exportRecordsLoading.value = true
  try {
    const res = await listStatisticsExportRecords(exportRecordQuery)
    exportRecords.value = res.data?.list || []
    exportRecordTotal.value = res.data?.total || 0
  } finally {
    exportRecordsLoading.value = false
    syncExportPolling()
  }
}

function stopExportPolling() {
  if (exportPollingTimer) {
    window.clearTimeout(exportPollingTimer)
    exportPollingTimer = 0
  }
}

function syncExportPolling() {
  stopExportPolling()
  if (activeTab.value !== 'exports') return
  if (!exportRecords.value.some(item => activeExportStatuses.has(item.status))) return
  exportPollingTimer = window.setTimeout(() => {
    loadExportRecords()
  }, 1500)
}

async function handleExport() {
  exportLoading.value = true
  try {
    await createStatisticsExportRecord({ taskType: 'award_statistics_export', contestId: queryParams.contestId })
    proxy.$modal.msgSuccess('统计导出任务已创建')
    exportRecordQuery.pageNum = 1
    await loadExportRecords()
  } finally {
    exportLoading.value = false
  }
}

async function handleArchiveExport() {
  archiveExportLoading.value = true
  try {
    await createStatisticsExportRecord({ taskType: 'archive_export', contestId: queryParams.contestId })
    proxy.$modal.msgSuccess('归档导出任务已创建')
    exportRecordQuery.pageNum = 1
    await loadExportRecords()
  } finally {
    archiveExportLoading.value = false
  }
}

async function handleDownloadExportRecord(row) {
  downloadingExportId.value = row.id
  try {
    await proxy.download(`/api/v1/statistics/export-records/${row.id}/download`, {}, row.fileName || `${exportTaskLabel(row)}.xlsx`)
  } finally {
    downloadingExportId.value = 0
  }
}

async function handleRetryExportRecord(row) {
  retryingExportId.value = row.id
  try {
    await retryStatisticsExportRecord(row.id)
    proxy.$modal.msgSuccess('导出任务已重新提交')
    await loadExportRecords()
  } finally {
    retryingExportId.value = 0
  }
}

function handleGuideAction(action) {
  if (action.key === 'export') {
    handleExport()
    return
  }
  if (action.key === 'archive') {
    handleArchiveExport()
    return
  }
  getData()
}

const awardRows = computed(() => statistics.value.awardLevels || [])
const contestRows = computed(() => statistics.value.contestStats || [])
const collegeRows = computed(() => statistics.value.collegeStats || [])
const unawardedRows = computed(() => statistics.value.unawardedList || [])

watch(activeTab, (value) => {
  if (value === 'exports') {
    loadExportRecords()
    return
  }
  stopExportPolling()
})

onMounted(async () => {
  await loadContests()
  await getData()
  await loadExportRecords()
})

onBeforeUnmount(() => {
  stopExportPolling()
})
</script>

<template>
  <div class="competition-page" v-loading="loading">
    <el-card class="competition-control-card" shadow="never">
      <template #header>
        <div class="competition-control-head">
          <div class="competition-control-copy">
            <div class="competition-control-eyebrow">Statistics & Reports</div>
            <div class="competition-control-title">统计报表</div>
            <div class="competition-control-subtitle">{{ pageSubtitle }}</div>
          </div>
          <div class="competition-control-actions">
            <el-button type="primary" :icon="Search" @click="getData">重新统计</el-button>
            <el-button v-if="activeTab === 'exports'" plain :icon="Download" :loading="exportLoading" @click="handleExport">创建统计导出</el-button>
            <el-button v-if="activeTab === 'exports' && canCreateArchiveExport" plain :icon="Finished" :loading="archiveExportLoading" @click="handleArchiveExport">创建归档导出</el-button>
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

      <el-form :model="queryParams" :inline="true" class="competition-filter-form">
        <el-form-item label="赛事">
          <el-select v-model="queryParams.contestId" clearable style="width: 220px">
            <el-option v-for="item in contestOptions" :key="item.id" :label="item.contestName" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="getData">统计</el-button>
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
              <div class="competition-panel__title">{{ activeTab === 'overview' ? '统计概览' : activeTab === 'awards' ? '获奖分析' : '导出中心' }}</div>
              <div class="competition-panel__desc">{{ pageSubtitle }}</div>
            </div>
          </div>
          <div class="competition-toolbar__right">
            <el-button v-if="activeTab === 'exports'" type="warning" plain :icon="Refresh" :loading="exportRecordsLoading" @click="loadExportRecords">刷新记录</el-button>
            <el-button v-if="activeTab === 'exports'" type="warning" plain :icon="Download" :loading="exportLoading" @click="handleExport">创建统计导出</el-button>
            <el-button v-if="activeTab === 'exports' && canCreateArchiveExport" type="success" plain :icon="Finished" :loading="archiveExportLoading" @click="handleArchiveExport">创建归档导出</el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="统计概览" name="overview">
          <div>
            <el-card class="competition-page__panel" shadow="never">
              <template #header>
                <div class="competition-panel__head">
                  <div>
                    <div class="competition-panel__title">赛事维度统计</div>
                    <div class="competition-panel__desc">赛事成绩、获奖和证书汇总</div>
                  </div>
                </div>
              </template>
              <div class="competition-empty-fix">
                <el-empty v-if="!contestRows.length" description="暂无数据" />
                <el-table v-else :data="contestRows" border>
                  <el-table-column label="赛事" prop="contestName" min-width="180" />
                  <el-table-column label="成绩数" prop="resultCount" width="100" />
                  <el-table-column label="获奖数" prop="awardedCount" width="100" />
                  <el-table-column label="证书数" prop="certificateCount" width="100" />
                </el-table>
              </div>
            </el-card>

            <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
              <template #header>
                <div class="competition-panel__head">
                  <div>
                    <div class="competition-panel__title">学院维度统计</div>
                    <div class="competition-panel__desc">学院参与与获奖情况</div>
                  </div>
                </div>
              </template>
              <div class="competition-empty-fix">
                <el-empty v-if="!collegeRows.length" description="暂无数据" />
                <el-table v-else :data="collegeRows" border>
                  <el-table-column label="学院" prop="college" min-width="180" />
                  <el-table-column label="参与数" prop="participantCount" width="100" />
                  <el-table-column label="获奖数" prop="awardedCount" width="100" />
                </el-table>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <el-tab-pane label="获奖分析" name="awards">
          <div>
            <el-card class="competition-page__panel" shadow="never">
              <template #header>
                <div class="competition-panel__head">
                  <div>
                    <div class="competition-panel__title">获奖等级分布</div>
                    <div class="competition-panel__desc">各等级获奖数量统计</div>
                  </div>
                </div>
              </template>
              <div class="competition-empty-fix">
                <el-empty v-if="!awardRows.length" description="暂无数据" />
                <el-table v-else :data="awardRows" border>
                  <el-table-column label="获奖等级" prop="awardLevel" min-width="180" />
                  <el-table-column label="数量" prop="count" width="120" />
                </el-table>
              </div>
            </el-card>

            <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
              <template #header>
                <div class="competition-panel__head">
                  <div>
                    <div class="competition-panel__title">未获奖名单</div>
                    <div class="competition-panel__desc">用于赛后补充核验与回访</div>
                  </div>
                </div>
              </template>
              <div class="competition-empty-fix">
                <el-empty v-if="!unawardedRows.length" description="暂无数据" />
                <el-table v-else :data="unawardedRows" border>
                  <el-table-column label="赛事" prop="contestName" min-width="180" />
                  <el-table-column label="学号" prop="studentNo" min-width="120" />
                  <el-table-column label="学生" prop="studentName" min-width="100" />
                  <el-table-column label="学院" prop="college" min-width="140" />
                </el-table>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <el-tab-pane label="导出中心" name="exports">
          <el-card class="competition-page__panel" shadow="never">
            <template #header>
              <div class="competition-panel__head">
                <div>
                  <div class="competition-panel__title">报表导出</div>
                  <div class="competition-panel__desc">按当前筛选范围生成统计报表</div>
                </div>
              </div>
            </template>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="统计范围">{{ selectedContestName }}</el-descriptions-item>
              <el-descriptions-item label="参与人数">{{ statistics.summary.participantCount }}</el-descriptions-item>
              <el-descriptions-item label="获奖人数">{{ statistics.summary.awardedCount }}</el-descriptions-item>
              <el-descriptions-item label="未获奖人数">{{ statistics.summary.unawardedCount }}</el-descriptions-item>
              <el-descriptions-item label="证书归档数">{{ statistics.summary.certificateCount }}</el-descriptions-item>
              <el-descriptions-item label="导出内容">概览、获奖等级、赛事维度、学院维度、未获奖名单；如需归档资料可单独创建归档导出任务</el-descriptions-item>
            </el-descriptions>
            <div class="competition-row-actions" style="margin-top: 12px">
              <el-button type="primary" :loading="exportLoading" @click="handleExport">创建统计导出</el-button>
              <el-button v-if="canCreateArchiveExport" type="success" plain :loading="archiveExportLoading" @click="handleArchiveExport">创建归档导出</el-button>
            </div>
          </el-card>

          <el-card class="competition-page__panel" shadow="never" style="margin-top: 12px">
            <template #header>
              <div class="competition-panel__head">
                <div>
                  <div class="competition-panel__title">导出记录</div>
                  <div class="competition-panel__desc">当前账号最近生成的统计与归档文件，可直接下载复用</div>
                </div>
              </div>
            </template>
            <div class="competition-empty-fix">
              <el-empty v-if="!exportRecords.length && !exportRecordsLoading" description="当前账号暂无导出记录" />
              <el-table v-else v-loading="exportRecordsLoading" :data="exportRecords" border>
                <el-table-column label="任务名称" min-width="220">
                  <template #default="scope">
                    {{ exportTaskTitle(scope.row) }}
                  </template>
                </el-table-column>
                <el-table-column label="任务类型" min-width="140">
                  <template #default="scope">
                    {{ exportTaskLabel(scope.row) }}
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="110" align="center">
                  <template #default="scope">
                    <el-tag :type="exportStatusMeta(scope.row.status).type">
                      {{ exportStatusMeta(scope.row.status).label }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="进度" min-width="220">
                  <template #default="scope">
                    <div>
                      <el-progress :percentage="scope.row.progress || 0" :status="scope.row.status === 'failed' ? 'exception' : scope.row.status === 'completed' ? 'success' : ''" />
                      <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
                        {{ scope.row.currentStep || '等待执行' }}
                      </div>
                      <div v-if="scope.row.errorMessage" style="font-size: 12px; color: var(--el-color-danger); margin-top: 4px;">
                        {{ scope.row.errorMessage }}
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="文件名" prop="fileName" min-width="220" show-overflow-tooltip />
                <el-table-column label="文件大小" width="120">
                  <template #default="scope">
                    {{ formatFileSize(scope.row.fileSize) }}
                  </template>
                </el-table-column>
                <el-table-column label="重试" width="80" align="center">
                  <template #default="scope">
                    {{ scope.row.retryCount || 0 }}
                  </template>
                </el-table-column>
                <el-table-column label="更新时间" min-width="180">
                  <template #default="scope">
                    {{ exportTimeLabel(scope.row.finishedAt || scope.row.updatedAt || scope.row.createdAt) }}
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="180" align="center">
                  <template #default="scope">
                    <el-button
                      link
                      type="primary"
                      :loading="downloadingExportId === scope.row.id"
                      :disabled="scope.row.status !== 'completed' || !scope.row.fileName"
                      @click="handleDownloadExportRecord(scope.row)"
                    >
                      下载
                    </el-button>
                    <el-button
                      v-if="scope.row.canRetry"
                      link
                      type="warning"
                      :loading="retryingExportId === scope.row.id"
                      @click="handleRetryExportRecord(scope.row)"
                    >
                      重试
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <pagination
              v-show="exportRecordTotal > 0"
              :total="exportRecordTotal"
              v-model:page="exportRecordQuery.pageNum"
              v-model:limit="exportRecordQuery.pageSize"
              @pagination="loadExportRecords"
            />
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>
