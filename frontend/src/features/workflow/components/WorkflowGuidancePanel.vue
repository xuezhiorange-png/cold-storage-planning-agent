<script setup lang="ts">
import { computed, onMounted } from 'vue'

import type { WorkflowBlocker, WorkflowNextAction } from '../../../api/contracts/workflow'
import { usePersistedPlanningResultsStore } from '../../../stores/persistedPlanningResults'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'

const OPERATOR_NEXT_STEPS = new Set([
  'PROJECT_INPUT',
  'INPUT_COMPLETENESS',
  'DETERMINISTIC_CALCULATION',
  'SCHEME_COMPARISON'
])

const NON_CORE_BLOCKER_CODES = new Set([
  'INPUT_REQUIRES_REVIEW',
  'CALCULATION_REQUIRES_REVIEW',
  'SCHEME_REVIEW_REQUIRED',
  'HUMAN_REVIEW_PENDING',
  'APPROVAL_PENDING',
  'APPROVAL_STALE',
  'REVIEW_REASONS_UNRESOLVED',
  'FORMAL_REPORT_NOT_APPROVED',
  'REPORT_MISSING',
  'REPORT_REVISION_STALE',
  'REPORT_QUALITY_BLOCKER',
  'KNOWLEDGE_PROVENANCE_PENDING',
  'KNOWLEDGE_PROVENANCE_UNAVAILABLE'
])

const NON_CORE_BLOCKER_STAGES = new Set([
  'FORMAL_REPORT',
  'REVIEW_BLOCKER',
  'HUMAN_REVIEW',
  'APPROVAL',
  'KNOWLEDGE_PROVENANCE'
])

const SCHEME_MISSING_NUDGE_MESSAGE = '还没跑生产方案评分，请到计算结果页运行'

const SCHEME_MISSING_NEXT_ACTION: WorkflowNextAction = {
  action_id: 'action-calculations-production-scheme',
  type: 'SCHEME_COMPARISON',
  target_step: 'SCHEME_COMPARISON',
  label: '前往计算结果页运行生产方案评分',
  reason: '五阶段结果已持久化，请在计算结果页运行生产方案评分',
  required: true,
  enabled: true,
  blocked_by: []
}

const workbench = useWorkbenchContextStore()
const persisted = usePersistedPlanningResultsStore()

const workflow = computed(() => workbench.workflow)
const readinessStatus = computed(() => workflow.value?.workflow_readiness.status ?? 'UNKNOWN')
const currentStep = computed(() => workflow.value?.current_step ?? '')
const blockers = computed<WorkflowBlocker[]>(() => workflow.value?.blockers ?? [])
const nextActions = computed<WorkflowNextAction[]>(
  () => workflow.value?.next_required_actions ?? []
)
const revisionStale = computed(() => workflow.value?.project_context.revision_stale ?? false)
const formalEligible = computed(
  () => workflow.value?.formal_export_eligibility.eligible ?? false
)
const fiveStagePersisted = computed(() => persisted.fiveStageProgress.chainComplete)

function isCoreOperatorBlocker(blocker: WorkflowBlocker): boolean {
  const code = blocker.code ?? ''
  const stage = blocker.stage ?? ''
  if (NON_CORE_BLOCKER_STAGES.has(stage)) return false
  if (NON_CORE_BLOCKER_CODES.has(code)) return false
  if (code.includes('REQUIRES_REVIEW') || code.includes('REVIEW_REQUIRED')) return false
  if (code.startsWith('FORMAL_') || code.startsWith('KNOWLEDGE_PROVENANCE')) return false
  return true
}

const coreBlockers = computed(() => blockers.value.filter(isCoreOperatorBlocker))

const schemeMissingOnly = computed(() => {
  if (!fiveStagePersisted.value) return false
  const core = coreBlockers.value
  return core.length === 1 && core[0]?.code === 'SCHEME_MISSING'
})

const displayCoreBlockers = computed<WorkflowBlocker[]>(() => {
  if (schemeMissingOnly.value) {
    return [{ code: 'SCHEME_MISSING', message: SCHEME_MISSING_NUDGE_MESSAGE }]
  }
  return coreBlockers.value
})

const operatorNextActions = computed(() =>
  nextActions.value.filter((action) => {
    return OPERATOR_NEXT_STEPS.has(action.type) || OPERATOR_NEXT_STEPS.has(action.target_step)
  })
)

const displayOperatorNextActions = computed(() => {
  if (schemeMissingOnly.value) {
    return [SCHEME_MISSING_NEXT_ACTION]
  }
  return operatorNextActions.value
})

const displayReadiness = computed(() => {
  if (schemeMissingOnly.value) return 'IN_PROGRESS'
  const raw = readinessStatus.value
  if (coreBlockers.value.length > 0) return raw
  if (raw === 'BLOCKED' || raw === 'REVIEW_REQUIRED') return 'IN_PROGRESS'
  return raw
})

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    READY: '可继续',
    NOT_READY: '未就绪',
    BLOCKED: '已阻断',
    STALE: '数据过期',
    UNAVAILABLE: '不可用',
    IN_PROGRESS: '进行中',
    REVIEW_REQUIRED: '待复核'
  }
  return labels[status] ?? status
}

onMounted(() => {
  if (workbench.isReady) {
    void persisted.load()
  }
})
</script>

<template>
  <section
    class="workflow-guidance"
    aria-label="工作流引导"
    :aria-busy="workbench.isRefreshingWorkflow"
  >
    <header class="workflow-guidance__header">
      <div class="workflow-guidance__context">
        <strong v-if="workbench.projectName">{{ workbench.projectName }}</strong>
        <span v-if="workbench.versionNumber !== null">
          版本 {{ workbench.versionNumber }}
        </span>
        <span v-if="workbench.projectCode" class="workflow-guidance__code">
          {{ workbench.projectCode }}
        </span>
      </div>
      <div class="workflow-guidance__status-row">
        <span
          class="workflow-guidance__badge"
          :class="`workflow-guidance__badge--${displayReadiness.toLowerCase()}`"
        >
          工作流：{{ statusLabel(displayReadiness) }}
        </span>
        <span
          v-if="revisionStale"
          class="workflow-guidance__badge workflow-guidance__badge--stale"
        >
          修订已过期
        </span>
        <span v-if="currentStep" class="workflow-guidance__current-step">
          当前步骤：{{ currentStep.replace(/_/g, ' ') }}
        </span>
      </div>
    </header>

    <div
      v-if="workbench.error"
      class="workflow-guidance__error"
      role="alert"
    >
      {{ workbench.error }}
    </div>

    <div
      v-if="displayCoreBlockers.length"
      class="workflow-guidance__blockers"
      role="status"
      aria-live="polite"
    >
      <strong>核心阻断</strong>
      <ul>
        <li
          v-for="(blocker, index) in displayCoreBlockers"
          :key="`${blocker.code}-${index}`"
        >
          <span
            v-if="!schemeMissingOnly"
            class="workflow-guidance__blocker-code"
          >
            {{ blocker.code }}
          </span>
          {{ blocker.message }}
        </li>
      </ul>
    </div>

    <div v-if="displayOperatorNextActions.length" class="workflow-guidance__actions">
      <strong>下一步建议</strong>
      <ul>
        <li v-for="action in displayOperatorNextActions" :key="action.action_id">
          <span :class="{ 'workflow-guidance__action-disabled': !action.enabled }">
            {{ action.label }}
          </span>
          <span
            v-if="!action.enabled && displayCoreBlockers.length && !schemeMissingOnly"
            class="workflow-guidance__action-hint"
          >
            （需先解决阻断项）
          </span>
        </li>
      </ul>
    </div>

    <p class="workflow-guidance__formal" role="note">
      <strong>正式导出</strong>
      正式导出与草稿导出不是同一件事；本条不阻止继续填写/计算。
      <span v-if="formalEligible" class="workflow-guidance__formal-eligible">
        后端判定可尝试正式导出（P4 报告页将再次校验）。
      </span>
    </p>
  </section>
</template>

<style scoped>
.workflow-guidance {
  display: grid;
  gap: 8px;
  margin-bottom: 0;
  padding: 10px 12px;
  border: 1px solid #c7d4e3;
  border-radius: 8px;
  background: #f8fbff;
  font-size: 13px;
  line-height: 1.45;
}

.workflow-guidance__header {
  display: grid;
  gap: 6px;
}

.workflow-guidance__context {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
}

.workflow-guidance__code {
  color: #5f7a99;
  font-size: 12px;
}

.workflow-guidance__status-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.workflow-guidance__badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: #e8edf4;
  color: #123a63;
}

.workflow-guidance__badge--ready,
.workflow-guidance__badge--in_progress {
  background: #e8f5e9;
  color: #1b5e20;
}

.workflow-guidance__badge--blocked,
.workflow-guidance__badge--stale {
  background: #fdecea;
  color: #b42318;
}

.workflow-guidance__badge--not_ready {
  background: #fff4e5;
  color: #9a6700;
}

.workflow-guidance__current-step {
  color: #40566f;
  font-size: 12px;
}

.workflow-guidance__error {
  padding: 8px 10px;
  border-radius: 6px;
  background: #fdecea;
  color: #b42318;
}

.workflow-guidance ul {
  margin: 4px 0 0;
  padding-left: 18px;
}

.workflow-guidance__blocker-code {
  font-weight: 600;
  margin-right: 4px;
}

.workflow-guidance__action-disabled {
  color: #6b7280;
}

.workflow-guidance__action-hint {
  color: #9ca3af;
  font-size: 12px;
}

.workflow-guidance__formal {
  margin: 0;
  padding-top: 6px;
  border-top: 1px dashed #d0d7e2;
  color: #5f7a99;
  font-size: 12px;
}

.workflow-guidance__formal-eligible {
  display: block;
  margin-top: 4px;
  color: #40566f;
}
</style>
