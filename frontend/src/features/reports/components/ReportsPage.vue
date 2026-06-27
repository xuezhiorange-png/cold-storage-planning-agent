<script setup lang="ts">
import { ref } from 'vue'
import { ElCard, ElInput } from 'element-plus'

import ReportExportPanel from '../../reports/components/ReportExportPanel.vue'

const reportId = ref('')
</script>

<template>
  <div class="reports-page">
    <ElCard>
      <template #header>
        <span>报告输出</span>
      </template>

      <div class="reports-page__input-row">
        <label class="reports-page__label">
          <span>项目 ID</span>
          <ElInput
            v-model="reportId"
            placeholder="可选，留空使用当前项目"
            size="small"
            clearable
          />
        </label>
      </div>

      <ReportExportPanel :project-id="reportId || undefined" />
    </ElCard>
  </div>
</template>

<style scoped>
.reports-page {
  max-width: 960px;
}

.reports-page__input-row {
  margin-bottom: 16px;
}

.reports-page__label {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
  align-items: center;
  max-width: 400px;
}

.reports-page__label span {
  font-size: 13px;
  color: #40566f;
  white-space: nowrap;
}
</style>
