<script setup>
import { Download, View } from '@element-plus/icons-vue'
import { computed, getCurrentInstance, ref } from 'vue'

import CompetitionFilePreviewDialog from '@/components/CompetitionFilePreviewDialog.vue'
import CompetitionStatusTag from '@/components/CompetitionStatusTag.vue'
import { formatBeijingDateTime } from '@/utils/beijingTime'

const props = defineProps({
  materials: {
    type: Array,
    default: () => [],
  },
  showReviewer: {
    type: Boolean,
    default: false,
  },
})

const { proxy } = getCurrentInstance()
const previewRef = ref()

const hasReviewerColumn = computed(() => props.showReviewer || props.materials.some(item => item?.reviewerName))

function formatDateTime(value, fallback = '未记录') {
  return formatBeijingDateTime(value, { fallback, withTime: true, withSeconds: false })
}

function formatFileSize(value) {
  const size = Number(value || 0)
  if (!size) return '大小未记录'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size >= 10 * 1024 ? 0 : 1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(size >= 10 * 1024 * 1024 ? 0 : 1)} MB`
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function canPreview(material) {
  return Boolean(material?.attachmentId)
}

function handlePreview(material) {
  if (!material?.attachmentId) return
  previewRef.value?.open({
    url: `/api/v1/registrations/materials/${material.id}/preview`,
    params: {},
    fileName: material.fileName,
  })
}

function handleDownload(material) {
  if (!material?.attachmentId) return
  proxy.download(`/api/v1/registrations/materials/${material.id}/download`, {}, material.fileName)
}
</script>

<template>
  <el-table :data="materials || []" border>
    <el-table-column label="材料类型" prop="materialType" min-width="120" />
    <el-table-column label="文件信息" min-width="320">
      <template #default="scope">
        <div class="material-file">
          <div class="material-file__title">
            <span class="material-file__name">{{ scope.row.fileName || '未命名材料' }}</span>
            <el-tag v-if="scope.row.fileExt" size="small" effect="plain">{{ String(scope.row.fileExt).toUpperCase() }}</el-tag>
            <el-tag :type="scope.row.attachmentId ? 'success' : 'warning'" size="small" effect="light">
              {{ scope.row.attachmentId ? '已上传原件' : '仅登记文件名' }}
            </el-tag>
            <el-tag v-if="scope.row.dataQualityStatus === 'dirty'" type="danger" size="small" effect="light">脏数据</el-tag>
          </div>
          <div class="material-file__meta">
            <span>{{ formatFileSize(scope.row.fileSize) }}</span>
            <span>上传于 {{ formatDateTime(scope.row.uploadedAt, scope.row.attachmentId ? '未记录' : '仅登记名称') }}</span>
          </div>
          <div v-if="scope.row.dataQualityMessage" class="material-file__warning" :class="{ 'is-clean': scope.row.attachmentId }">
            {{ scope.row.dataQualityMessage }}
          </div>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="审核状态" width="120">
      <template #default="scope"><competition-status-tag :value="scope.row.reviewStatus" /></template>
    </el-table-column>
    <el-table-column label="审核意见" prop="reviewComment" min-width="180" show-overflow-tooltip />
    <el-table-column v-if="hasReviewerColumn" label="审核人" prop="reviewerName" min-width="120" />
    <el-table-column label="操作" width="170" fixed="right">
      <template #default="scope">
        <div class="material-file__actions">
          <el-button v-if="canPreview(scope.row)" link type="primary" :icon="View" @click="handlePreview(scope.row)">查看</el-button>
          <el-button v-if="scope.row.attachmentId" link type="success" :icon="Download" @click="handleDownload(scope.row)">下载</el-button>
          <span v-if="!scope.row.attachmentId" class="material-file__hint">缺少原件</span>
        </div>
      </template>
    </el-table-column>
  </el-table>
  <competition-file-preview-dialog ref="previewRef" />
</template>

<style scoped lang="scss">
.material-file {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.material-file__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.material-file__name {
  font-weight: 600;
  color: var(--el-text-color-primary);
  word-break: break-all;
}

.material-file__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.material-file__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.material-file__hint {
  font-size: 12px;
  color: var(--el-color-warning);
}

.material-file__warning {
  font-size: 12px;
  color: var(--el-color-danger);
}

.material-file__warning.is-clean {
  color: var(--el-color-success);
}
</style>
