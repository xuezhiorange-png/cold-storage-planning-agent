<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { ElAlert, ElCard, ElTable, ElTableColumn } from 'element-plus'

import { usePersistedPlanningResultsStore } from '../../../stores/persistedPlanningResults'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import type { EquipmentPowerRowContract, PowerSummaryRowContract } from '../../../api/contracts/planning'

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

const response = computed(() => persisted.displayResponse)

const installedPowerSlot = computed(() =>
  persisted.fiveStageProgress.slots.find((slot) => slot.stage === 'power')
)

const installedPowerResult = computed(() => {
  const record = installedPowerSlot.value?.record
  return record?.result_snapshot?.result ?? null
})

const canonicalTotalPower = computed(() => {
  const result = installedPowerResult.value as Record<string, unknown> | null
  if (!result) return 0
  const total = result.total_installed_power_kw_e ?? result.total_installed_power_kw
  return typeof total === 'number' ? total : Number(total) || 0
})

const equipmentRows = computed<(EquipmentPowerRowContract & { _key: string })[]>(() => {
  const pc = response.value?.power_configuration
  if (!pc?.equipment_rows) return []
  return pc.equipment_rows.map((r, idx) => ({
    ...r,
    _key: `${idx}-${r.sequence}-${r.name}`
  }))
})

const summaryRows = computed<(PowerSummaryRowContract & { _key: string })[]>(() => {
  const pc = response.value?.power_configuration
  if (!pc?.summary_rows) return []
  return pc.summary_rows.map((r, idx) => ({
    ...r,
    _key: `summary-${idx}`
  }))
})

const supplementalTotalInstalled = computed(() => {
  return response.value?.power_configuration?.total_installed_power_kw ?? 0
})

const supplementalTotalDemand = computed(() => {
  return response.value?.power_configuration?.total_estimated_demand_kw ?? 0
})

const requiresReview = computed(() => {
  return installedPowerSlot.value?.requiresReview
    ?? response.value?.power_configuration?.requires_review
    ?? false
})

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function formatOptionalPower(value: number | null): string {
  return value === null ? '-' : `${formatNumber(value)} kW`
}
</script>

<template>
  <div class="power-page owb-page owb-page--wide">
    <ElCard class="power-page__canonical">
      <template #header>
        <span class="power-page__title">规范装机功率</span>
      </template>

      <template v-if="installedPowerSlot?.record">
        <div v-if="canonicalTotalPower > 0" class="power-page__totals">
          <div class="power-page__total-item">
            <span class="power-page__total-label">装机总功率</span>
            <span class="power-page__total-value">{{ formatNumber(canonicalTotalPower) }} kW(e)</span>
          </div>
        </div>

        <p v-if="requiresReview" class="power-page__note">
          装机功率为概念阶段估算，不能替代正式电气设计、设备铭牌功率统计或供配电校核。
        </p>
      </template>

      <div v-else class="owb-page__empty">
        <p>暂无规范装机功率结果</p>
        <p>请先在「工程输入」提交五阶段执行</p>
      </div>
    </ElCard>

    <ElCard v-if="response?.power_configuration" class="power-page__supplemental">
      <template #header>
        <span class="power-page__title">补充用电配置</span>
      </template>

      <ElAlert
        type="info"
        :closable="false"
        show-icon
        title="补充/演示表"
        description="power_configuration 为 V0.4 向后兼容补充数据，不得作为五阶段规范 power 阶段结果。"
        class="power-page__alert"
      />

      <div class="table-scroll">
        <ElTable
          :data="equipmentRows"
          stripe
          border
          size="small"
          max-height="480"
        >
          <ElTableColumn prop="sequence" label="序号" width="60" align="center" />
          <ElTableColumn prop="name" label="名称" min-width="140" />
          <ElTableColumn prop="area" label="区域" min-width="140" />
          <ElTableColumn prop="quantity" label="数量" width="80" align="right" />
          <ElTableColumn label="化霜功率" width="120" align="right">
            <template #default="scope">
              {{ formatOptionalPower((scope.row as EquipmentPowerRowContract).defrost_power_kw) }}
            </template>
          </ElTableColumn>
          <ElTableColumn label="化霜总功率" width="120" align="right">
            <template #default="scope">
              {{ formatOptionalPower((scope.row as EquipmentPowerRowContract).defrost_total_power_kw) }}
            </template>
          </ElTableColumn>
          <ElTableColumn label="运行功率" width="120" align="right">
            <template #default="scope">
              {{ formatNumber((scope.row as EquipmentPowerRowContract).running_power_kw) }} kW
            </template>
          </ElTableColumn>
          <ElTableColumn label="总功率" width="120" align="right">
            <template #default="scope">
              {{ formatNumber((scope.row as EquipmentPowerRowContract).total_power_kw) }} kW
            </template>
          </ElTableColumn>
          <template #empty>
            <span class="power-page__table-empty">暂无补充设备明细</span>
          </template>
        </ElTable>
      </div>

      <div v-if="summaryRows.length > 0" class="table-scroll" style="margin-top: 16px">
        <ElTable :data="summaryRows" stripe border size="small">
          <ElTableColumn prop="name" label="汇总项" min-width="160" />
          <ElTableColumn prop="basis" label="计算依据" min-width="200" />
          <ElTableColumn label="功率" width="140" align="right">
            <template #default="scope">
              {{ formatNumber((scope.row as PowerSummaryRowContract).total_power_kw) }} kW
            </template>
          </ElTableColumn>
        </ElTable>
      </div>

      <div v-if="supplementalTotalInstalled > 0 || supplementalTotalDemand > 0" class="power-page__totals">
        <div class="power-page__total-item">
          <span class="power-page__total-label">补充装机总功率</span>
          <span class="power-page__total-value">{{ formatNumber(supplementalTotalInstalled) }} kW</span>
        </div>
        <div class="power-page__total-item">
          <span class="power-page__total-label">补充估算需求功率</span>
          <span class="power-page__total-value">{{ formatNumber(supplementalTotalDemand) }} kW</span>
        </div>
      </div>
    </ElCard>
  </div>
</template>

<style scoped>
.power-page {
  width: 100%;
  max-width: 1400px;
  display: grid;
  gap: var(--owb-page-gap);
}

.power-page__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--owb-navy-deep);
}

.power-page__alert {
  margin-bottom: 12px;
}

.power-page__table-empty {
  color: var(--owb-muted);
  font-size: 13px;
}

.power-page__totals {
  display: flex;
  gap: 24px;
  margin-top: 16px;
  padding: 12px 16px;
  border: 1px solid var(--owb-navy-mid);
  border-radius: 6px;
  background: var(--owb-surface);
}

.power-page__total-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.power-page__total-label {
  font-weight: 600;
  color: var(--owb-navy-deep);
  font-size: 14px;
}

.power-page__total-value {
  font-weight: 700;
  font-size: 18px;
}

.power-page__note {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #fff3cd;
  border: 1px solid #ffc107;
  color: #856404;
  font-size: 12px;
  line-height: 1.4;
}
</style>
