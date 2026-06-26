<script setup lang="ts">
import { computed } from 'vue'
import { ElCard, ElTable, ElTableColumn } from 'element-plus'

import { usePlanningWorkflowStore } from '../../../stores/planningWorkflow'

const store = usePlanningWorkflowStore()

interface InvestmentRow {
  item_name: string
  amount_cny: number
}

const investmentItems = computed<InvestmentRow[]>(() => {
  const r = store.latestResponse
  if (!r?.investment_estimate?.result?.items) return []
  return r.investment_estimate.result.items
})

const totalCny = computed(() => {
  return investmentItems.value.reduce((sum, item) => sum + item.amount_cny, 0)
})

function formatWan(value: number): string {
  return `${(value / 10000).toFixed(2)}`
}
</script>

<template>
  <div class="investment-page">
    <template v-if="investmentItems.length > 0">
      <ElCard>
        <template #header>
          <span>投资估算</span>
        </template>

        <ElTable :data="investmentItems" stripe border size="small">
          <ElTableColumn prop="item_name" label="投资分项" min-width="200" />
          <ElTableColumn label="估算金额" width="180" align="right">
            <template #default="scope">
              {{ formatWan((scope.row as InvestmentRow).amount_cny) }} 万元
            </template>
          </ElTableColumn>
        </ElTable>

        <div class="investment-page__total">
          <strong>合计</strong>
          <span>{{ formatWan(totalCny) }} 万元</span>
        </div>

        <p class="investment-page__note">
          投资测算使用 demo / unverified 演示单价，未包含土地、税费、融资、正式设计费和专项工程费用。
        </p>
      </ElCard>
    </template>

    <div v-else class="investment-page__empty">
      <p>暂无投资估算数据。</p>
      <p>请在「基本信息」页面生成规划。</p>
    </div>
  </div>
</template>

<style scoped>
.investment-page {
  max-width: 760px;
}

.investment-page__total {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 16px;
  border: 1px solid #123a63;
  border-radius: 6px;
  background: #f3f7fb;
  font-size: 16px;
}

.investment-page__total strong {
  color: #0b1f3a;
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

.investment-page__empty {
  padding: 48px 24px;
  text-align: center;
  color: #6b7a8f;
  border: 1px dashed #d0d7e2;
  border-radius: 8px;
  background: #f8f9fb;
  font-size: 14px;
}

.investment-page__empty p {
  margin: 4px 0;
}
</style>
