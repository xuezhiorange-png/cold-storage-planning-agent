<script setup lang="ts">
import type { ZoneResultContract } from '../../../api/contracts/planning'

defineProps<{
  zones: ZoneResultContract[]
}>()

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function formatMass(kg: number): string {
  if (kg <= 0) return '按周转配置'
  if (kg >= 1000) return `${formatNumber(kg / 1000)} t`
  return `${formatNumber(kg)} kg`
}

function formatThroughput(value: number | undefined | null): string {
  if (value == null || value <= 0) return '-'
  return `${formatNumber(value)} kg/day`
}
</script>

<template>
  <section class="zone-results-table" aria-label="区域规划结果">
    <div v-if="zones.length === 0" class="zone-results-table__empty">
      暂无区域规划数据，请先执行计算。
    </div>
    <table v-else class="zone-results-table__table">
      <thead>
        <tr>
          <th scope="col">区域名称</th>
          <th scope="col">温区</th>
          <th scope="col">日处理量</th>
          <th scope="col">存储质量</th>
          <th scope="col">板位</th>
          <th scope="col">面积</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="zone in zones" :key="zone.zone_name">
          <td>{{ zone.zone_name }}</td>
          <td>{{ zone.temperature_band }}</td>
          <td>{{ formatThroughput(zone.daily_throughput_kg_day ?? zone.daily_throughput_kg) }}</td>
          <td>{{ formatMass(zone.design_storage_mass_kg) }}</td>
          <td>{{ zone.position_count }}</td>
          <td>{{ formatNumber(zone.required_area_m2) }} m²</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.zone-results-table {
  margin-bottom: 16px;
}

.zone-results-table__empty {
  padding: 32px 16px;
  text-align: center;
  color: #6b7a8f;
  border: 1px dashed #d0d7e2;
  border-radius: 8px;
  background: #f8f9fb;
  font-size: 14px;
}

.zone-results-table__table {
  width: 100%;
  border-collapse: collapse;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e0e6ed;
}

.zone-results-table__table th {
  background: #f0f4f8;
  color: #2c3e50;
  font-weight: 600;
  font-size: 13px;
  padding: 10px 12px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 2px solid #d0d7e2;
}

.zone-results-table__table td {
  padding: 10px 12px;
  font-size: 14px;
  color: #1a2a3a;
  border-bottom: 1px solid #e8ecf0;
}

.zone-results-table__table tbody tr:last-child td {
  border-bottom: none;
}

.zone-results-table__table tbody tr:hover {
  background: #f6f9fc;
}
</style>
