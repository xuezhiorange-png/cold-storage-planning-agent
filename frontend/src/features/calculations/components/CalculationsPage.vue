<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { ElCard } from 'element-plus'

import CalculationSummary from './CalculationSummary.vue'
import ZoneResultsTable from './ZoneResultsTable.vue'
import FiveStageProgressPanel from '../../five-stage/components/FiveStageProgressPanel.vue'
import { usePersistedPlanningResultsStore } from '../../../stores/persistedPlanningResults'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'

const workbench = useWorkbenchContextStore()
const persisted = usePersistedPlanningResultsStore()

onMounted(() => {
  persisted.load()
})

watch(
  () => [workbench.projectId, workbench.versionNumber] as const,
  () => {
    persisted.load()
  }
)
</script>

<template>
  <div class="calculations-page">
    <FiveStageProgressPanel :progress="persisted.fiveStageProgress" />

    <template v-if="persisted.displayResponse?.summary && persisted.displayResponse.zone_plan?.result">
      <CalculationSummary :summary="persisted.displayResponse.summary" />
      <ElCard>
        <template #header>
          <span>区域规划结果</span>
        </template>
        <ZoneResultsTable :zones="persisted.displayResponse.zone_plan.result.zones" />
      </ElCard>
    </template>

    <div
      v-else-if="!persisted.fiveStageProgress.chainComplete"
      class="calculations-page__empty"
    >
      <p>暂无完整五阶段计算结果。</p>
      <p>请在「工程输入」页面填写 EngineeringInputBundleV1 并提交五阶段执行。</p>
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
