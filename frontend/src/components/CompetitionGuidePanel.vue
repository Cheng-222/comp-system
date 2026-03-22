<script setup>
const props = defineProps({
  eyebrow: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    default: '',
  },
  note: {
    type: String,
    default: '',
  },
  noteType: {
    type: String,
    default: 'info',
  },
  steps: {
    type: Array,
    default: () => [],
  },
  actions: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['action'])

function stepIndex(step, index) {
  return step?.step || String(index + 1)
}

function stepKey(step, index) {
  return step?.key || step?.step || step?.title || index
}

function actionKey(action, index) {
  return action?.key || action?.label || index
}

function handleAction(action) {
  emit('action', action)
}
</script>

<template>
  <div class="competition-guide-panel">
    <el-alert
      v-if="props.note"
      class="competition-guide-panel__note"
      :type="props.noteType"
      :closable="false"
      show-icon
      :title="props.note"
    />

    <div class="competition-guide-panel__body">
      <div class="competition-guide-panel__intro">
        <div v-if="props.eyebrow" class="competition-guide-panel__eyebrow">{{ props.eyebrow }}</div>
        <div class="competition-guide-panel__title">{{ props.title }}</div>
        <div v-if="props.description" class="competition-guide-panel__desc">{{ props.description }}</div>
      </div>

      <div v-if="props.steps.length" class="competition-guide-panel__steps">
        <div v-for="(item, index) in props.steps" :key="stepKey(item, index)" class="competition-guide-panel__step">
          <div class="competition-guide-panel__step-index">{{ stepIndex(item, index) }}</div>
          <div class="competition-guide-panel__step-title">{{ item.title }}</div>
          <div class="competition-guide-panel__step-desc">{{ item.desc }}</div>
        </div>
      </div>

      <div v-if="props.actions.length" class="competition-guide-panel__actions">
        <el-button
          v-for="(item, index) in props.actions"
          :key="actionKey(item, index)"
          :type="item.type || 'primary'"
          :plain="item.plain !== false"
          :disabled="Boolean(item.disabled)"
          @click="handleAction(item)"
        >
          {{ item.label }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.competition-guide-panel {
  margin-top: 16px;
}

.competition-guide-panel__note {
  border-radius: 14px;
}

.competition-guide-panel__body {
  margin-top: 12px;
  padding: 18px;
  border-radius: 18px;
  border: 1px solid var(--el-border-color-lighter);
  background:
    radial-gradient(circle at top right, rgba(64, 158, 255, 0.12), transparent 36%),
    linear-gradient(135deg, #ffffff, #f7fbff);
}

.competition-guide-panel__eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--el-color-primary);
}

.competition-guide-panel__title {
  margin-top: 8px;
  font-size: 18px;
  line-height: 1.4;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.competition-guide-panel__desc {
  margin-top: 6px;
  max-width: 780px;
  font-size: 13px;
  line-height: 1.75;
  color: var(--el-text-color-regular);
}

.competition-guide-panel__steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.competition-guide-panel__step {
  min-width: 0;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid var(--el-border-color-extra-light);
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
}

.competition-guide-panel__step-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: rgba(64, 158, 255, 0.12);
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 700;
}

.competition-guide-panel__step-title {
  margin-top: 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.competition-guide-panel__step-desc {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
}

.competition-guide-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

@media (max-width: 1100px) {
  .competition-guide-panel__steps {
    grid-template-columns: 1fr;
  }
}
</style>
