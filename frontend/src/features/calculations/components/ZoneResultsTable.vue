<script setup lang="ts">
import type { ZoneResultContract } from '../../../api/contracts/planning'
import { formatAisleLayout, formatSchemeId } from './persistedResultLabels'

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

function formatOptionalInt(value: number | undefined): string {
  return value == null ? '—' : String(value)
}

function packedDimensions(zone: ZoneResultContract): string | null {
  const nLong = zone.n_long ?? zone.layout?.n_long
  const nShort = zone.n_short ?? zone.layout?.n_short
  if (nLong == null || nShort == null) return null
  return `${nLong}×${nShort}`
}

function hasExtendedDetails(zone: ZoneResultContract): boolean {
  return Boolean(
  zone.schemes?.length
    || zone.n_need != null
    || zone.pallet_count != null
    || zone.truck_count != null
    || zone.platform_count != null
  )
}

function hasShippingDocks(zone: ZoneResultContract): boolean {
  return zone.pallet_count != null || zone.truck_count != null || zone.platform_count != null
}
</script>

<template>
  <section class="zone-results-table" aria-label="区域规划结果">
    <div v-if="zones.length === 0" class="zone-results-table__empty">
      暂无区域规划数据，请先执行计算。
    </div>
    <div v-else class="table-scroll">
      <table class="zone-results-table__table">
        <thead>
          <tr>
            <th scope="col">区域名称</th>
            <th scope="col">温区</th>
            <th scope="col">日处理量</th>
            <th scope="col">存储质量</th>
            <th scope="col">板位 (6位汇报)</th>
            <th scope="col">面积 (6位汇报)</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="zone in zones" :key="zone.zone_code ?? zone.zone_name">
            <tr>
              <td>
                {{ zone.zone_name }}
                <span v-if="zone.zone_code" class="zone-results-table__zone-code">{{ zone.zone_code }}</span>
              </td>
              <td>{{ zone.temperature_band }}</td>
              <td>{{ formatThroughput(zone.daily_throughput_kg_day ?? zone.daily_throughput_kg) }}</td>
              <td>{{ formatMass(zone.design_storage_mass_kg) }}</td>
              <td>{{ zone.position_count }}</td>
              <td>{{ formatNumber(zone.required_area_m2) }} m²</td>
            </tr>
            <tr v-if="hasExtendedDetails(zone)" class="zone-results-table__detail-row">
              <td colspan="6">
                <div class="zone-results-table__details">
                  <div v-if="zone.schemes?.length" class="zone-results-table__detail-block">
                    <strong>预冷方案</strong>
                    <ul class="zone-results-table__scheme-list">
                      <li v-for="scheme in zone.schemes" :key="scheme.scheme_id">
                        {{ formatSchemeId(scheme.scheme_id) }}：间数 {{ scheme.room_count }}，板位
                        {{ scheme.position_count }}，面积 {{ formatNumber(scheme.required_area_m2) }} m²
                      </li>
                    </ul>
                    <span v-if="zone.reporting_scheme_id" class="zone-results-table__reporting-scheme">
                      6位汇报方案：{{ formatSchemeId(zone.reporting_scheme_id) }}
                    </span>
                  </div>
                  <div v-if="zone.n_need != null" class="zone-results-table__detail-block">
                    <strong>板位排布</strong>
                    <span>需求 {{ formatOptionalInt(zone.n_need) }}</span>
                    <span v-if="zone.n_actual != null">，实际 {{ zone.n_actual }}</span>
                    <span v-if="zone.unused_cells != null">，空余 {{ zone.unused_cells }}</span>
                    <span v-if="packedDimensions(zone)">，排布 {{ packedDimensions(zone) }}</span>
                    <span v-if="zone.aisle_layout">，通道 {{ formatAisleLayout(zone.aisle_layout) }}</span>
                  </div>
                  <div v-if="hasShippingDocks(zone)" class="zone-results-table__detail-block">
                    <strong>出货通道</strong>
                    <span v-if="zone.pallet_count != null">托盘 {{ zone.pallet_count }}</span>
                    <span v-if="zone.truck_count != null">，车数 {{ zone.truck_count }}</span>
                    <span v-if="zone.platform_count != null">，月台 {{ zone.platform_count }}</span>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
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

.zone-results-table__zone-code {
  display: block;
  font-size: 12px;
  color: #6b7a8f;
  margin-top: 2px;
}

.zone-results-table__detail-row td {
  background: #f8f9fb;
  border-bottom: 1px solid #e8ecf0;
  padding-top: 6px;
  padding-bottom: 10px;
}

.zone-results-table__details {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  font-size: 13px;
  color: #4a5a6a;
}

.zone-results-table__detail-block {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
}

.zone-results-table__scheme-list {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
}

.zone-results-table__scheme-list li {
  margin: 2px 0;
}

.zone-results-table__reporting-scheme {
  font-size: 12px;
  color: #6b7a8f;
}
</style>
