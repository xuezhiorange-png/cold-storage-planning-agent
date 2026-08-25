<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElAlert, ElButton, ElCard, ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import EngineeringInputBundleForm from './EngineeringInputBundleForm.vue'
import { createProjectsApi } from '../../workflow/api/projectsApi'
import { createDefaultEngineeringInputFormState } from '../model/engineeringInputForm'
import { isVersionLocked } from '../model/mapFiveStageCalculations'
import { useFiveStageExecutionStore } from '../../../stores/fiveStageExecution'
import { usePersistedPlanningResultsStore } from '../../../stores/persistedPlanningResults'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'

const router = useRouter()
const workbench = useWorkbenchContextStore()
const execution = useFiveStageExecutionStore()
const persisted = usePersistedPlanningResultsStore()

const formState = ref(createDefaultEngineeringInputFormState())
const projectVersionId = ref('')
const versionStatus = ref('draft')
const isArchived = ref(false)

const versionLocked = computed(() => isVersionLocked(versionStatus.value) || isArchived.value)

onMounted(async () => {
  if (!workbench.isReady) {
    await workbench.initialize()
  }
  await loadVersionContext()
})

async function loadVersionContext(): Promise<void> {
  if (!workbench.projectId || workbench.versionNumber === null) return
  const version = await createProjectsApi().getVersion(
    workbench.projectId,
    workbench.versionNumber
  )
  projectVersionId.value = version.id
  versionStatus.value = version.status
  isArchived.value = version.status.toLowerCase() === 'archived'
}

async function handleSubmit(): Promise<void> {
  if (versionLocked.value) {
    ElMessage.warning('当前版本已锁定，无法提交五阶段执行')
    return
  }
  if (!workbench.projectId || workbench.versionNumber === null || !projectVersionId.value) {
    ElMessage.error('项目上下文未就绪')
    return
  }

  const outcome = await execution.execute(formState.value, {
    projectId: workbench.projectId,
    projectVersionId: projectVersionId.value,
    versionNumber: workbench.versionNumber,
    versionStatus: versionStatus.value,
    isArchived: isArchived.value,
    actorPrincipal: 'workbench-user',
    correlationId: crypto.randomUUID()
  })

  if (outcome) {
    await workbench.refreshWorkflow()
    await persisted.load()
    ElMessage.success(outcome.idempotent_replay ? '五阶段执行（幂等重放）' : '五阶段执行完成')
    await router.push('/workbench/calculations')
  }
}
</script>

<template>
  <div class="engineering-inputs-page">
    <ElCard>
      <template #header>
        <div class="engineering-inputs-page__header">
          <span>五阶段工程输入 (EngineeringInputBundleV1)</span>
        </div>
      </template>

      <ElAlert
        v-if="versionLocked"
        type="warning"
        :closable="false"
        show-icon
        title="版本已锁定"
        description="已批准或已归档版本不可提交五阶段执行。请查看持久化结果。"
        class="engineering-inputs-page__alert"
      />

      <ElAlert
        v-if="execution.generalError && !execution.fieldError"
        type="error"
        :closable="false"
        show-icon
        :title="execution.generalError"
        class="engineering-inputs-page__alert"
      />

      <EngineeringInputBundleForm
        v-model="formState"
        :field-error="execution.fieldError"
        :disabled="versionLocked || execution.isExecuting"
      />

      <div class="engineering-inputs-page__actions">
        <ElButton
          type="primary"
          :loading="execution.isExecuting"
          :disabled="versionLocked"
          @click="handleSubmit"
        >
          提交五阶段执行
        </ElButton>
      </div>
    </ElCard>
  </div>
</template>

<style scoped>
.engineering-inputs-page {
  max-width: 960px;
}

.engineering-inputs-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.engineering-inputs-page__alert {
  margin-bottom: 16px;
}

.engineering-inputs-page__actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}
</style>
