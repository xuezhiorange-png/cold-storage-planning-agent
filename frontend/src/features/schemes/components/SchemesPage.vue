<script setup lang="ts">
import { onMounted } from 'vue'
import { useSchemes } from '../composables/useSchemes'

const { data, schemes, state, error, load } = useSchemes()

onMounted(() => {
  load()
})

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
    <div v-if="state === 'loading'" class="schemes-page__status">加载方案数据...</div>
    <div v-if="error" class="schemes-page__error">{{ error }}</div>

    <template v-if="data">
      <div class="schemes-page__summary">
        <strong>{{ data.weight_set_name }}</strong>
        <span>{{ data.schemes.length }} 个方案</span>
        <em :class="{ 'status-unverified': data.weight_set_status === 'unverified' }">
          {{ data.weight_set_status === 'unverified' ? '演示权重 / 待复核' : data.weight_set_status }}
        </em>
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
                <td>可行性</td>
                <td>
                  <span :class="scheme.feasible ? 'tag-feasible' : 'tag-infeasible'">
                    {{ scheme.feasible ? '可行' : '不可行' }}
                  </span>
                </td>
              </tr>
              <tr>
                <td>总分</td>
                <td>{{ scheme.total_score }}</td>
              </tr>
              <tr>
                <td>面积</td>
                <td>{{ formatNumber(scheme.total_area_m2) }} m²</td>
              </tr>
              <tr>
                <td>板位</td>
                <td>{{ scheme.total_position_count }} 个</td>
              </tr>
              <tr>
                <td>房间 / 门</td>
                <td>{{ scheme.room_module_count }} 个 / {{ scheme.door_count }} 扇</td>
              </tr>
              <tr>
                <td>投资</td>
                <td>{{ formatWan(scheme.investment_cny) }}</td>
              </tr>
              <tr>
                <td>装机功率</td>
                <td>{{ formatNumber(scheme.installed_power_kw_e) }} kW(e)</td>
              </tr>
              <tr v-if="scheme.requires_review">
                <td>待复核</td>
                <td><span class="tag-review">是</span></td>
              </tr>
            </tbody>
          </table>

          <div v-if="!scheme.feasible" class="scheme-card__overlay">
            不可行
          </div>
        </article>
      </div>
    </template>
  </div>
</template>

<style scoped>
.schemes-page {
  max-width: 1200px;
}

.schemes-page__status {
  color: #5d6f84;
  font-size: 14px;
}

.schemes-page__error {
  padding: 8px 12px;
  border-radius: 6px;
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #991b1b;
  font-size: 13px;
}

.schemes-page__summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 10px 16px;
  border: 1px solid #123a63;
  border-radius: 8px;
  background: #f3f7fb;
}

.schemes-page__summary strong {
  font-size: 16px;
}

.schemes-page__summary span {
  font-size: 18px;
  font-weight: 700;
}

.schemes-page__summary em {
  border: 1px solid #c7d4e3;
  border-radius: 999px;
  padding: 2px 8px;
  font-style: normal;
  background: #fff;
}

.status-unverified {
  color: #d97706;
  border-color: #d97706;
}

/* ── Scheme grid ──────────────────────────────────── */
.schemes-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  gap: 16px;
}

.scheme-card {
  position: relative;
  border: 1px solid #c7d4e3;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.scheme-card--recommended {
  border-color: #123a63;
  box-shadow: 0 0 0 2px rgba(18, 58, 99, 0.15);
}

.scheme-card--infeasible {
  opacity: 0.75;
}

.scheme-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #e0e6ed;
  background: #f0f4f8;
}

.scheme-card__header strong {
  font-size: 15px;
}

.scheme-card__badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: #123a63;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.scheme-card__table {
  width: 100%;
  border-collapse: collapse;
}

.scheme-card__table td {
  padding: 6px 14px;
  border-bottom: 1px solid #eef2f6;
  font-size: 13px;
}

.scheme-card__table td:first-child {
  color: #5d6f84;
  width: 40%;
}

.scheme-card__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.6);
  color: #b91c1c;
  font-size: 20px;
  font-weight: 700;
  pointer-events: none;
}

.tag-feasible {
  color: #166534;
  font-weight: 600;
}

.tag-infeasible {
  color: #b91c1c;
  font-weight: 600;
}

.tag-review {
  color: #d97706;
  font-weight: 600;
}
</style>
