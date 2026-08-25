<script setup lang="ts">
import { computed } from 'vue'
import { ElCard } from 'element-plus'

import ReportExportPanel from '../../reports/components/ReportExportPanel.vue'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'

const workbench = useWorkbenchContextStore()

const projectId = computed(() => workbench.projectId ?? undefined)
const projectVersionId = computed(
  () => workbench.workflow?.project_context.project_version_id ?? undefined
)
const formalExportEligible = computed(
  () => workbench.formalExportEligibility?.eligible ?? false
)
const formalExportBlockers = computed(
  () => workbench.formalExportEligibility?.blockers ?? []
)
</script>

<template>
  <div class="reports-page">
    <ElCard>
      <template #header>
        <span>报告输出</span>
      </template>

      <ReportExportPanel
        :project-id="projectId"
        :project-version-id="projectVersionId"
        :formal-export-eligible="formalExportEligible"
        :formal-export-blockers="formalExportBlockers"
      />
    </ElCard>
  </div>
</template>

<style scoped>
.reports-page {
  max-width: 960px;
}
</style>
