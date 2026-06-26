<script setup lang="ts">
import { onUnmounted } from 'vue'
import { ElCard, ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ProjectInputsPanel from './ProjectInputsPanel.vue'
import { usePlanningRun } from '../../calculations/composables/usePlanningRun'
import { usePlanningWorkflowStore } from '../../../stores/planningWorkflow'
import type { PlanningRunRequest } from '../../../api/contracts/planning'

const router = useRouter()
const store = usePlanningWorkflowStore()
const planner = usePlanningRun()

let isAlive = true

onUnmounted(() => {
  isAlive = false
  planner.abort()
})

async function handleSubmit(request: PlanningRunRequest): Promise<void> {
  store.setLoading(true)
  store.setRequest(request)
  store.setError('')

  const response = await planner.execute(request)

  if (!isAlive) return

  if (response) {
    store.setResponse(response)
    ElMessage.success('规划计算完成')
    router.push('/workbench/calculations')
  } else if (planner.error.value) {
    store.setError(planner.error.value)
    throw new Error(planner.error.value)
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

      <div v-if="store.error" role="alert" class="project-page__error">
        <p>{{ store.error }}</p>
        <p>请修改输入后重试。</p>
      </div>

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
