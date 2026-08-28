<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { ElCard } from 'element-plus'

import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import { useSchemes } from '../composables/useSchemes'

const workbench = useWorkbenchContextStore()
const { data, state, error, load } = useSchemes()

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
  <div class="schemes-page owb-page owb-page--wide">
    <ElCard>
      <template #header>
        <span class="schemes-page__title">方案比选</span>
      </template>

      <div v-if="state === 'loading'" class="schemes-page__status">
        <span>加载方案数据…</span>
        <button
          type="button"
          class="schemes-page__refresh"
          @click="tryLoadSchemes"
        >
          重新加载
        </button>
      </div>

      <div v-else-if="state === 'empty'" class="owb-page__empty">
        <p>暂无方案数据</p>
        <p>请先完成工程输入并查看计算结果</p>
      </div>

      <div v-else-if="state === 'unavailable'" class="schemes-page__status schemes-page__status--warn" role="status">
        方案比选服务当前不可用
        <button class="schemes-page__retry" @click="tryLoadSchemes">重试</button>
      </div>

      <div v-else-if="state === 'error'" class="schemes-page__status schemes-page__status--error schemes-page__error">
        {{ error }}
        <button class="schemes-page__retry" @click="tryLoadSchemes">重试</button>
      </div>

      <template v-else-if="state === 'success' && data">
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
    </ElCard>
  </div>
</template>

<style scoped>
.schemes-page {
  width: 100%;
  max-width: 1400px;
}

.schemes-page__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--owb-navy-deep);
}

.schemes-page__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: var(--owb-card-radius);
  background: var(--owb-surface);
  color: var(--owb-muted);
  font-size: 14px;
}

.schemes-page__status--warn {
  color: #856404;
  background: #fff8e6;
}

.schemes-page__status--error {
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
  border: 1px solid var(--owb-border);
  border-radius: 4px;
  padding: 4px 10px;
  background: #fff;
  color: var(--owb-navy-mid);
  cursor: pointer;
  font-size: 12px;
}

.schemes-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.scheme-card {
  border: 1px solid var(--owb-border-light);
  border-radius: var(--owb-card-radius);
  padding: 12px;
  background: #fff;
}

.scheme-card--recommended {
  border-color: var(--owb-navy-mid);
  box-shadow: 0 0 0 1px var(--owb-navy-mid);
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
  background: var(--owb-navy-mid);
  color: #fff;
}

.scheme-card__table {
  width: 100%;
  font-size: 13px;
}

.scheme-card__table th {
  text-align: left;
  color: var(--owb-muted-soft);
  padding: 4px 8px 4px 0;
  width: 40%;
}

.scheme-card__table td {
  padding: 4px 0;
}
</style>
