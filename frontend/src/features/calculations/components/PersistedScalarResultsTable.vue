<script setup lang="ts">
import type { PersistedScalarField } from './persistedResultLabels'

defineProps<{
  fields: Array<PersistedScalarField & { value: string }>
}>()
</script>

<template>
  <div class="table-scroll">
    <table class="persisted-scalar-table">
      <thead>
        <tr>
          <th scope="col">项目</th>
          <th scope="col">数值</th>
          <th scope="col">单位</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="field in fields" :key="field.key">
          <td>{{ field.label }}</td>
          <td>{{ field.value }}</td>
          <td>{{ field.unit || '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.persisted-scalar-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.persisted-scalar-table th,
.persisted-scalar-table td {
  border: 1px solid #d0d7e2;
  padding: 8px 10px;
  text-align: left;
}

.persisted-scalar-table th {
  background: #f3f7fb;
  font-weight: 600;
}

.persisted-scalar-table td:nth-child(2) {
  font-weight: 500;
}
</style>
