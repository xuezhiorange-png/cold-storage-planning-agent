<script setup lang="ts">
import { computed } from 'vue'
import { ElCard } from 'element-plus'

import ReportExportPanel from '../../reports/components/ReportExportPanel.vue'
import {
  DRAFT_EXPORT_POLICY_COPY,
  FORMAL_EXPORT_POLICY_COPY
} from '../../reports/composables/useReportExport'
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
const exportPolicyCopy = `${FORMAL_EXPORT_POLICY_COPY}，${DRAFT_EXPORT_POLICY_COPY}`
</script>

<template>
  <div class="reports-page owb-page">
    <ElCard>
      <template #header>
        <span class="reports-page__title">报告输出</span>
      </template>

      <p class="reports-page__policy">
        {{ exportPolicyCopy }}。浏览器审核请求不是生产 RBAC。
      </p>

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
.reports-page__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--owb-navy-deep);
}

.reports-page__policy {
  margin: 0 0 12px;
  font-size: 13px;
  color: #2d4a6f;
  line-height: 1.5;
}
</style>
