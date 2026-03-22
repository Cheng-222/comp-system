<template>
   <div class="app-container">
      <el-card shadow="never">
         <template #header>
            <div class="runtime-card__header">
               <div>
                  <div class="runtime-card__title">存储与备份运行态</div>
                  <div class="runtime-card__subtitle">查看当前存储驱动、备份目录与最近备份包，并在此执行备份恢复。</div>
               </div>
               <div class="runtime-card__actions">
                  <el-button plain icon="Refresh" :loading="runtimeLoading" @click="loadRuntimeProfile">刷新运行态</el-button>
                  <el-button type="success" plain icon="FolderChecked" :loading="backupLoading" @click="handleCreateBackup(true)">创建完整备份</el-button>
                  <el-button type="warning" plain icon="Tickets" :loading="backupLoading" @click="handleCreateBackup(false)">仅备份数据</el-button>
               </div>
            </div>
         </template>

         <el-row :gutter="16">
            <el-col :xs="24" :lg="12">
               <el-descriptions :column="1" border>
                  <el-descriptions-item label="存储驱动">{{ runtimeProfile.storage?.driver || 'local' }}</el-descriptions-item>
                  <el-descriptions-item label="目录布局">{{ runtimeProfile.storage?.layout || 'flat' }}</el-descriptions-item>
                  <el-descriptions-item label="附件目录">{{ runtimeProfile.storage?.rootPath || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="备份目录">{{ runtimeProfile.backup?.rootPath || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="保留数量">{{ runtimeProfile.backup?.keepCount || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="目录可写">
                     <el-tag :type="runtimeProfile.storage?.writable ? 'success' : 'danger'">
                        {{ runtimeProfile.storage?.writable ? '是' : '否' }}
                     </el-tag>
                  </el-descriptions-item>
               </el-descriptions>
            </el-col>
            <el-col :xs="24" :lg="12">
               <el-alert
                  :title="runtimeProfile.backup?.latestFile ? `最近备份：${runtimeProfile.backup.latestFile.fileName}` : '当前还没有备份包'"
                  :type="runtimeProfile.backup?.latestFile ? 'success' : 'info'"
                  :closable="false"
                  show-icon
               />
               <el-table class="runtime-card__table" :data="runtimeProfile.backup?.files || []" size="small" max-height="320" empty-text="暂无备份包">
                  <el-table-column label="备份文件" prop="fileName" min-width="220" :show-overflow-tooltip="true" />
                  <el-table-column label="大小" min-width="100">
                     <template #default="scope">
                        {{ formatFileSize(scope.row.fileSize) }}
                     </template>
                  </el-table-column>
                  <el-table-column label="创建时间" min-width="180">
                     <template #default="scope">
                        <span>{{ parseTime(scope.row.createdAt) }}</span>
                     </template>
                  </el-table-column>
                  <el-table-column label="操作" width="180" align="center">
                     <template #default="scope">
                        <el-button link type="primary" icon="Download" @click="handleDownloadBackup(scope.row)">下载</el-button>
                        <el-button link type="warning" icon="RefreshRight" :loading="restoreTarget === scope.row.fileName && backupLoading" @click="handleRestoreBackup(scope.row)">恢复</el-button>
                     </template>
                  </el-table-column>
               </el-table>
            </el-col>
         </el-row>
      </el-card>
   </div>
</template>

<script setup name="MonitorRuntime">
import { createBackup, getRuntimeProfile, restoreBackup } from "@/api/system/config"

const { proxy } = getCurrentInstance()

const runtimeLoading = ref(false)
const backupLoading = ref(false)
const restoreTarget = ref("")
const runtimeProfile = ref({
  storage: {},
  backup: {
    files: []
  }
})

function loadRuntimeProfile() {
  runtimeLoading.value = true
  getRuntimeProfile().then(response => {
    runtimeProfile.value = response.data || { storage: {}, backup: { files: [] } }
  }).finally(() => {
    runtimeLoading.value = false
  })
}

function formatFileSize(value) {
  const size = Number(value || 0)
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function handleCreateBackup(includeUploads) {
  backupLoading.value = true
  restoreTarget.value = ""
  createBackup({ includeUploads }).then(() => {
    proxy.$modal.msgSuccess(includeUploads ? "完整备份创建成功" : "数据备份创建成功")
    loadRuntimeProfile()
  }).finally(() => {
    backupLoading.value = false
  })
}

function handleDownloadBackup(row) {
  proxy.download("system/config/backup/download", { backupFile: row.fileName }, row.fileName)
}

function handleRestoreBackup(row) {
  proxy.$modal.confirm(`是否确认恢复备份 "${row.fileName}"？当前系统数据和附件会被该备份覆盖。`).then(() => {
    backupLoading.value = true
    restoreTarget.value = row.fileName
    return restoreBackup({ backupFile: row.fileName })
  }).then(() => {
    proxy.$modal.msgSuccess("备份恢复成功")
    loadRuntimeProfile()
  }).catch(() => {}).finally(() => {
    backupLoading.value = false
    restoreTarget.value = ""
  })
}

loadRuntimeProfile()
</script>

<style scoped>
.runtime-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.runtime-card__title {
  font-size: 16px;
  font-weight: 600;
}

.runtime-card__subtitle {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.runtime-card__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.runtime-card__table {
  margin-top: 12px;
}
</style>
