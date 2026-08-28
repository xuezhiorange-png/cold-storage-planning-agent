<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { ElCard, ElTable, ElTableColumn } from 'element-plus'

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

interface InvestmentRow {
  item_name: string
  amount_cny: number
}

const response = computed(() => persisted.displayResponse)

const investmentItems = computed<InvestmentRow[]>(() => {
  const r = response.value
  if (!r?.investment_estimate?.result?.items) return []
  return r.investment_estimate.result.items
})

const totalCny = computed(() => {
  return response.value?.summary?.total_investment_cny ?? null
})

function formatWan(value: number): string {
  return `${(value / 10000).toFixed(2)}`
}
</script>

<template>
  <div class="investment-page owb-page owb-page--wide">
    <ElCard v-if="investmentItems.length > 0">
      <template #header>
        <span class="investment-page__title">投资估算</span>
      </template>

      <div class="table-scroll">
        <ElTable :data="investmentItems" stripe border size="small">
          <ElTableColumn prop="item_name" label="投资分项" min-width="200" />
          <ElTableColumn label="估算金额" width="180" align="right">
            <template #default="scope">
              {{ formatWan((scope.row as InvestmentRow).amount_cny) }} 万元
            </template>
          </ElTableColumn>
        </ElTable>
      </div>

      <div class="investment-page__total">
        <strong>合计</strong>
        <span v-if="totalCny !== null">{{ formatWan(totalCny) }} 万元</span>
        <span v-else>—</span>
      </div>

      <p class="investment-page__note">
        投资测算使用 demo / unverified 演示单价，未包含土地、税费、融资、正式设计费和专项工程费用。
      </p>
    </ElCard>

    <ElCard v-else>
      <template #header>
        <span class="investment-page__title">投资估算</span>
      </template>
      <div class="owb-page__empty">
        <p>暂无投资估算数据</p>
        <p>请先在「工程输入」填写五个过程参数并提交</p>
      </div>
    </ElCard>
  </div>
</template>

<style scoped>
.investment-page {
  width: 100%;
  max-width: 1400px;
}

.investment-page__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--owb-navy-deep);
}

.investment-page__total {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 16px;
  border: 1px solid var(--owb-navy-mid);
  border-radius: 6px;
  background: var(--owb-surface);
  font-size: 16px;
}

.investment-page__total strong {
  color: var(--owb-navy-deep);
}

.investment-page__total span {
  font-weight: 700;
  font-size: 18px;
}

.investment-page__note {
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
