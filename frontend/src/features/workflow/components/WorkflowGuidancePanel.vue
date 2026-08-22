<script setup lang="ts">
import { computed } from 'vue'

import type { WorkflowBlocker, WorkflowNextAction } from '../../../api/contracts/workflow'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'

const workbench = useWorkbenchContextStore()

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
const formalBlockers = computed(
  () => workflow.value?.formal_export_eligibility.blockers ?? []
)

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
          :class="`workflow-guidance__badge--${readinessStatus.toLowerCase()}`"
        >
          工作流：{{ statusLabel(readinessStatus) }}
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

    <div v-if="blockers.length" class="workflow-guidance__blockers" role="status" aria-live="polite">
      <strong>核心阻断</strong>
      <ul>
        <li v-for="(blocker, index) in blockers" :key="`${blocker.code}-${index}`">
          <span class="workflow-guidance__blocker-code">{{ blocker.code }}</span>
          {{ blocker.message }}
        </li>
      </ul>
    </div>

    <div v-if="nextActions.length" class="workflow-guidance__actions">
      <strong>下一步建议</strong>
      <ul>
        <li v-for="action in nextActions" :key="action.action_id">
          <span :class="{ 'workflow-guidance__action-disabled': !action.enabled }">
            {{ action.label }}
          </span>
          <span v-if="!action.enabled" class="workflow-guidance__action-hint">
            （需先解决阻断项）
          </span>
        </li>
      </ul>
    </div>

    <div class="workflow-guidance__formal" role="note">
      <strong>正式导出</strong>
      <span v-if="formalEligible">后端判定可尝试正式导出（P1 权威将在渲染/下载时再次校验）。</span>
      <span v-else>正式导出当前不可用；与工作流就绪状态独立判定。</span>
      <ul v-if="!formalEligible && formalBlockers.length">
        <li v-for="(blocker, index) in formalBlockers" :key="`formal-${blocker.code}-${index}`">
          {{ blocker.message }}
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.workflow-guidance {
  display: grid;
  gap: 10px;
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid #c7d4e3;
  border-radius: 8px;
  background: #f8fbff;
  font-size: 13px;
  line-height: 1.45;
}

.workflow-guidance__header {
  display: grid;
  gap: 8px;
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

.workflow-guidance__badge--ready {
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
  padding-top: 6px;
  border-top: 1px dashed #d0d7e2;
  color: #40566f;
}
</style>
