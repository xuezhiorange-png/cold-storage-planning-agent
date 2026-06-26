<script setup lang="ts">
import { ElCard, ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ProjectInputsPanel from './ProjectInputsPanel.vue'
import { createPlanningApi } from '../../calculations/api/planningApi'
import { usePlanningWorkflowStore } from '../../../stores/planningWorkflow'
import type { PlanningRunRequest } from '../../../api/contracts/planning'

const router = useRouter()
const store = usePlanningWorkflowStore()
const planningApi = createPlanningApi()

async function handleSubmit(request: PlanningRunRequest): Promise<void> {
  store.setLoading(true)
  store.setRequest(request)
  try {
    const response = await planningApi.run(request)
    store.setResponse(response)
    ElMessage.success('规划计算完成')
    router.push('/workbench/calculations')
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : '规划运行失败'
    store.setError(message)
  }
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

      <ProjectInputsPanel :onSubmit="handleSubmit" />
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
</style>
