<script setup lang="ts">
import { computed } from 'vue'
import { ElAlert, ElCard, ElTag } from 'element-plus'

import type { FiveStageProgressView, FiveStageSlotView } from '../model/mapFiveStageCalculations'

const props = defineProps<{
  progress: FiveStageProgressView
}>()

const statusLabel: Record<FiveStageSlotView['status'], string> = {
  missing: '缺失',
  present: '已持久化',
  partial: '部分完成',
  stale: '已过期',
  locked: '已锁定',
  error: '错误'
}

const statusType: Record<FiveStageSlotView['status'], 'info' | 'success' | 'warning' | 'danger'> = {
  missing: 'info',
  present: 'success',
  partial: 'warning',
  stale: 'warning',
  locked: 'info',
  error: 'danger'
}

const progressSummary = computed(() => {
  return `${props.progress.completedCount} / ${props.progress.totalCount} 阶段已持久化`
})
</script>

<template>
  <ElCard class="five-stage-progress-panel">
    <template #header>
      <div class="five-stage-progress-panel__header">
        <span>五阶段工程链进度</span>
        <span class="five-stage-progress-panel__summary">{{ progressSummary }}</span>
      </div>
    </template>

    <ElAlert
      v-if="progress.hasPartialChain"
      type="warning"
      :closable="false"
      show-icon
      title="五阶段链不完整"
      description="存在部分持久化结果；请完成全部五个规范阶段。power_configuration 不能替代 installed_power。"
      class="five-stage-progress-panel__alert"
    />

    <div class="five-stage-progress-panel__slots">
      <article
        v-for="slot in progress.slots"
        :key="slot.stage"
        class="five-stage-progress-panel__slot"
        :data-stage="slot.stage"
        :data-status="slot.status"
      >
        <div class="five-stage-progress-panel__slot-header">
          <strong>{{ slot.label }}</strong>
          <ElTag :type="statusType[slot.status]" size="small">
            {{ statusLabel[slot.status] }}
          </ElTag>
        </div>
        <p class="five-stage-progress-panel__calculator">{{ slot.calculatorName }}</p>

        <dl v-if="slot.record" class="five-stage-progress-panel__meta">
          <div v-if="slot.calculationId">
            <dt>calculation_id</dt>
            <dd>{{ slot.calculationId }}</dd>
          </div>
          <div v-if="slot.resultHash">
            <dt>result_hash</dt>
            <dd class="five-stage-progress-panel__hash">{{ slot.resultHash }}</dd>
          </div>
          <div>
            <dt>requires_review</dt>
            <dd>{{ slot.requiresReview ? 'true' : 'false' }}</dd>
          </div>
        </dl>

        <ul v-if="slot.warnings.length > 0" class="five-stage-progress-panel__warnings">
          <li v-for="(warning, index) in slot.warnings" :key="`${slot.stage}-warning-${index}`">
            {{ warning }}
          </li>
        </ul>

        <ul v-if="slot.staleReasons.length > 0" class="five-stage-progress-panel__stale">
          <li v-for="(reason, index) in slot.staleReasons" :key="`${slot.stage}-stale-${index}`">
            {{ reason }}
          </li>
        </ul>
      </article>
    </div>

    <ElAlert
      v-if="progress.supplementalPowerConfiguration"
      type="info"
      :closable="false"
      show-icon
      title="V0.4 补充用电配置 (power_configuration)"
      description="此为补充/演示表，不能替代规范 installed_power 阶段。"
      class="five-stage-progress-panel__alert"
    />
  </ElCard>
</template>

<style scoped>
.five-stage-progress-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.five-stage-progress-panel__summary {
  font-size: 13px;
  color: #6b7a8f;
}

.five-stage-progress-panel__alert {
  margin-bottom: 12px;
}

.five-stage-progress-panel__slots {
  display: grid;
  gap: 12px;
}

.five-stage-progress-panel__slot {
  padding: 12px;
  border: 1px solid #d0d7e2;
  border-radius: 8px;
  background: #fafbfc;
}

.five-stage-progress-panel__slot-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.five-stage-progress-panel__calculator {
  margin: 4px 0 8px;
  font-size: 12px;
  color: #6b7a8f;
}

.five-stage-progress-panel__meta {
  display: grid;
  gap: 4px;
  margin: 0;
  font-size: 12px;
}

.five-stage-progress-panel__meta div {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px;
}

.five-stage-progress-panel__meta dt {
  margin: 0;
  color: #6b7a8f;
}

.five-stage-progress-panel__meta dd {
  margin: 0;
  word-break: break-all;
}

.five-stage-progress-panel__hash {
  font-family: monospace;
  font-size: 11px;
}

.five-stage-progress-panel__warnings,
.five-stage-progress-panel__stale {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: #856404;
}

.five-stage-progress-panel__stale {
  color: #c45656;
}
</style>
