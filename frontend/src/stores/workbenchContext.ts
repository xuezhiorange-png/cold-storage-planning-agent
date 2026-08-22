import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { CapabilityProjectionEntry } from '../api/contracts/capabilities'
import type { WorkflowAggregateV1 } from '../api/contracts/workflow'
import { createProjectsApi, type ProjectsApi } from '../features/workflow/api/projectsApi'
import { createRuntimeApi, type RuntimeApi } from '../features/workflow/api/runtimeApi'
import { createWorkflowApi, type WorkflowApi } from '../features/workflow/api/workflowApi'

const STORAGE_KEY = 'cold_storage_workbench_context'

interface StoredWorkbenchContext {
  projectId: string
  versionNumber: number
}

function readStoredContext(): StoredWorkbenchContext | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredWorkbenchContext
    if (parsed.projectId && Number.isFinite(parsed.versionNumber)) {
      return parsed
    }
  } catch {
    return null
  }
  return null
}

function writeStoredContext(context: StoredWorkbenchContext): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(context))
}

export const useWorkbenchContextStore = defineStore('workbenchContext', () => {
  const projectId = ref<string | null>(null)
  const versionNumber = ref<number | null>(null)
  const projectName = ref('')
  const projectCode = ref('')
  const workflow = ref<WorkflowAggregateV1 | null>(null)
  const capabilities = ref<CapabilityProjectionEntry[]>([])
  const isInitializing = ref(false)
  const isRefreshingWorkflow = ref(false)
  const error = ref('')

  const isReady = computed(() => projectId.value !== null && versionNumber.value !== null)
  const workflowReadiness = computed(() => workflow.value?.workflow_readiness ?? null)
  const formalExportEligibility = computed(() => workflow.value?.formal_export_eligibility ?? null)
  const agentAssistance = computed(() => workflow.value?.agent_assistance ?? null)

  let workflowAbort: AbortController | null = null
  let initializePromise: Promise<void> | null = null

  async function ensureProject(
    projectsApi: ProjectsApi = createProjectsApi()
  ): Promise<void> {
    const stored = readStoredContext()
    if (stored) {
      try {
        const project = await projectsApi.getProject(stored.projectId)
        projectId.value = project.id
        versionNumber.value = stored.versionNumber
        projectName.value = project.name
        projectCode.value = project.code
        return
      } catch {
        localStorage.removeItem(STORAGE_KEY)
      }
    }

    const created = await projectsApi.createProject({
      name: '蓝莓冷库规划',
      location: '山东',
      product_category: 'blueberry'
    })
    projectId.value = created.id
    versionNumber.value = created.current_version_number
    projectName.value = '蓝莓冷库规划'
    projectCode.value = created.code
    writeStoredContext({
      projectId: created.id,
      versionNumber: created.current_version_number
    })
  }

  async function loadCapabilities(runtimeApi: RuntimeApi = createRuntimeApi()): Promise<void> {
    try {
      const response = await runtimeApi.getReady()
      capabilities.value = response.capabilities ?? []
    } catch {
      capabilities.value = []
    }
  }

  async function refreshWorkflow(
    workflowApi: WorkflowApi = createWorkflowApi()
  ): Promise<WorkflowAggregateV1 | null> {
    if (!projectId.value || versionNumber.value === null) {
      return null
    }

    workflowAbort?.abort()
    const controller = new AbortController()
    workflowAbort = controller
    isRefreshingWorkflow.value = true
    error.value = ''

    try {
      const aggregate = await workflowApi.getAggregate(
        projectId.value,
        versionNumber.value,
        'formal_report',
        controller.signal
      )
      if (!controller.signal.aborted) {
        workflow.value = aggregate
        projectName.value = aggregate.project_context.project_name
        projectCode.value = aggregate.project_context.project_code
      }
      return aggregate
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return null
      }
      error.value = err instanceof Error ? err.message : '工作流状态加载失败'
      return null
    } finally {
      if (!controller.signal.aborted) {
        isRefreshingWorkflow.value = false
      }
    }
  }

  async function initialize(
    projectsApi: ProjectsApi = createProjectsApi(),
    workflowApi: WorkflowApi = createWorkflowApi(),
    runtimeApi: RuntimeApi = createRuntimeApi()
  ): Promise<void> {
    if (initializePromise) {
      await initializePromise
      return
    }

    initializePromise = (async () => {
      isInitializing.value = true
      error.value = ''
      try {
        await ensureProject(projectsApi)
        await Promise.all([loadCapabilities(runtimeApi), refreshWorkflow(workflowApi)])
      } catch (err: unknown) {
        error.value = err instanceof Error ? err.message : '工作台初始化失败'
      } finally {
        isInitializing.value = false
      }
    })()

    try {
      await initializePromise
    } finally {
      initializePromise = null
    }
  }

  function resetForTests(): void {
    workflowAbort?.abort()
    initializePromise = null
    projectId.value = null
    versionNumber.value = null
    projectName.value = ''
    projectCode.value = ''
    workflow.value = null
    capabilities.value = []
    isInitializing.value = false
    isRefreshingWorkflow.value = false
    error.value = ''
    localStorage.removeItem(STORAGE_KEY)
  }

  return {
    projectId,
    versionNumber,
    projectName,
    projectCode,
    workflow,
    capabilities,
    isInitializing,
    isRefreshingWorkflow,
    error,
    isReady,
    workflowReadiness,
    formalExportEligibility,
    agentAssistance,
    ensureProject,
    loadCapabilities,
    refreshWorkflow,
    initialize,
    resetForTests
  }
})
