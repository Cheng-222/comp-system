<script setup>
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, ref } from 'vue'

import { download, fetchBinary } from '@/utils/request'

const visible = ref(false)
const loading = ref(false)
const previewMode = ref('unsupported')
const fileName = ref('')
const contentType = ref('')
const objectUrl = ref('')
const textContent = ref('')
const htmlContent = ref('')
const sheetNames = ref([])
const activeSheet = ref('')
const sheetHtmlMap = ref({})
const unsupportedMessage = ref('当前格式暂不支持在线查看，请直接下载原件。')
const source = ref({ url: '', params: {}, fileName: '' })

const imageExts = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'])
const textExts = new Set(['txt', 'md', 'json', 'csv', 'log', 'html', 'htm', 'xml'])
const sheetExts = new Set(['xls', 'xlsx'])

let mammothModulePromise
let xlsxModulePromise

const dialogTitle = computed(() => fileName.value || '文件预览')

function inferExt(name) {
  const raw = String(name || '').trim().toLowerCase()
  if (!raw.includes('.')) return ''
  return raw.split('.').pop()
}

function revokeObjectUrl() {
  if (objectUrl.value) {
    window.URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = ''
  }
}

function resetPreviewState() {
  revokeObjectUrl()
  previewMode.value = 'unsupported'
  fileName.value = ''
  contentType.value = ''
  textContent.value = ''
  htmlContent.value = ''
  sheetNames.value = []
  activeSheet.value = ''
  sheetHtmlMap.value = {}
  unsupportedMessage.value = '当前格式暂不支持在线查看，请直接下载原件。'
  source.value = { url: '', params: {}, fileName: '' }
}

function renderTextPreview(rawText, ext) {
  if (ext === 'json') {
    try {
      return JSON.stringify(JSON.parse(rawText), null, 2)
    } catch (_error) {
      return rawText
    }
  }
  return rawText
}

async function loadPreview(options) {
  loading.value = true
  resetPreviewState()
  source.value = {
    url: options.url,
    params: options.params || {},
    fileName: options.fileName || '',
  }
  try {
    const response = await fetchBinary(options.url, options.params || {}, options.config)
    fileName.value = response.filename || options.fileName || '未命名文件'
    contentType.value = response.contentType || ''
    const ext = inferExt(fileName.value)
    if (response.contentType.includes('pdf') || ext === 'pdf') {
      objectUrl.value = window.URL.createObjectURL(response.blob)
      previewMode.value = 'pdf'
      return
    }
    if (response.contentType.startsWith('image/') || imageExts.has(ext)) {
      objectUrl.value = window.URL.createObjectURL(response.blob)
      previewMode.value = 'image'
      return
    }
    if (ext === 'docx') {
      mammothModulePromise ||= import('mammoth/mammoth.browser')
      const mammoth = (await mammothModulePromise).default
      const arrayBuffer = await response.blob.arrayBuffer()
      const result = await mammoth.convertToHtml({ arrayBuffer })
      htmlContent.value = result.value || '<p>文档内容为空</p>'
      previewMode.value = 'html'
      return
    }
    if (sheetExts.has(ext)) {
      xlsxModulePromise ||= import('xlsx')
      const XLSX = await xlsxModulePromise
      const workbook = XLSX.read(await response.blob.arrayBuffer(), { type: 'array' })
      const htmlMap = {}
      workbook.SheetNames.forEach((name) => {
        htmlMap[name] = XLSX.utils.sheet_to_html(workbook.Sheets[name], { editable: false })
      })
      sheetHtmlMap.value = htmlMap
      sheetNames.value = workbook.SheetNames
      activeSheet.value = workbook.SheetNames[0] || ''
      previewMode.value = 'sheet'
      return
    }
    if (response.contentType.startsWith('text/') || response.contentType.includes('json') || textExts.has(ext)) {
      textContent.value = renderTextPreview(await response.blob.text(), ext)
      previewMode.value = 'text'
      return
    }
    unsupportedMessage.value = ext === 'doc'
      ? '`.doc` 旧版文档当前环境不支持在线查看，请下载后打开。'
      : '当前格式暂不支持在线查看，请直接下载原件。'
    previewMode.value = 'unsupported'
  } catch (error) {
    visible.value = false
    if (error?.message !== 'binary-response-error') {
      ElMessage.error('打开文件出现错误，请稍后重试')
    }
  } finally {
    loading.value = false
  }
}

function open(options) {
  visible.value = true
  loadPreview(options)
}

function handleDownload() {
  if (!source.value.url) return
  download(source.value.url, source.value.params || {}, fileName.value || source.value.fileName || '下载文件')
}

function handleClosed() {
  resetPreviewState()
}

defineExpose({ open })

onBeforeUnmount(() => {
  revokeObjectUrl()
})
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="78%"
    top="4vh"
    destroy-on-close
    class="competition-file-preview"
    @closed="handleClosed"
  >
    <div v-loading="loading" class="competition-file-preview__body">
      <div class="competition-file-preview__meta">
        <span>{{ fileName || '未命名文件' }}</span>
        <span v-if="contentType">{{ contentType }}</span>
      </div>

      <iframe
        v-if="previewMode === 'pdf' && objectUrl"
        :src="objectUrl"
        class="competition-file-preview__frame"
        title="PDF 预览"
      />

      <div v-else-if="previewMode === 'image' && objectUrl" class="competition-file-preview__image-wrap">
        <img :src="objectUrl" :alt="fileName" class="competition-file-preview__image" />
      </div>

      <div v-else-if="previewMode === 'html'" class="competition-file-preview__html" v-html="htmlContent" />

      <div v-else-if="previewMode === 'sheet'" class="competition-file-preview__sheet">
        <el-tabs v-model="activeSheet">
          <el-tab-pane v-for="sheet in sheetNames" :key="sheet" :label="sheet" :name="sheet" />
        </el-tabs>
        <div v-if="activeSheet" class="competition-file-preview__html" v-html="sheetHtmlMap[activeSheet]" />
      </div>

      <pre v-else-if="previewMode === 'text'" class="competition-file-preview__text">{{ textContent }}</pre>

      <el-empty v-else :description="unsupportedMessage" />
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :icon="Download" @click="handleDownload">下载原件</el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="scss">
.competition-file-preview__body {
  min-height: 62vh;
}

.competition-file-preview__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.competition-file-preview__frame {
  width: 100%;
  min-height: 68vh;
  border: 1px solid var(--el-border-color);
  border-radius: 16px;
  background: #fff;
}

.competition-file-preview__image-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 64vh;
  padding: 24px;
  border: 1px solid var(--el-border-color);
  border-radius: 16px;
  background: linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%);
}

.competition-file-preview__image {
  max-width: 100%;
  max-height: 64vh;
  border-radius: 12px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.12);
}

.competition-file-preview__html,
.competition-file-preview__text {
  min-height: 64vh;
  padding: 20px;
  overflow: auto;
  border: 1px solid var(--el-border-color);
  border-radius: 16px;
  background: #fff;
}

.competition-file-preview__text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  line-height: 1.6;
}

.competition-file-preview__sheet :deep(table) {
  width: 100%;
  border-collapse: collapse;
}

.competition-file-preview__sheet :deep(td),
.competition-file-preview__sheet :deep(th) {
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-light);
}
</style>
