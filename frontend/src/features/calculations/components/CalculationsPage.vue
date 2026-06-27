<script setup lang="ts">
import { ElCard } from 'element-plus'

import CalculationSummary from './CalculationSummary.vue'
import ZoneResultsTable from './ZoneResultsTable.vue'
import { usePlanningWorkflowStore } from '../../../stores/planningWorkflow'

const store = usePlanningWorkflowStore()
const response = store.latestResponse
</script>

<template>
  <div class="calculations-page">
    <template v-if="response">
      <CalculationSummary :summary="response.summary" />
      <ElCard>
        <template #header>
          <span>区域规划结果</span>
        </template>
        <ZoneResultsTable :zones="response.zone_plan.result.zones" />
      </ElCard>
    </template>

    <div v-else class="calculations-page__empty">
      <p>暂无计算结果。</p>
      <p>请在「基本信息」页面输入参数并生成规划。</p>
    </div>
  </div>
</template>

<style scoped>
.calculations-page {
  max-width: 960px;
  display: grid;
  gap: 16px;
}

.calculations-page__empty {
  padding: 48px 24px;
  text-align: center;
  color: #6b7a8f;
  border: 1px dashed #d0d7e2;
  border-radius: 8px;
  background: #f8f9fb;
  font-size: 14px;
}

.calculations-page__empty p {
  margin: 4px 0;
}
</style>
