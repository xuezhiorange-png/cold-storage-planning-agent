<script setup lang="ts">
import { onMounted, ref } from 'vue'

import type { ArtifactListItemContract } from '../../../api/contracts/reports'

import {
  createDefaultExportForm,
  useReportExport
} from '../composables/useReportExport'
import type { ExportForm } from '../composables/useReportExport'

const props = withDefaults(
  defineProps<{
    projectId?: string
  }>(),
  {
    projectId: undefined
  }
)

const emit = defineEmits<{
  reportSelected: [reportId: string]
  renderStarted: [reportId: string, revisionNumber: number]
  downloadStarted: [artifactId: string]
  error: [message: string]
}>()

const {
  reports,
  reportsLoading,
  reportsError,

  selectedReportId,
  selectedRevisionNumber,

  revisions,
  revisionsLoading,
  revisionsError,

  exports,
  exportsLoading,
  exportsError,

  renderLoading,
  renderError,
  renderResult,

  downloadLoading,
  downloadError,

  loadReports,
  selectReport,
  renderReport,
  downloadArtifact,
  reset
} = useReportExport()

/* ── Local UI state ────────────────────────────────── */

const activeExportForm = ref<ExportForm>(createDefaultExportForm())
const expandedReportId = ref<string | null>(null)

/* ── Lifecycle ─────────────────────────────────────── */

onMounted(() => {
  loadReports(props.projectId)
})

/* ── Actions ───────────────────────────────────────── */

function toggleReport(reportId: string): void {
  if (expandedReportId.value === reportId) {
    expandedReportId.value = null
    return
  }
  expandedReportId.value = reportId
  emit('reportSelected', reportId)
  selectReport(reportId)
}

async function handleRender(reportId: string, revisionNumber: number): Promise<void> {
  emit('renderStarted', reportId, revisionNumber)
  await renderReport(reportId, revisionNumber, activeExportForm.value)
  if (renderError.value) {
    emit('error', renderError.value)
  }
}

async function handleDownload(reportId: string, artifact: ArtifactListItemContract): Promise<void> {
  emit('downloadStarted', artifact.artifact_id)
  await downloadArtifact(reportId, artifact.artifact_id)
  if (downloadError.value) {
    emit('error', downloadError.value)
  }
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '待渲染',
    rendering: '渲染中',
    completed: '已完成',
    failed: '失败'
  }
  return labels[status] ?? status
}

function reportStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: '草稿',
    generated: '已生成',
    under_review: '审核中',
    reviewed: '已审核',
    approved: '已批准',
    archived: '已归档'
  }
  return labels[status] ?? status
}
</script>

<template>
  <section class="report-export-panel" aria-label="报告导出面板">
    <header class="report-export-panel__header">
      <strong>报告导出</strong>
      <span v-if="reports.length">共 {{ reports.length }} 个报告</span>
      <button
        type="button"
        class="report-export-panel__refresh"
        :disabled="reportsLoading"
        @click="loadReports(projectId)"
      >
        {{ reportsLoading ? '加载中...' : '刷新' }}
      </button>
    </header>

    <!-- Error banner -->
    <div
      v-if="reportsError"
      class="report-export-panel__error"
      role="alert"
    >
      {{ reportsError }}
    </div>

    <!-- Loading indicator -->
    <div
      v-if="reportsLoading && reports.length === 0"
      class="report-export-panel__loading"
    >
      加载报告列表...
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!reportsLoading && reports.length === 0 && !reportsError"
      class="report-export-panel__empty"
    >
      暂无可用报告
    </div>

    <!-- Report list -->
    <ul
      v-else
      class="report-export-panel__list"
      role="list"
      aria-label="报告列表"
    >
      <li
        v-for="report in reports"
        :key="report.id"
        class="report-export-panel__item"
      >
        <button
          type="button"
          :class="[
            'report-export-panel__toggle',
            { 'report-export-panel__toggle--active': expandedReportId === report.id }
          ]"
          :aria-expanded="expandedReportId === report.id"
          :aria-controls="`report-detail-${report.id}`"
          @click="toggleReport(report.id)"
        >
          <span class="report-export-panel__item-name">{{ report.id }}</span>
          <span class="report-export-panel__item-status">{{ reportStatusLabel(report.status) }}</span>
          <span class="report-export-panel__item-chevron">{{ expandedReportId === report.id ? '▼' : '▶' }}</span>
        </button>

        <!-- Expanded detail -->
        <div
          v-if="expandedReportId === report.id"
          :id="`report-detail-${report.id}`"
          class="report-export-panel__detail"
          role="region"
        >
          <!-- Revisions section -->
          <div class="report-export-panel__section">
            <strong class="report-export-panel__section-title">版本</strong>

            <div
              v-if="revisionsLoading"
              class="report-export-panel__loading"
            >
              加载版本列表...
            </div>
            <div
              v-else-if="revisionsError"
              class="report-export-panel__error report-export-panel__error--inline"
            >
              {{ revisionsError }}
            </div>
            <div
              v-else-if="revisions.length === 0"
              class="report-export-panel__empty report-export-panel__empty--inline"
            >
              暂无版本
            </div>

            <ul
              v-else
              class="report-export-panel__revisions"
              role="list"
              aria-label="版本列表"
            >
              <li
                v-for="rev in revisions"
                :key="rev.revision_number"
                class="report-export-panel__revision"
              >
                <span class="report-export-panel__revision-num">
                  v{{ rev.revision_number }}
                </span>

                <!-- Export form (shown only when this revision is selected) -->
                <div
                  class="report-export-panel__export-form"
                >
                  <label class="report-export-panel__field">
                    <span>格式</span>
                    <select v-model="activeExportForm.format">
                      <option value="pdf">PDF</option>
                      <option value="docx">Word</option>
                    </select>
                  </label>

                  <label class="report-export-panel__field">
                    <span>模式</span>
                    <select v-model="activeExportForm.mode">
                      <option value="draft">草稿</option>
                      <option value="formal">正式</option>
                    </select>
                  </label>

                  <label class="report-export-panel__field">
                    <span>语言</span>
                    <select v-model="activeExportForm.locale">
                      <option value="zh-CN">中文</option>
                      <option value="en-US">English</option>
                    </select>
                  </label>

                  <button
                    type="button"
                    class="report-export-panel__render-btn"
                    :disabled="renderLoading"
                    @click="handleRender(report.id, rev.revision_number)"
                  >
                    {{ renderLoading && selectedRevisionNumber === rev.revision_number ? '渲染中...' : '导出' }}
                  </button>
                </div>
              </li>
            </ul>
          </div>

          <!-- Render result banner -->
          <div
            v-if="renderResult && selectedReportId === report.id"
            class="report-export-panel__render-success"
          >
            <span>✅ 导出已提交 ({{ renderResult.artifact_id }})</span>
          </div>
          <div
            v-if="renderError && selectedReportId === report.id"
            class="report-export-panel__error report-export-panel__error--inline"
          >
            {{ renderError }}
          </div>

          <!-- Exports (artifacts) section -->
          <div class="report-export-panel__section">
            <strong class="report-export-panel__section-title">已导出文件</strong>

            <div
              v-if="exportsLoading"
              class="report-export-panel__loading"
            >
              加载导出列表...
            </div>
            <div
              v-else-if="exportsError"
              class="report-export-panel__error report-export-panel__error--inline"
            >
              {{ exportsError }}
            </div>
            <div
              v-else-if="exports.length === 0"
              class="report-export-panel__empty report-export-panel__empty--inline"
            >
              暂无导出文件
            </div>

            <div v-else class="table-scroll">
              <table
                class="report-export-panel__exports-table"
                aria-label="已导出文件列表"
              >
                <thead>
                  <tr>
                    <th>文件名</th>
                    <th>格式</th>
                    <th>版本</th>
                    <th>大小</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="artifact in exports"
                    :key="artifact.artifact_id"
                  >
                    <td>{{ artifact.file_name }}</td>
                    <td>{{ artifact.format.toUpperCase() }}</td>
                    <td>v{{ artifact.revision_number }}</td>
                    <td>{{ formatFileSize(artifact.file_size_bytes) }}</td>
                    <td>{{ statusLabel(artifact.status) }}</td>
                    <td>
                      <button
                        type="button"
                        class="report-export-panel__download-btn"
                        :disabled="downloadLoading || artifact.status !== 'completed'"
                        @click="handleDownload(report.id, artifact)"
                      >
                        {{ downloadLoading ? '下载中...' : '下载' }}
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Download error banner -->
          <div
            v-if="downloadError"
            class="report-export-panel__error report-export-panel__error--inline"
          >
            {{ downloadError }}
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
/* ── Container ────────────────────────────────────── */

.report-export-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── Header ───────────────────────────────────────── */

.report-export-panel__header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.report-export-panel__refresh {
  margin-left: auto;
  border: 1px solid #b8cae0;
  border-radius: 4px;
  padding: 4px 10px;
  background: #123a63;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
}

.report-export-panel__refresh:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ── List ─────────────────────────────────────────── */

.report-export-panel__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.report-export-panel__item {
  display: flex;
  flex-direction: column;
  border: 1px solid #dbe8f6;
  border-radius: 6px;
  background: #fff;
}

/* ── Toggle / item header ─────────────────────────── */

.report-export-panel__toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  border: none;
  border-radius: 6px;
  padding: 10px 12px;
  width: 100%;
  background: none;
  cursor: pointer;
  font-size: 14px;
  text-align: left;
}

.report-export-panel__toggle:hover {
  background: #f0f4f9;
}

.report-export-panel__toggle--active {
  border-bottom: 1px solid #dbe8f6;
  border-radius: 6px 6px 0 0;
  background: #eef3f9;
}

.report-export-panel__item-name {
  font-weight: 600;
}

.report-export-panel__item-status {
  font-size: 12px;
  color: #5f7a99;
}

.report-export-panel__item-chevron {
  margin-left: auto;
  font-size: 11px;
  color: #8aa3c2;
}

/* ── Expanded detail ──────────────────────────────── */

.report-export-panel__detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px 12px 16px;
}

.report-export-panel__section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.report-export-panel__section-title {
  font-size: 13px;
  color: #2d4a6f;
}

/* ── Revisions ────────────────────────────────────── */

.report-export-panel__revisions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.report-export-panel__revision {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid #e8edf4;
  border-radius: 4px;
  background: #fafcfe;
}

.report-export-panel__revision-num {
  font-weight: 600;
  font-size: 13px;
  min-width: 40px;
}

/* ── Export form (inline) ─────────────────────────── */

.report-export-panel__export-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.report-export-panel__field {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.report-export-panel__field select {
  border: 1px solid #b8cae0;
  border-radius: 4px;
  padding: 3px 6px;
  font-size: 12px;
  background: #fff;
}

.report-export-panel__render-btn {
  border: 1px solid #123a63;
  border-radius: 4px;
  padding: 4px 12px;
  background: #123a63;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
}

.report-export-panel__render-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ── Exports table ────────────────────────────────── */

.report-export-panel__exports-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.report-export-panel__exports-table th {
  padding: 6px 8px;
  border-bottom: 2px solid #dbe8f6;
  text-align: left;
  font-weight: 600;
  font-size: 12px;
  color: #2d4a6f;
}

.report-export-panel__exports-table td {
  padding: 6px 8px;
  border-bottom: 1px solid #e8edf4;
}

.report-export-panel__download-btn {
  border: 1px solid #5f7a99;
  border-radius: 4px;
  padding: 3px 10px;
  background: #fff;
  color: #123a63;
  cursor: pointer;
  font-size: 12px;
}

.report-export-panel__download-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ── Status banners ───────────────────────────────── */

.report-export-panel__loading {
  padding: 8px 12px;
  font-size: 13px;
  color: #5f7a99;
}

.report-export-panel__empty {
  padding: 8px 12px;
  font-size: 13px;
  color: #8aa3c2;
}

.report-export-panel__empty--inline {
  padding: 4px 0;
}

.report-export-panel__error {
  padding: 8px 12px;
  border-radius: 4px;
  background: #fdf0ef;
  color: #c0392b;
  font-size: 13px;
}

.report-export-panel__error--inline {
  padding: 4px 8px;
}

.report-export-panel__render-success {
  padding: 8px 12px;
  border-radius: 4px;
  background: #eaf7ea;
  color: #27ae60;
  font-size: 13px;
}
</style>
