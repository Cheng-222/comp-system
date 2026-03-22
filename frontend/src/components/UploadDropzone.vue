<script setup>
import { Document, UploadFilled } from '@element-plus/icons-vue'
import { getCurrentInstance, nextTick, ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  accept: {
    type: String,
    default: '',
  },
  fileTypes: {
    type: Array,
    default: () => [],
  },
  limit: {
    type: Number,
    default: 1,
  },
  multiple: {
    type: Boolean,
    default: false,
  },
  maxSize: {
    type: Number,
    default: 20,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: '将文件拖到此处，或点击上传',
  },
  description: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:modelValue'])

const { proxy } = getCurrentInstance()
const uploadRef = ref()
const internalFiles = ref([])

watch(
  () => props.modelValue,
  (value) => {
    internalFiles.value = Array.isArray(value) ? [...value] : []
  },
  { deep: true, immediate: true },
)

function normalizeExtension(fileName) {
  const segments = String(fileName || '').split('.')
  return segments.length > 1 ? segments.pop().toLowerCase() : ''
}

function validateFile(file) {
  const rawFile = file?.raw || file
  const fileName = rawFile?.name || file?.name || ''
  if (!fileName) return false

  if (props.fileTypes.length) {
    const fileExt = normalizeExtension(fileName)
    if (!props.fileTypes.includes(fileExt)) {
      proxy?.$modal?.msgError(`文件格式不正确，请上传 ${props.fileTypes.join('/')} 格式文件`)
      return false
    }
  }

  if (props.maxSize) {
    const fileSizeMb = Number(rawFile?.size || 0) / 1024 / 1024
    if (fileSizeMb > props.maxSize) {
      proxy?.$modal?.msgError(`上传文件大小不能超过 ${props.maxSize} MB`)
      return false
    }
  }
  return true
}

function syncFiles(files) {
  internalFiles.value = [...files]
  emit('update:modelValue', [...files])
}

function handleChange(file, files) {
  if (!validateFile(file)) {
    nextTick(() => uploadRef.value?.handleRemove(file))
    return
  }
  syncFiles(files)
}

function handleRemove(_file, files) {
  syncFiles(files)
}

function handleExceed(files) {
  if (props.limit === 1 && files.length) {
    uploadRef.value?.clearFiles()
    const nextFile = files[0]
    if (validateFile(nextFile)) {
      uploadRef.value?.handleStart(nextFile)
    }
    return
  }
  proxy?.$modal?.msgError(`上传文件数量不能超过 ${props.limit} 个`)
}

function removeFile(file) {
  uploadRef.value?.handleRemove(file)
}

function formatSize(size = 0) {
  if (!size) return '未记录大小'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function clearFiles() {
  uploadRef.value?.clearFiles()
  syncFiles([])
}

defineExpose({ clearFiles })
</script>

<template>
  <div class="upload-dropzone">
    <el-upload
      ref="uploadRef"
      drag
      :auto-upload="false"
      :show-file-list="false"
      :disabled="disabled"
      :accept="accept"
      :limit="limit"
      :multiple="multiple"
      :file-list="internalFiles"
      @change="handleChange"
      @remove="handleRemove"
      @exceed="handleExceed"
    >
      <el-icon class="upload-dropzone__icon"><UploadFilled /></el-icon>
      <div class="upload-dropzone__title">{{ title }}</div>
      <div v-if="description" class="upload-dropzone__desc">{{ description }}</div>
    </el-upload>

    <slot name="tip" />

    <div v-if="internalFiles.length" class="upload-dropzone__list">
      <div v-for="item in internalFiles" :key="item.uid" class="upload-dropzone__item">
        <div class="upload-dropzone__item-main">
          <el-icon class="upload-dropzone__item-icon"><Document /></el-icon>
          <div class="upload-dropzone__item-copy">
            <div class="upload-dropzone__item-name">{{ item.name }}</div>
            <div class="upload-dropzone__item-meta">{{ formatSize(item.size) }}</div>
          </div>
        </div>
        <el-button v-if="!disabled" link type="danger" @click="removeFile(item)">移除</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.upload-dropzone {
  width: 100%;
}

.upload-dropzone__icon {
  font-size: 28px;
  color: var(--el-color-primary);
}

.upload-dropzone__title {
  margin-top: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.upload-dropzone__desc {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.upload-dropzone__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.upload-dropzone__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--el-border-color-extra-light);
  background: linear-gradient(180deg, #ffffff, #f8fbff);
}

.upload-dropzone__item-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.upload-dropzone__item-icon {
  color: var(--el-color-primary);
}

.upload-dropzone__item-copy {
  min-width: 0;
}

.upload-dropzone__item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.upload-dropzone__item-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
