<script setup lang="ts">
import { computed } from 'vue'

import type {
  KnowledgePageEvidenceProjection,
  KnowledgeProvenanceProjection,
  KnowledgeSourceReferenceProjection,
  WorkflowBlocker
} from '../../../api/contracts/workflow'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'

const workbench = useWorkbenchContextStore()

const provenance = computed<KnowledgeProvenanceProjection | null>(
  () => workbench.workflow?.knowledge_provenance ?? null
)
const status = computed(() => provenance.value?.status ?? 'UNKNOWN')
const sourceReferences = computed<KnowledgeSourceReferenceProjection[]>(
  () => provenance.value?.source_references ?? []
)
const blockers = computed<WorkflowBlocker[]>(() => provenance.value?.blockers ?? [])

const isQuiet = computed(() => {
  if (!provenance.value) return true
  if (provenance.value.required === false) return true
  if (status.value === 'NOT_REQUIRED') return true
  if (
    (status.value === 'UNKNOWN' || status.value === '') &&
    sourceReferences.value.length === 0 &&
    blockers.value.length === 0
  ) {
    return true
  }
  return false
})

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    NOT_REQUIRED: '无需溯源',
    AVAILABLE: '溯源可用',
    PENDING: '溯源待完成',
    INVALID: '溯源无效',
    UNKNOWN: '未知'
  }
  return labels[value] ?? value
}

function extractionMethodLabel(method: string | undefined): string {
  if (method === 'ocr') return 'OCR'
  if (method === 'native_text') return '原生文本'
  return method ?? '—'
}

function formatConfidence(page: KnowledgePageEvidenceProjection): string {
  if (page.confidence === null || page.confidence === undefined) {
    return page.confidence_source === 'unavailable' ? '不可用' : '—'
  }
  return String(page.confidence)
}
</script>

<template>
  <section
    class="knowledge-provenance"
    :class="{ 'knowledge-provenance--quiet': isQuiet }"
    aria-label="知识溯源"
    :aria-busy="workbench.isRefreshingWorkflow"
  >
    <header class="knowledge-provenance__header">
      <strong>知识溯源</strong>
      <span
        class="knowledge-provenance__badge"
        :class="`knowledge-provenance__badge--${(isQuiet ? 'NOT_REQUIRED' : status).toLowerCase()}`"
      >
        {{ isQuiet ? statusLabel('NOT_REQUIRED') : statusLabel(status) }}
      </span>
    </header>

    <p v-if="isQuiet" class="knowledge-provenance__note" role="status">
      当前工作流输出未引用知识库修订，无需展示 OCR/页面溯源。
    </p>

    <div
      v-else-if="blockers.length"
      class="knowledge-provenance__blockers"
      role="status"
      aria-live="polite"
    >
      <strong>溯源阻断</strong>
      <ul>
        <li v-for="(blocker, index) in blockers" :key="`${blocker.code}-${index}`">
          <span class="knowledge-provenance__blocker-code">{{ blocker.code }}</span>
          {{ blocker.message }}
        </li>
      </ul>
    </div>

    <div v-if="!isQuiet && sourceReferences.length" class="knowledge-provenance__sources">
      <article
        v-for="source in sourceReferences"
        :key="source.revision_id"
        class="knowledge-provenance__source"
      >
        <header class="knowledge-provenance__source-header">
          <div>
            <strong v-if="source.document_code">{{ source.document_code }}</strong>
            <span v-if="source.document_title" class="knowledge-provenance__muted">
              {{ source.document_title }}
            </span>
          </div>
          <div class="knowledge-provenance__meta">
            <span v-if="source.original_filename">{{ source.original_filename }}</span>
            <span v-if="source.version_label">版本 {{ source.version_label }}</span>
            <span v-if="source.revision_number !== undefined">
              修订 #{{ source.revision_number }}
            </span>
          </div>
          <div class="knowledge-provenance__meta knowledge-provenance__hash">
            内容哈希 {{ source.content_sha256 }}
          </div>
          <div class="knowledge-provenance__meta">
            入库状态 {{ source.ingestion_status }}
            · 复核 {{ source.review_status ?? '—' }}
            <span v-if="source.requires_review" class="knowledge-provenance__review-flag">
              需复核
            </span>
          </div>
        </header>

        <p
          v-if="!source.page_evidence_available"
          class="knowledge-provenance__missing"
          role="status"
        >
          页面证据缺失；未伪造溯源数据。
        </p>

        <table
          v-else
          class="knowledge-provenance__table"
          aria-label="页面溯源明细"
        >
          <thead>
            <tr>
              <th scope="col">页码</th>
              <th scope="col">证据 ID</th>
              <th scope="col">提取方式</th>
              <th scope="col">状态</th>
              <th scope="col">复核</th>
              <th scope="col">置信度</th>
              <th scope="col">OCR</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="page in source.page_evidence" :key="page.source_page_evidence_id">
              <td>{{ page.page_number }}</td>
              <td class="knowledge-provenance__evidence-id">
                {{ page.source_page_evidence_id }}
              </td>
              <td>{{ extractionMethodLabel(page.extraction_method) }}</td>
              <td>{{ page.extraction_status }}</td>
              <td>
                {{ page.review_status ?? '—' }}
                <span v-if="page.requires_review" class="knowledge-provenance__review-flag">
                  需复核
                </span>
              </td>
              <td>{{ formatConfidence(page) }}</td>
              <td>{{ page.is_ocr_derived ? '是' : '否' }}</td>
            </tr>
          </tbody>
        </table>
      </article>
    </div>

    <p
      v-else-if="!isQuiet && status !== 'NOT_REQUIRED' && !sourceReferences.length"
      class="knowledge-provenance__missing"
      role="status"
    >
      未找到可展示的知识修订引用；溯源数据未伪造。
    </p>
  </section>
</template>

<style scoped>
.knowledge-provenance {
  display: grid;
  gap: 8px;
  margin-bottom: 0;
  padding: 10px 12px;
  border: 1px solid #d8e2ec;
  border-radius: 8px;
  background: #fafcfe;
  font-size: 13px;
  line-height: 1.45;
}

.knowledge-provenance--quiet {
  padding: 8px 12px;
  background: #f7f9fb;
  border-color: #e4ebf3;
  color: #5f7a99;
}

.knowledge-provenance--quiet .knowledge-provenance__note {
  margin: 0;
  font-size: 12px;
}

.knowledge-provenance__header {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.knowledge-provenance__badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: #e8edf4;
  color: #123a63;
}

.knowledge-provenance__badge--available {
  background: #e8f5e9;
  color: #1b5e20;
}

.knowledge-provenance__badge--pending {
  background: #fff4e5;
  color: #9a6700;
}

.knowledge-provenance__badge--invalid,
.knowledge-provenance__badge--unknown {
  background: #fdecea;
  color: #b42318;
}

.knowledge-provenance__badge--not_required {
  background: #eef2f7;
  color: #40566f;
}

.knowledge-provenance__note,
.knowledge-provenance__missing {
  color: #40566f;
}

.knowledge-provenance__blockers {
  padding: 8px 10px;
  border-radius: 6px;
  background: #f8fafc;
  border: 1px solid #e4ebf3;
  color: #40566f;
}

.knowledge-provenance__blockers ul,
.knowledge-provenance__sources {
  margin: 0;
  padding: 0;
  list-style: none;
}

.knowledge-provenance__blockers ul {
  margin-top: 4px;
  padding-left: 18px;
  list-style: disc;
}

.knowledge-provenance__blocker-code {
  font-weight: 600;
  margin-right: 4px;
}

.knowledge-provenance__source {
  padding-top: 8px;
  border-top: 1px dashed #d0d7e2;
}

.knowledge-provenance__source:first-child {
  border-top: none;
  padding-top: 0;
}

.knowledge-provenance__source-header {
  display: grid;
  gap: 4px;
  margin-bottom: 8px;
}

.knowledge-provenance__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  color: #5f7a99;
  font-size: 12px;
}

.knowledge-provenance__hash {
  font-family: ui-monospace, monospace;
  word-break: break-all;
}

.knowledge-provenance__muted {
  color: #5f7a99;
}

.knowledge-provenance__review-flag {
  color: #9a6700;
  font-weight: 600;
}

.knowledge-provenance__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.knowledge-provenance__table th,
.knowledge-provenance__table td {
  padding: 6px 8px;
  border: 1px solid #d8e2ec;
  text-align: left;
  vertical-align: top;
}

.knowledge-provenance__table th {
  background: #f3f7fb;
  font-weight: 600;
}

.knowledge-provenance__evidence-id {
  font-family: ui-monospace, monospace;
  word-break: break-all;
  max-width: 220px;
}
</style>
