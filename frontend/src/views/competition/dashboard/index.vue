<script setup>
import {
  Bell,
  Document,
  Finished,
  MessageBox,
  Opportunity,
  Tickets,
  Trophy,
  User,
  WarningFilled,
} from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getCompetitionDashboard } from '@/api/competition/system'
import CompetitionGuidePanel from '@/components/CompetitionGuidePanel.vue'
import CompetitionStatusTag from '@/components/CompetitionStatusTag.vue'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const router = useRouter()
const loading = ref(false)
const stats = ref({
  currentUser: { realName: '', roleCodes: [] },
  studentCount: 0,
  contestCount: 0,
  registrationCount: 0,
  pendingReviewCount: 0,
  sentMessageCount: 0,
  resultCount: 0,
  awardedCount: 0,
  recentRegistrations: [],
  todoRegistrations: [],
  recentMessages: [],
})

const roleLabelMap = {
  admin: '系统管理员',
  teacher: '竞赛管理员',
  reviewer: '审核人员',
  student: '学生用户'
}

const actionItems = [
  {
    key: 'students',
    label: '学生管理',
    path: '/competition/students',
    desc: '维护学生基础档案',
    icon: User,
    roles: ['admin'],
  },
  {
    key: 'contests',
    label: '赛事管理',
    path: '/competition/contests',
    desc: '维护赛事配置与状态',
    icon: Trophy,
    roles: ['admin', 'teacher'],
  },
  {
    key: 'registrations',
    label: '报名管理',
    path: '/competition/registrations',
    desc: '维护报名与材料提交',
    icon: Tickets,
    roles: ['admin', 'teacher', 'student'],
  },
  {
    key: 'qualifications',
    label: '资格管理',
    path: '/competition/qualifications',
    desc: '处理退赛、换人、补录',
    icon: Opportunity,
    roles: ['admin', 'teacher'],
  },
  {
    key: 'reviews',
    label: '材料审核',
    path: '/competition/reviews',
    desc: '处理审核与补正意见',
    icon: Document,
    roles: ['admin', 'reviewer'],
  },
  {
    key: 'messages',
    label: '通知中心',
    path: '/competition/messages',
    desc: '区分通知发布与我的消息',
    icon: MessageBox,
    roles: ['admin', 'teacher', 'reviewer', 'student'],
  },
  {
    key: 'results',
    label: '赛后管理',
    path: '/competition/results',
    desc: '维护成绩、证书与归档',
    icon: Finished,
    roles: ['admin', 'teacher', 'student'],
  },
  {
    key: 'statistics',
    label: '统计报表',
    path: '/competition/statistics',
    desc: '输出分析与报表',
    icon: Bell,
    roles: ['admin', 'teacher'],
  },
]

function formatDateTime(value, options = {}) {
  return formatBeijingDateTime(value, { fallback: '待补充', withTime: options.withTime !== false, withSeconds: false })
}

const roleCodes = computed(() => stats.value.currentUser?.roleCodes || [])
const isAdmin = computed(() => roleCodes.value.includes('admin'))
const canManageRegistrations = computed(() => roleCodes.value.some(role => ['admin', 'teacher'].includes(role)))
const canReview = computed(() => roleCodes.value.some(role => ['admin', 'reviewer'].includes(role)))
const canReadMessages = computed(() => roleCodes.value.some(role => ['admin', 'teacher', 'reviewer', 'student'].includes(role)))

const roleTags = computed(() => roleCodes.value.map(item => ({ code: item, label: roleLabelMap[item] || item })))

const visibleActions = computed(() => actionItems.filter(item => item.roles.some(role => roleCodes.value.includes(role))))
const visibleActionPaths = computed(() => new Set(visibleActions.value.map(item => item.path)))

const summaryCards = computed(() => {
  const cards = []
  if (visibleActionPaths.value.has('/competition/students')) {
    cards.push({ label: '学生档案', value: stats.value.studentCount })
  }
  if (visibleActionPaths.value.has('/competition/contests')) {
    cards.push({ label: '赛事数量', value: stats.value.contestCount })
  }
  cards.push({
    label: roleCodes.value.includes('student') && !canReview.value ? '我的报名' : '报名记录',
    value: stats.value.registrationCount,
  })
  if (canReview.value) {
    cards.push({ label: '待审核材料', value: stats.value.pendingReviewCount, tone: 'warning' })
  } else {
    cards.push({ label: '成绩记录', value: stats.value.resultCount })
  }
  if (cards.length < 4 && visibleActionPaths.value.has('/competition/results')) {
    cards.push({ label: '赛后记录', value: stats.value.resultCount })
  }
  if (cards.length < 4 && canReadMessages.value) {
    cards.push({
      label: isAdmin.value ? '已发通知' : '我的消息',
      value: isAdmin.value ? stats.value.sentMessageCount : stats.value.recentMessages.length,
    })
  }
  return cards.slice(0, 4)
})

const dashboardNote = computed(() => {
  if (canReview.value) return '注意：工作台只负责总览和分发，真正的审核结论请进“材料审核”页面处理。'
  if (canManageRegistrations.value) return '注意：工作台只负责看全局和快速跳转，建报名、补材料、退赛换人都在各自业务页完成。'
  return '注意：这里是你的竞赛概览页。报名、补正和退赛都在“我的报名”里处理，不需要单独找资格管理。'
})
const dashboardGuide = computed(() => {
  if (canReview.value) {
    return {
      eyebrow: '审核总览',
      title: '先处理待审核材料，再回头看通知和历史记录',
      desc: '审核角色最重要的是先清队列，再去查看通知或补充上下文，避免把精力花在不需要马上处理的页面上。',
      steps: [
        { step: '1', title: '先看待审核材料', desc: '优先进入材料审核，处理待通过、待补正和待驳回的记录。' },
        { step: '2', title: '再回看通知中心', desc: '确认是否有新的审核提醒、规则调整或补充说明。' },
        { step: '3', title: '需要上下文再查报名', desc: '对单条记录有疑问时，再去报名管理补充查看历史信息。' },
      ],
    }
  }
  if (canManageRegistrations.value) {
    return {
      eyebrow: '管理总览',
      title: '先看最近报名，再决定去审核、资格还是通知',
      desc: '管理角色最容易被跨页面流程打散，所以工作台先告诉你现在最值得进入哪个模块。',
      steps: [
        { step: '1', title: '先看最近报名', desc: '确认当前新增记录、待补材料和最新流转情况。' },
        { step: '2', title: '再去对应业务页', desc: '审核问题去材料审核，资格变更去资格管理，通知触达去通知中心。' },
        { step: '3', title: '最后回到赛后和统计', desc: '主流程稳定后，再继续维护成绩、证书和统计报表。' },
      ],
    }
  }
  return {
    eyebrow: '个人总览',
    title: '先看我的报名进度，再查消息和赛后结果',
    desc: '学生视角最重要的是知道报名走到哪一步，以及有没有新的补正要求、退赛变更或赛后结果。',
    steps: [
      { step: '1', title: '先看我的报名', desc: '确认当前报名有没有提交材料、是否被退回补正；如需退出，也直接在这里处理。' },
      { step: '2', title: '再看最近通知', desc: '通知中心会告诉你是否有新提醒、审核结果或材料要求。' },
      { step: '3', title: '赛后再看结果', desc: '比赛结束后，再去赛后管理查看成绩、证书和归档情况。' },
    ],
  }
})
const dashboardGuideActions = computed(() => {
  const actions = []
  if (visibleActionPaths.value.has(todoActionPath.value)) {
    actions.push({ key: todoActionPath.value, label: todoActionLabel.value, type: 'primary', plain: false, path: todoActionPath.value })
  }
  if (visibleActionPaths.value.has('/competition/messages')) {
    actions.push({ key: 'messages', label: '通知中心', type: 'info', path: '/competition/messages' })
  }
  return actions
})

const todoTitle = computed(() => {
  if (canReview.value) return '待审核材料'
  if (canManageRegistrations.value) return '最近报名'
  return '我的报名进度'
})
const todoSubtitle = computed(() => {
  if (canReview.value) return '集中处理待审核和待补正的报名记录。'
  if (canManageRegistrations.value) return '查看最新报名记录和当前业务状态。'
  return '查看当前账号相关的报名记录和状态。'
})
const todoActionPath = computed(() => (canReview.value ? '/competition/reviews' : '/competition/registrations'))
const todoActionLabel = computed(() => {
  if (canReview.value) return '进入材料审核'
  return canManageRegistrations.value ? '进入报名管理' : '进入我的报名'
})
const todoItems = computed(() => (canReview.value ? stats.value.todoRegistrations || [] : stats.value.recentRegistrations || []))

const actionTiles = computed(() => visibleActions.value.map(item => ({
  ...item,
  count: resolveActionCount(item.key),
})))

function resolveActionCount(key) {
  const countMap = {
    students: stats.value.studentCount,
    contests: stats.value.contestCount,
    registrations: stats.value.registrationCount,
    qualifications: stats.value.pendingReviewCount,
    reviews: stats.value.pendingReviewCount,
    messages: isAdmin.value ? stats.value.sentMessageCount : stats.value.recentMessages.length,
    results: stats.value.resultCount,
    statistics: stats.value.awardedCount,
  }
  return countMap[key] ?? 0
}

function todoStatusValue(item) {
  return canReview.value ? item.reviewStatus : item.finalStatus
}

function go(path) {
  if (!path || (path.startsWith('/competition') && !visibleActionPaths.value.has(path))) return
  router.push(path)
}

function handleGuideAction(action) {
  go(action.path)
}

async function loadData() {
  loading.value = true
  try {
    const res = await getCompetitionDashboard()
    stats.value = res.data || stats.value
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="competition-dashboard" v-loading="loading">
    <section class="dashboard-head">
      <div class="dashboard-head__copy">
        <div class="dashboard-head__title">竞赛管理概览</div>
        <div class="dashboard-head__subtitle">
          查看当前账号相关的待处理事项、消息和业务入口。当前账号：{{ stats.currentUser.realName || '未登录' }}。
        </div>
        <div class="dashboard-head__tags">
          <el-tag v-for="item in roleTags" :key="item.code" round>{{ item.label }}</el-tag>
        </div>
      </div>
      <div class="dashboard-head__metrics">
        <article v-for="item in summaryCards" :key="item.label" class="head-metric" :class="{ 'head-metric--warning': item.tone === 'warning' }">
          <div class="head-metric__label">{{ item.label }}</div>
          <div class="head-metric__value">{{ item.value }}</div>
        </article>
      </div>
    </section>

    <competition-guide-panel
      :note="dashboardNote"
      :eyebrow="dashboardGuide.eyebrow"
      :title="dashboardGuide.title"
      :description="dashboardGuide.desc"
      :steps="dashboardGuide.steps"
      :actions="dashboardGuideActions"
      @action="handleGuideAction"
    />

    <section class="dashboard-grid">
      <el-card class="shell-card dashboard-panel" shadow="never">
        <template #header>
          <div class="panel-head">
            <div>
              <div class="panel-head__title">{{ todoTitle }}</div>
              <div class="panel-head__desc">{{ todoSubtitle }}</div>
            </div>
            <el-button v-if="visibleActionPaths.has(todoActionPath)" link type="primary" @click="go(todoActionPath)">
              {{ todoActionLabel }}
            </el-button>
          </div>
        </template>
        <el-empty v-if="!todoItems.length" description="暂无待处理记录" />
        <div v-else class="todo-list">
          <div v-for="item in todoItems.slice(0, 6)" :key="item.id" class="todo-item">
            <div class="todo-item__main">
              <div class="todo-item__title">{{ item.studentName }} · {{ item.contestName }}</div>
              <div class="todo-item__meta">
                {{ item.studentNo || '学号待补充' }}
                <span>提交于 {{ formatDateTime(item.submitTime) }}</span>
              </div>
            </div>
            <div class="todo-item__side">
              <competition-status-tag :value="todoStatusValue(item)" />
            </div>
          </div>
        </div>
      </el-card>

      <el-card class="shell-card dashboard-panel" shadow="never">
        <template #header>
          <div class="panel-head">
            <div>
              <div class="panel-head__title">最近通知</div>
              <div class="panel-head__desc">按当前账号可见范围展示。</div>
            </div>
            <el-button v-if="visibleActionPaths.has('/competition/messages')" link type="primary" @click="go('/competition/messages')">
              通知中心
            </el-button>
          </div>
        </template>
        <el-empty v-if="!stats.recentMessages.length" description="暂无通知数据" />
        <div v-else class="message-list">
          <div v-for="item in stats.recentMessages" :key="item.id" class="message-item">
            <div class="message-item__icon">
              <el-icon><component :is="item.messageType === 'todo' ? WarningFilled : Bell" /></el-icon>
            </div>
            <div class="message-item__body">
              <div class="message-item__title">{{ item.title }}</div>
              <div class="message-item__meta">
                {{ item.messageTypeLabel }} · {{ item.createdByName || '系统' }} · {{ formatDateTime(item.createdAt) }}
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </section>

    <el-card class="shell-card dashboard-panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <div class="panel-head__title">业务入口</div>
            <div class="panel-head__desc">按职责划分进入各功能模块。</div>
          </div>
        </div>
      </template>
      <div class="action-grid">
        <button
          v-for="item in actionTiles"
          :key="item.path"
          type="button"
          class="action-tile"
          @click="go(item.path)"
        >
          <div class="action-tile__top">
            <div class="action-tile__icon">
              <el-icon><component :is="item.icon" /></el-icon>
            </div>
            <div class="action-tile__badge">{{ item.count }}</div>
          </div>
          <div class="action-tile__title">{{ item.label }}</div>
          <div class="action-tile__desc">{{ item.desc }}</div>
        </button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.competition-dashboard {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dashboard-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.08), rgba(103, 194, 58, 0.03));
}

.dashboard-head__copy {
  min-width: 0;
}

.dashboard-head__title {
  font-size: 22px;
  line-height: 1.2;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.dashboard-head__subtitle {
  margin-top: 8px;
  max-width: 760px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.dashboard-head__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.dashboard-head__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(140px, 1fr));
  gap: 10px;
  min-width: 320px;
}

.head-metric {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(64, 158, 255, 0.12);
  background: rgba(255, 255, 255, 0.76);
}

.head-metric--warning {
  border-color: rgba(230, 162, 60, 0.2);
}

.head-metric__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.head-metric__value {
  margin-top: 8px;
  font-size: 24px;
  line-height: 1;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.9fr);
  gap: 12px;
  align-items: start;
}

.shell-card {
  border-radius: 14px;
  border: 1px solid var(--el-border-color-light);
}

.shell-card :deep(.el-card__header) {
  padding: 16px 18px 0;
  border-bottom: none;
}

.shell-card :deep(.el-card__body) {
  padding: 16px 18px 18px;
}

.dashboard-panel {
  min-height: 100%;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-head__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.panel-head__desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.todo-list,
.message-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.todo-item,
.message-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
}

.todo-item__main,
.message-item__body {
  min-width: 0;
}

.todo-item__title,
.message-item__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.todo-item__meta,
.message-item__meta {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.message-item__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 10px;
  color: var(--el-color-primary);
  background: rgba(64, 158, 255, 0.1);
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.action-tile {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px;
  background: linear-gradient(180deg, var(--el-fill-color-blank), var(--el-fill-color-light));
  text-align: left;
  cursor: pointer;
  transition: border-color .2s ease, transform .2s ease;
}

.action-tile:hover {
  border-color: rgba(64, 158, 255, 0.3);
  transform: translateY(-1px);
}

.action-tile__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.action-tile__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  font-size: 18px;
  color: var(--el-color-primary);
  background: rgba(64, 158, 255, 0.1);
}

.action-tile__badge {
  min-width: 34px;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1;
  text-align: center;
  color: var(--el-color-primary);
  background: rgba(64, 158, 255, 0.1);
}

.action-tile__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.action-tile__desc {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

@media (max-width: 1320px) {
  .dashboard-head {
    flex-direction: column;
  }

  .dashboard-head__metrics {
    width: 100%;
    min-width: 0;
  }

  .dashboard-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 768px) {
  .dashboard-head__metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .action-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
