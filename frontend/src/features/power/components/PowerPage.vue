<script setup lang="ts">
import { computed } from 'vue'
import { ElCard, ElTable, ElTableColumn } from 'element-plus'

import { usePlanningWorkflowStore } from '../../../stores/planningWorkflow'
import type { EquipmentPowerRowContract, PowerSummaryRowContract } from '../../../api/contracts/planning'

const store = usePlanningWorkflowStore()

const response = computed(() => store.latestResponse)

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

const totalInstalled = computed(() => {
  return response.value?.power_configuration?.total_installed_power_kw ?? 0
})

const totalDemand = computed(() => {
  return response.value?.power_configuration?.total_estimated_demand_kw ?? 0
})

const requiresReview = computed(() => {
  return response.value?.power_configuration?.requires_review ?? false
})

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function formatOptionalPower(value: number | null): string {
  return value === null ? '-' : `${formatNumber(value)} kW`
}
</script>

<template>
  <div class="power-page">
    <template v-if="response && equipmentRows.length > 0">
      <ElCard>
        <template #header>
          <span>用电配置</span>
        </template>

        <!-- Equipment table -->
        <div class="table-scroll">
          <ElTable :data="equipmentRows" stripe border size="small" max-height="480">
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
          </ElTable>
        </div>

        <!-- Summary table -->
        <div v-if="summaryRows.length > 0" class="table-scroll" style="margin-top: 16px">
          <ElTable
            :data="summaryRows"
            stripe
            border
            size="small"
          >
            <ElTableColumn prop="name" label="汇总项" min-width="160" />
            <ElTableColumn prop="basis" label="计算依据" min-width="200" />
            <ElTableColumn label="功率" width="140" align="right">
              <template #default="scope">
                {{ formatNumber((scope.row as PowerSummaryRowContract).total_power_kw) }} kW
              </template>
            </ElTableColumn>
          </ElTable>
        </div>

        <!-- Totals -->
        <div class="power-page__totals">
          <div class="power-page__total-item">
            <span class="power-page__total-label">装机总功率</span>
            <span class="power-page__total-value">{{ formatNumber(totalInstalled) }} kW</span>
          </div>
          <div class="power-page__total-item">
            <span class="power-page__total-label">估算需求功率</span>
            <span class="power-page__total-value">{{ formatNumber(totalDemand) }} kW</span>
          </div>
        </div>

        <p v-if="requiresReview" class="power-page__note">
          用电配置为概念阶段估算，不能替代正式电气设计、设备铭牌功率统计或供配电校核。
        </p>
      </ElCard>
    </template>

    <div v-else class="power-page__empty">
      <p>暂无用电配置数据。</p>
      <p>请在「基本信息」页面生成规划。</p>
    </div>
  </div>
</template>

<style scoped>
.power-page {
  max-width: 1200px;
}

.power-page__totals {
  display: flex;
  gap: 24px;
  margin-top: 16px;
  padding: 12px 16px;
  border: 1px solid #123a63;
  border-radius: 6px;
  background: #f3f7fb;
}

.power-page__total-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.power-page__total-label {
  font-weight: 600;
  color: #0b1f3a;
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

.power-page__empty {
  padding: 48px 24px;
  text-align: center;
  color: #6b7a8f;
  border: 1px dashed #d0d7e2;
  border-radius: 8px;
  background: #f8f9fb;
  font-size: 14px;
}

.power-page__empty p {
  margin: 4px 0;
}
</style>
