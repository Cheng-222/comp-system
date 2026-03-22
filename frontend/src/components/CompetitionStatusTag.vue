<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: {
    type: String,
    default: ''
  }
})

const map = {
  draft: { label: '草稿', type: 'info' },
  pending_publish: { label: '待发布', type: 'warning' },
  signing_up: { label: '报名中', type: 'success' },
  submitted: { label: '已提交', type: 'primary' },
  reviewing: { label: '审核中', type: 'warning' },
  correction_required: { label: '待补正', type: 'warning' },
  approved: { label: '已通过', type: 'success' },
  rejected: { label: '已驳回', type: 'danger' },
  withdrawn: { label: '已退赛', type: 'info' },
  replaced: { label: '已替换', type: 'danger' },
  supplemented: { label: '补录中', type: 'warning' },
  pending: { label: '待处理', type: 'warning' },
  sent: { label: '已发送', type: 'success' },
  awarded: { label: '已获奖', type: 'success' },
  participated: { label: '已参赛', type: 'primary' },
  closed: { label: '已截止', type: 'info' },
  archived: { label: '已归档', type: 'info' },
  failed: { label: '发送失败', type: 'danger' },
  canceled: { label: '已取消', type: 'info' },
  enabled: { label: '启用', type: 'success' },
  disabled: { label: '停用', type: 'info' },
  processing: { label: '处理中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  partial_success: { label: '部分成功', type: 'warning' },
}

const current = computed(() => map[props.value] || { label: props.value || '未知', type: 'info' })
</script>

<template>
  <el-tag :type="current.type">{{ current.label }}</el-tag>
</template>
