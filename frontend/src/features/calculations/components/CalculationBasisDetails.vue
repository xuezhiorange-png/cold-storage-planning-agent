<script setup lang="ts">
import type { PersistedFormulaEntry } from '../../../api/contracts/calculations'

defineProps<{
  formulas?: PersistedFormulaEntry[]
  assumptions?: string[]
  warnings?: string[]
  calculationId?: string | null
  resultHash?: string | null
}>()
</script>

<template>
  <details
    v-if="
      (formulas && formulas.length > 0)
        || (assumptions && assumptions.length > 0)
        || (warnings && warnings.length > 0)
        || calculationId
        || resultHash
    "
    class="calculation-basis-details"
  >
    <summary>计算依据</summary>

    <section v-if="formulas && formulas.length > 0" class="calculation-basis-details__section">
      <h4>公式</h4>
      <ul>
        <li v-for="(formula, index) in formulas" :key="`formula-${index}`">
          <span v-if="formula.formula_id">{{ formula.formula_id }}：</span>
          <span v-if="formula.expression">{{ formula.expression }}</span>
          <span v-if="formula.description"> — {{ formula.description }}</span>
        </li>
      </ul>
    </section>

    <section v-if="assumptions && assumptions.length > 0" class="calculation-basis-details__section">
      <h4>假设</h4>
      <ul>
        <li v-for="(assumption, index) in assumptions" :key="`assumption-${index}`">
          {{ assumption }}
        </li>
      </ul>
    </section>

    <section
      v-if="warnings && warnings.length > 0"
      class="calculation-basis-details__section calculation-basis-details__section--warnings"
    >
      <h4>警告</h4>
      <ul>
        <li v-for="(warning, index) in warnings" :key="`warning-${index}`">
          {{ warning }}
        </li>
      </ul>
    </section>

    <dl
      v-if="calculationId || resultHash"
      class="calculation-basis-details__meta"
    >
      <div v-if="calculationId">
        <dt>计算标识</dt>
        <dd>{{ calculationId }}</dd>
      </div>
      <div v-if="resultHash">
        <dt>结果哈希</dt>
        <dd class="calculation-basis-details__hash">{{ resultHash }}</dd>
      </div>
    </dl>
  </details>
</template>

<style scoped>
.calculation-basis-details {
  margin-top: 12px;
  font-size: 12px;
}

.calculation-basis-details summary {
  cursor: pointer;
  font-weight: 600;
  color: #2c3e50;
}

.calculation-basis-details__section {
  margin-top: 10px;
}

.calculation-basis-details__section h4 {
  margin: 0 0 4px;
  font-size: 13px;
}

.calculation-basis-details__section ul {
  margin: 0;
  padding-left: 18px;
}

.calculation-basis-details__section--warnings {
  color: #856404;
}

.calculation-basis-details__meta {
  display: grid;
  gap: 4px;
  margin: 10px 0 0;
}

.calculation-basis-details__meta div {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: 8px;
}

.calculation-basis-details__meta dt {
  margin: 0;
  color: #6b7a8f;
}

.calculation-basis-details__meta dd {
  margin: 0;
  word-break: break-all;
}

.calculation-basis-details__hash {
  font-family: monospace;
  font-size: 11px;
}
</style>
