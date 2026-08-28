<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import type { ArtifactListItemContract } from '../../../api/contracts/reports'
import type { WorkflowBlocker } from '../../../api/contracts/workflow'

import {
  createDefaultExportForm,
  DRAFT_EXPORT_POLICY_COPY,
  FORMAL_EXPORT_POLICY_COPY,
  selectDisplayedExportBlockers,
  useReportExport
} from '../composables/useReportExport'
import type { ExportForm } from '../composables/useReportExport'

const props = withDefaults(
  defineProps<{
    projectId?: string
    projectVersionId?: string
    formalExportEligible?: boolean
    formalExportBlockers?: WorkflowBlocker[]
  }>(),
  {
    projectId: undefined,
    projectVersionId: undefined,
    formalExportEligible: false,
    formalExportBlockers: () => []
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

  reportDetail,
  reportDetailLoading,
  reportDetailError,

  createLoading,
  createError,
  generateLoading,
  generateError,
  actionBlockers,

  reviewLoading,
  reviewError,

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
  createAndGenerateReport,
  generateRevision,
  submitReview,
  markReviewed,
  approveReport,
  selectReport,
  renderReport,
  downloadArtifact,
  reset,
  revisionContent,
  revisionContentLoading,
  revisionContentError
} = useReportExport()

/* ── Local UI state ────────────────────────────────── */

const activeExportForm = ref<ExportForm>(createDefaultExportForm())
const expandedReportId = ref<string | null>(null)

const canCreateReport = computed(
  () => Boolean(props.projectId && props.projectVersionId)
)
const workflowBusy = computed(
  () => createLoading.value || generateLoading.value || reviewLoading.value
)
const displayedBlockers = computed(() =>
  selectDisplayedExportBlockers({
    mode: activeExportForm.value.mode,
    actionBlockers: [...actionBlockers.value],
    formalExportEligible: props.formalExportEligible,
    formalExportBlockers: props.formalExportBlockers
  })
)
const draftRenderDisabled = computed(() => renderLoading.value)
const formalRenderDisabled = computed(
  () => renderLoading.value || !props.formalExportEligible
)
const exportPolicyCopy = `${FORMAL_EXPORT_POLICY_COPY}，${DRAFT_EXPORT_POLICY_COPY}`
const operatorKeyFields = [
  'daily_inbound_mass_kg',
  'finished_storage_days',
  'frozen_storage_days',
  'main_packaging_storage_days',
  'auxiliary_packaging_storage_days'
] as const

/* ── Lifecycle ─────────────────────────────────────── */

onMounted(() => {
  loadReports(props.projectId)
})

watch(
  () => props.projectId,
  (projectId) => {
    reset()
    loadReports(projectId)
  }
)

watch(
  () => props.formalExportEligible,
  (eligible) => {
    if (!eligible && activeExportForm.value.mode === 'formal') {
      activeExportForm.value.mode = 'draft'
    }
  }
)

async function handleCreateAndGenerate(): Promise<void> {
  if (!props.projectId || !props.projectVersionId) return
  const reportId = await createAndGenerateReport({
    projectId: props.projectId,
    projectVersionId: props.projectVersionId
  })
  if (reportId) {
    expandedReportId.value = reportId
    emit('reportSelected', reportId)
  }
  if (createError.value || generateError.value) {
    emit('error', createError.value || generateError.value)
  }
}

async function handleGenerateRevision(reportId: string): Promise<void> {
  const ok = await generateRevision(reportId)
  if (!ok && generateError.value) {
    emit('error', generateError.value)
  }
}

async function handleReviewAction(
  action: 'submit' | 'mark-reviewed' | 'approve',
  reportId: string
): Promise<void> {
  let ok = false
  if (action === 'submit') ok = await submitReview(reportId)
  if (action === 'mark-reviewed') ok = await markReviewed(reportId)
  if (action === 'approve') ok = await approveReport(reportId)
  if (!ok && reviewError.value) {
    emit('error', reviewError.value)
  }
}

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

async function handleDraftRender(reportId: string, revisionNumber: number): Promise<void> {
  activeExportForm.value.mode = 'draft'
  await handleRender(reportId, revisionNumber)
}

async function handleFormalRender(reportId: string, revisionNumber: number): Promise<void> {
  if (!props.formalExportEligible) return
  activeExportForm.value.mode = 'formal'
  await handleRender(reportId, revisionNumber)
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
      <span class="report-export-panel__policy">{{ exportPolicyCopy }}。</span>
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

    <div
      v-if="!formalExportEligible"
      class="report-export-panel__formal-note"
      role="status"
      data-export-scope="formal"
    >
      正式导出当前不可用，不影响草稿导出。{{ exportPolicyCopy }}。
      后端将在正式渲染/下载时再次校验。浏览器内标记已审核不是生产 RBAC。
      <ul v-if="formalExportBlockers.length">
        <li v-for="(blocker, index) in formalExportBlockers" :key="`formal-${blocker.code}-${index}`">
          {{ blocker.message }}
        </li>
      </ul>
    </div>

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

    <!-- Empty state with guided create -->
    <div
      v-else-if="!reportsLoading && reports.length === 0 && !reportsError"
      class="report-export-panel__empty"
    >
      <p>暂无可用报告。从已完成的五阶段结果创建报告并生成首版 JSON。</p>
      <p v-if="!canCreateReport" class="report-export-panel__hint">
        缺少项目版本标识，无法创建报告。请先在工作台完成项目初始化。
      </p>
      <button
        type="button"
        class="report-export-panel__create-btn"
        :disabled="!canCreateReport || workflowBusy"
        @click="handleCreateAndGenerate"
      >
        {{ createLoading || generateLoading ? '创建中...' : '创建并生成报告' }}
      </button>
      <div
        v-if="createError"
        class="report-export-panel__error report-export-panel__error--inline"
        role="alert"
      >
        {{ createError }}
      </div>
      <div
        v-if="generateError"
        class="report-export-panel__error report-export-panel__error--inline"
        role="alert"
      >
        {{ generateError }}
      </div>
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
          <!-- Persisted report sections (read-only JSON projection) -->
          <div class="report-export-panel__section">
            <strong class="report-export-panel__section-title">已持久化报告摘要</strong>
            <div
              v-if="revisionContentLoading"
              class="report-export-panel__loading"
            >
              加载报告 JSON...
            </div>
            <div
              v-else-if="revisionContentError"
              class="report-export-panel__error report-export-panel__error--inline"
            >
              {{ revisionContentError }}
            </div>
            <div
              v-else-if="revisionContent"
              class="report-export-panel__persisted-sections"
            >
              <div
                v-if="revisionContent.project_summary"
                class="report-export-panel__persisted-block"
              >
                <strong>project_summary</strong>
                <dl>
                  <div v-if="revisionContent.project_summary.project_name">
                    <dt>project_name</dt>
                    <dd>{{ revisionContent.project_summary.project_name }}</dd>
                  </div>
                  <div v-if="revisionContent.project_summary.location">
                    <dt>location</dt>
                    <dd>{{ revisionContent.project_summary.location }}</dd>
                  </div>
                  <div v-if="revisionContent.project_summary.product_category">
                    <dt>product_category</dt>
                    <dd>{{ revisionContent.project_summary.product_category }}</dd>
                  </div>
                </dl>
              </div>
              <div
                v-if="revisionContent.input_conditions"
                class="report-export-panel__persisted-block"
              >
                <strong>input_conditions</strong>
                <dl>
                  <div
                    v-for="field in operatorKeyFields"
                    :key="field"
                  >
                    <template v-if="revisionContent.input_conditions[field] !== undefined">
                      <dt>{{ field }}</dt>
                      <dd>{{ revisionContent.input_conditions[field] }}</dd>
                    </template>
                  </div>
                </dl>
              </div>
              <div
                v-if="revisionContent.calculation_logic?.stages?.length"
                class="report-export-panel__persisted-block"
              >
                <strong>calculation_logic</strong>
                <ul class="report-export-panel__formula-list">
                  <li
                    v-for="(stage, stageIndex) in revisionContent.calculation_logic.stages"
                    :key="`${stage.stage ?? 'stage'}-${stageIndex}`"
                  >
                    <span>{{ stage.stage }} ({{ stage.calculation_id }})</span>
                    <ul v-if="stage.formulas?.length">
                      <li
                        v-for="(formula, formulaIndex) in stage.formulas"
                        :key="`${formula.formula_id ?? 'formula'}-${formulaIndex}`"
                      >
                        {{ formula.formula_id }}: {{ formula.expression }}
                      </li>
                    </ul>
                  </li>
                </ul>
              </div>
              <div
                v-if="revisionContent.scheme_comparison?.review_authority"
                class="report-export-panel__persisted-block"
              >
                <strong>scheme_comparison.review_authority</strong>
                <dl>
                  <div v-if="revisionContent.scheme_comparison.review_authority.scheme_run_id">
                    <dt>scheme_run_id</dt>
                    <dd>{{ revisionContent.scheme_comparison.review_authority.scheme_run_id }}</dd>
                  </div>
                  <div v-if="revisionContent.scheme_comparison.review_authority.source_binding_id">
                    <dt>source_binding_id</dt>
                    <dd>{{ revisionContent.scheme_comparison.review_authority.source_binding_id }}</dd>
                  </div>
                  <div v-if="revisionContent.scheme_comparison.review_authority.combined_source_hash">
                    <dt>combined_source_hash</dt>
                    <dd class="report-export-panel__hash">
                      {{ revisionContent.scheme_comparison.review_authority.combined_source_hash }}
                    </dd>
                  </div>
                </dl>
              </div>
            </div>
            <div
              v-else
              class="report-export-panel__empty report-export-panel__empty--inline"
            >
              生成报告后将从此处展示已持久化的 project_summary / input_conditions / calculation_logic / scheme_comparison。
            </div>
          </div>

          <!-- Status & review workflow -->
          <div class="report-export-panel__section">
            <strong class="report-export-panel__section-title">报告状态</strong>
            <div
              v-if="reportDetailLoading"
              class="report-export-panel__loading"
            >
              加载报告状态...
            </div>
            <div
              v-else-if="reportDetailError"
              class="report-export-panel__error report-export-panel__error--inline"
            >
              {{ reportDetailError }}
            </div>
            <div
              v-else-if="reportDetail && reportDetail.id === report.id"
              class="report-export-panel__status-row"
            >
              <span>状态：{{ reportStatusLabel(reportDetail.status) }}</span>
              <span>当前版本：v{{ reportDetail.revision_number }}</span>
            </div>

            <div class="report-export-panel__review-actions">
              <p class="report-export-panel__review-note">
                以下操作向后端发起受信任操作员审核请求；按钮本身不代表生产 RBAC 授权。
              </p>
              <button
                type="button"
                class="report-export-panel__review-btn"
                :disabled="reviewLoading"
                @click="handleReviewAction('submit', report.id)"
              >
                请求提交审核
              </button>
              <button
                type="button"
                class="report-export-panel__review-btn"
                :disabled="reviewLoading"
                @click="handleReviewAction('mark-reviewed', report.id)"
              >
                请求标记已审核
              </button>
              <button
                type="button"
                class="report-export-panel__review-btn"
                :disabled="reviewLoading"
                @click="handleReviewAction('approve', report.id)"
              >
                请求批准
              </button>
              <button
                type="button"
                class="report-export-panel__generate-btn"
                :disabled="generateLoading"
                @click="handleGenerateRevision(report.id)"
              >
                {{ generateLoading ? '生成中...' : '重新生成版本' }}
              </button>
            </div>
            <div
              v-if="reviewError"
              class="report-export-panel__error report-export-panel__error--inline"
              role="alert"
            >
              {{ reviewError }}
            </div>
            <div
              v-if="generateError && selectedReportId === report.id"
              class="report-export-panel__error report-export-panel__error--inline"
              role="alert"
            >
              {{ generateError }}
            </div>
          </div>

          <!-- Persisted blockers from workflow or backend actions (draft path ignores formal gates) -->
          <div
            v-if="displayedBlockers.length"
            class="report-export-panel__blockers"
            role="status"
            data-export-scope="draft"
          >
            <strong>{{
              activeExportForm.mode === 'draft'
                ? '草稿导出阻塞项（不含正式导出门槛）'
                : '正式导出阻塞项（后端权威）'
            }}</strong>
            <ul>
              <li
                v-for="(blocker, index) in displayedBlockers"
                :key="`blocker-${blocker.code}-${index}`"
              >
                <code>{{ blocker.code }}</code> — {{ blocker.message }}
              </li>
            </ul>
          </div>

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
                    <span>语言</span>
                    <select v-model="activeExportForm.locale">
                      <option value="zh-CN">中文</option>
                      <option value="en-US">English</option>
                    </select>
                  </label>

                  <button
                    type="button"
                    class="report-export-panel__render-btn report-export-panel__render-btn--draft"
                    data-export-mode="draft"
                    :disabled="draftRenderDisabled"
                    @click="handleDraftRender(report.id, rev.revision_number)"
                  >
                    {{
                      renderLoading
                        && selectedRevisionNumber === rev.revision_number
                        && activeExportForm.mode === 'draft'
                        ? '草稿导出中...'
                        : '草稿导出'
                    }}
                  </button>
                  <button
                    type="button"
                    class="report-export-panel__render-btn report-export-panel__render-btn--formal"
                    data-export-mode="formal"
                    :disabled="formalRenderDisabled"
                    :title="exportPolicyCopy"
                    @click="handleFormalRender(report.id, rev.revision_number)"
                  >
                    {{
                      renderLoading
                        && selectedRevisionNumber === rev.revision_number
                        && activeExportForm.mode === 'formal'
                        ? '正式导出中...'
                        : '正式导出'
                    }}
                  </button>
                  <p class="report-export-panel__export-hint">
                    {{ exportPolicyCopy }}。
                  </p>
                </div>
              </li>
            </ul>
          </div>

          <!-- Render result banner -->
          <div
            v-if="renderResult && selectedReportId === report.id"
            class="report-export-panel__render-success"
          >
            <span>导出已提交 ({{ renderResult.artifact_id }})</span>
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
            <p class="report-export-panel__export-hint">
              已完成的草稿文件可直接下载，不依赖审核或正式导出资格。
            </p>

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
                        data-export-action="download"
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
  flex-wrap: wrap;
  gap: 12px;
}

.report-export-panel__policy {
  font-size: 12px;
  color: #2d4a6f;
  font-weight: 400;
}

.report-export-panel__empty p {
  margin: 0 0 8px;
}

.report-export-panel__hint {
  color: #7a4d00;
  font-size: 12px;
}

.report-export-panel__create-btn,
.report-export-panel__generate-btn {
  margin-top: 8px;
  border: 1px solid #123a63;
  border-radius: 4px;
  padding: 6px 14px;
  background: #123a63;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}

.report-export-panel__create-btn:disabled,
.report-export-panel__generate-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.report-export-panel__status-row {
  display: flex;
  gap: 16px;
  font-size: 13px;
}

.report-export-panel__review-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.report-export-panel__review-note {
  margin: 0;
  font-size: 12px;
  color: #5f7a99;
  line-height: 1.45;
}

.report-export-panel__review-btn {
  border: 1px solid #5f7a99;
  border-radius: 4px;
  padding: 4px 10px;
  background: #fff;
  color: #123a63;
  cursor: pointer;
  font-size: 12px;
}

.report-export-panel__review-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.report-export-panel__blockers {
  padding: 8px 12px;
  border-radius: 6px;
  background: #fdf0ef;
  border: 1px solid #f5c6cb;
  font-size: 12px;
  color: #7a1f1f;
}

.report-export-panel__blockers ul {
  margin: 6px 0 0;
  padding-left: 18px;
}

.report-export-panel__blockers code {
  font-size: 11px;
}

.report-export-panel__formal-note {
  padding: 8px 12px;
  border-radius: 6px;
  background: #fff4e5;
  border: 1px solid #f5c26b;
  color: #7a4d00;
  font-size: 12px;
  line-height: 1.45;
}

.report-export-panel__formal-note ul {
  margin: 6px 0 0;
  padding-left: 18px;
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

.report-export-panel__render-btn--formal {
  background: #fff;
  color: #123a63;
}

.report-export-panel__export-hint {
  margin: 0;
  flex-basis: 100%;
  font-size: 12px;
  color: #5f7a99;
  line-height: 1.45;
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
  padding: 24px 16px;
  border-radius: var(--owb-card-radius);
  background: var(--owb-surface);
  font-size: 13px;
  color: var(--owb-muted);
  text-align: center;
  line-height: 1.5;
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

.report-export-panel__persisted-sections {
  display: grid;
  gap: 12px;
}

.report-export-panel__persisted-block {
  padding: 8px 12px;
  border: 1px solid #dbe8f6;
  border-radius: 6px;
  background: #fafcfe;
  font-size: 12px;
}

.report-export-panel__persisted-block dl {
  display: grid;
  gap: 4px;
  margin: 8px 0 0;
}

.report-export-panel__persisted-block div {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 8px;
}

.report-export-panel__persisted-block dt {
  margin: 0;
  color: #6b7a8f;
}

.report-export-panel__persisted-block dd {
  margin: 0;
  word-break: break-all;
}

.report-export-panel__hash {
  font-family: monospace;
  font-size: 11px;
}

.report-export-panel__formula-list {
  margin: 8px 0 0;
  padding-left: 18px;
}
</style>
