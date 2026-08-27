<script setup lang="ts">
import { onMounted, watch } from 'vue'

import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import { useSchemes } from '../composables/useSchemes'

const workbench = useWorkbenchContextStore()
const { data, schemes, state, error, load } = useSchemes()

function tryLoadSchemes() {
  if (workbench.projectId && workbench.versionNumber !== null) {
    load(workbench.projectId, workbench.versionNumber)
  }
}

onMounted(() => {
  tryLoadSchemes()
})

watch(
  () => [workbench.projectId, workbench.versionNumber],
  () => {
    tryLoadSchemes()
  }
)

function formatNumber(value: number | null): string {
  if (value === null) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function formatWan(value: number | null): string {
  if (value === null) return '—'
  return `${(value / 10000).toFixed(2)} 万元`
}
</script>

<template>
  <div class="schemes-page">
    <div v-if="state === 'loading'" class="schemes-page__loading-row">
      <span>加载方案数据...</span>
      <button
        type="button"
        class="schemes-page__refresh"
        @click="tryLoadSchemes"
      >
        重新加载
      </button>
    </div>
    <div v-if="state === 'empty'" class="schemes-page__empty">暂无方案数据</div>
    <div v-if="state === 'unavailable'" class="schemes-page__unavailable" role="status">
      方案比选服务当前不可用
      <button class="schemes-page__retry" @click="tryLoadSchemes">重试</button>
    </div>
    <div v-if="state === 'error'" class="schemes-page__error">
      {{ error }}
      <button class="schemes-page__retry" @click="tryLoadSchemes">重试</button>
    </div>

    <template v-if="state === 'success' && data">
      <div class="schemes-page__summary">
        <strong>{{ data.weight_set_name }}</strong>
        <span>{{ data.schemes.length }} 个方案</span>
        <em :class="{ 'status-unverified': data.weight_set_status === 'unverified' }">
          {{ data.weight_set_status === 'unverified' ? '演示权重 / 待复核' : data.weight_set_status }}
        </em>
        <em v-if="data.recommended_scheme_code === null" class="schemes-page__no-recommendation">暂无推荐方案</em>
        <button
          type="button"
          class="schemes-page__refresh"
          @click="tryLoadSchemes"
        >
          刷新
        </button>
      </div>

      <!-- Scheme cards -->
      <div class="schemes-page__grid">
        <article
          v-for="scheme in data.schemes"
          :key="scheme.scheme_code"
          class="scheme-card"
          :class="{
            'scheme-card--recommended': data.recommended_scheme_code === scheme.scheme_code,
            'scheme-card--infeasible': !scheme.feasible
          }"
        >
          <div class="scheme-card__header">
            <strong>{{ scheme.scheme_name }}</strong>
            <span
              v-if="data.recommended_scheme_code === scheme.scheme_code"
              class="scheme-card__badge"
            >推荐</span>
          </div>

          <table class="scheme-card__table">
            <tbody>
              <tr>
                <th>总分</th>
                <td>{{ scheme.total_score }}</td>
              </tr>
              <tr>
                <th>总面积</th>
                <td>{{ formatNumber(scheme.total_area_m2) }} m²</td>
              </tr>
              <tr>
                <th>总货位数</th>
                <td>{{ formatNumber(scheme.total_position_count) }}</td>
              </tr>
              <tr>
                <th>投资</th>
                <td>{{ formatWan(scheme.investment_cny) }}</td>
              </tr>
              <tr>
                <th>装机功率</th>
                <td>{{ formatNumber(scheme.installed_power_kw_e) }} kW</td>
              </tr>
            </tbody>
          </table>
        </article>
      </div>
    </template>
  </div>
</template>

<style scoped>
.schemes-page {
  width: 100%;
  max-width: 1400px;
}

.schemes-page__loading-row,
.schemes-page__empty,
.schemes-page__unavailable,
.schemes-page__error {
  padding: 16px;
  border-radius: 8px;
  background: #f8f9fb;
  color: #5f7a99;
  font-size: 14px;
}

.schemes-page__error {
  color: #c0392b;
  background: #fdf0ef;
}

.schemes-page__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 14px;
}

.schemes-page__no-recommendation {
  color: #856404;
}

.status-unverified {
  color: #9a6700;
}

.schemes-page__refresh,
.schemes-page__retry {
  border: 1px solid #b8cae0;
  border-radius: 4px;
  padding: 4px 10px;
  background: #fff;
  color: #123a63;
  cursor: pointer;
  font-size: 12px;
}

.schemes-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.scheme-card {
  border: 1px solid #dbe8f6;
  border-radius: 8px;
  padding: 12px;
  background: #fff;
}

.scheme-card--recommended {
  border-color: #123a63;
  box-shadow: 0 0 0 1px #123a63;
}

.scheme-card--infeasible {
  opacity: 0.75;
}

.scheme-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.scheme-card__badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #123a63;
  color: #fff;
}

.scheme-card__table {
  width: 100%;
  font-size: 13px;
}

.scheme-card__table th {
  text-align: left;
  color: #5f7a99;
  padding: 4px 8px 4px 0;
  width: 40%;
}

.scheme-card__table td {
  padding: 4px 0;
}
</style>
