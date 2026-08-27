<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { ElCard } from 'element-plus'

import CalculationSummary from './CalculationSummary.vue'
import CoolingLoadResultsTable from './CoolingLoadResultsTable.vue'
import EquipmentResultsTable from './EquipmentResultsTable.vue'
import InstalledPowerResultsTable from './InstalledPowerResultsTable.vue'
import InvestmentResultsTable from './InvestmentResultsTable.vue'
import ZoneResultsTable from './ZoneResultsTable.vue'
import FiveStageProgressPanel from '../../five-stage/components/FiveStageProgressPanel.vue'
import { EMPTY_STAGE_COPY } from '../model/mapPersistedCalculations'
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

const hasAnyPersistedStage = computed(
  () => persisted.fiveStageProgress.completedCount > 0
)

const coolingSlot = computed(() =>
  persisted.fiveStageProgress.slots.find((slot) => slot.stage === 'cooling_load')
)
const equipmentSlot = computed(() =>
  persisted.fiveStageProgress.slots.find((slot) => slot.stage === 'equipment')
)
const powerSlot = computed(() =>
  persisted.fiveStageProgress.slots.find((slot) => slot.stage === 'power')
)
const investmentSlot = computed(() =>
  persisted.fiveStageProgress.slots.find((slot) => slot.stage === 'investment')
)

const zoneTableRows = computed(() => {
  const zones = persisted.displayResponse?.zone_plan?.result?.zones
  return zones && zones.length > 0 ? zones : []
})
</script>

<template>
  <div class="calculations-page">
    <FiveStageProgressPanel :progress="persisted.fiveStageProgress" />

    <template v-if="hasAnyPersistedStage">
      <CalculationSummary
        v-if="persisted.displayResponse?.summary"
        :summary="persisted.displayResponse.summary"
      />
      <p
        v-if="persisted.displayResponse?.summary?.total_area_m2_8_position_scheme != null"
        class="calculations-page__eight-position-caption"
      >
        全厂 8 位方案总面积（持久化）：
        {{ persisted.displayResponse.summary.total_area_m2_8_position_scheme }} m²
      </p>

      <ElCard>
        <template #header>
          <span>区域规划结果</span>
        </template>
        <ZoneResultsTable
          v-if="zoneTableRows.length > 0"
          :zones="zoneTableRows"
        />
        <p v-else class="calculations-page__stage-empty">{{ EMPTY_STAGE_COPY }}</p>
      </ElCard>

      <ElCard>
        <template #header>
          <span>冷负荷结果</span>
        </template>
        <CoolingLoadResultsTable :record="coolingSlot?.record ?? null" />
      </ElCard>

      <ElCard>
        <template #header>
          <span>设备选型结果</span>
        </template>
        <EquipmentResultsTable :record="equipmentSlot?.record ?? null" />
      </ElCard>

      <ElCard>
        <template #header>
          <span>装机功率结果 (installed_power)</span>
        </template>
        <InstalledPowerResultsTable :record="powerSlot?.record ?? null" />
      </ElCard>

      <ElCard>
        <template #header>
          <span>投资估算结果</span>
        </template>
        <InvestmentResultsTable :record="investmentSlot?.record ?? null" />
      </ElCard>
    </template>

    <div
      v-else
      class="calculations-page__empty"
    >
      <p>暂无完整五阶段计算结果。</p>
      <p>请在「工程输入」填写五个过程 KEY 并提交 OperatorProcessInputV1。</p>
    </div>
  </div>
</template>

<style scoped>
.calculations-page {
  max-width: 1400px;
  display: grid;
  gap: 16px;
}

.calculations-page__eight-position-caption {
  margin: 0;
  font-size: 13px;
  color: #6b7a8f;
}

.calculations-page__stage-empty {
  margin: 0;
  padding: 16px;
  text-align: center;
  color: #6b7a8f;
  border: 1px dashed #d0d7e2;
  border-radius: 8px;
  background: #f8f9fb;
  font-size: 14px;
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
