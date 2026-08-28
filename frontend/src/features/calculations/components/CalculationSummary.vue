<script setup lang="ts">
import { computed } from 'vue'

import type { PlanningRunResponse } from '../../../api/contracts/planning'

const props = defineProps<{
  summary: PlanningRunResponse['summary']
}>()

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function formatWan(value: number): string {
  return `${(value / 10000).toFixed(2)} 万元`
}

const items = computed(() => [
  {
    label: '总面积',
    value: `${formatNumber(props.summary.total_area_m2)} m²`
  },
  {
    label: '总板位',
    value: `${props.summary.total_position_count} 个`
  },
  {
    label: '总投资',
    value: formatWan(props.summary.total_investment_cny)
  },
  {
    label: '总功率',
    value: `${formatNumber(props.summary.total_power_kw)} kW`
  }
])
</script>

<template>
  <section class="calculation-summary" aria-label="计算结果概览">
    <div v-if="summary?.requires_review" class="calculation-summary__notice">
      部分参数采用演示系数，结果未经工程复核，仅供参考。
    </div>
    <div class="calculation-summary__grid">
      <div
        v-for="item in items"
        :key="item.label"
        class="calculation-summary__card"
      >
        <span class="calculation-summary__label">{{ item.label }}</span>
        <span class="calculation-summary__value">{{ item.value }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.calculation-summary {
  margin-bottom: 16px;
  display: grid;
  gap: 8px;
}

.calculation-summary__notice {
  padding: 8px 12px;
  border-radius: 6px;
  background: #fff3cd;
  border: 1px solid #ffc107;
  color: #856404;
  font-size: 13px;
  line-height: 1.4;
}

.calculation-summary__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.calculation-summary__card {
  display: grid;
  gap: 4px;
  padding: 16px;
  border-radius: var(--owb-card-radius);
  border: 1px solid var(--owb-border-light);
  background: #fff;
}

.calculation-summary__label {
  font-size: 12px;
  color: var(--owb-muted);
}

.calculation-summary__value {
  font-size: 18px;
  font-weight: 600;
  color: var(--owb-navy-deep);
}
</style>
