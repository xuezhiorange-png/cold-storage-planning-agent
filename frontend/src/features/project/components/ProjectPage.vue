<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { ElCard, ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ProjectInputsPanel from './ProjectInputsPanel.vue'
import { usePlanningWorkflowStore } from '../../../stores/planningWorkflow'
import { usePersistedPlanningResultsStore } from '../../../stores/persistedPlanningResults'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import type { PlanningRunRequest } from '../../../api/contracts/planning'

const router = useRouter()
const store = usePlanningWorkflowStore()
const workbench = useWorkbenchContextStore()
const persistedResults = usePersistedPlanningResultsStore()

onMounted(async () => {
  if (!workbench.isReady) {
    await workbench.initialize()
  }
})

onUnmounted(() => {
  store.cancel()
})

async function handleSubmit(request: PlanningRunRequest): Promise<void> {
  if (!workbench.isReady) {
    await workbench.initialize()
  }
  if (!workbench.projectId || workbench.versionNumber === null) {
    throw new Error('项目上下文未就绪')
  }

  const response = await store.execute(
    workbench.projectId,
    workbench.versionNumber,
    request
  )

  if (response) {
    await workbench.refreshWorkflow()
    await persistedResults.load()
    ElMessage.success('规划计算完成')
    await router.push('/workbench/calculations')
  }
}

function handleReset() {
  store.reset()
}
</script>

<template>
  <div class="project-page">
    <ElCard>
      <template #header>
        <div class="project-page__header">
          <span>项目设计输入</span>
        </div>
      </template>

      <div v-if="store.error" role="alert" class="project-page__error">
        <p>{{ store.error }}</p>
        <p>请修改输入后重试。</p>
      </div>

      <ProjectInputsPanel :on-submit="handleSubmit" :on-reset="handleReset" />
    </ElCard>
  </div>
</template>

<style scoped>
.project-page {
  max-width: 960px;
}

.project-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.project-page__error {
  margin: 0 16px 8px;
  padding: 8px 12px;
  border-radius: 4px;
  background: #fef0f0;
  color: #f56c6c;
  font-size: 13px;
  line-height: 1.4;
}
</style>
