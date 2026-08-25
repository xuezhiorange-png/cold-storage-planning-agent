import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type {
  EngineeringInputBundleV1,
  FiveStageExecutionSuccess
} from '../api/contracts/fiveStage'
import {
  createFiveStageApi,
  type FiveStageApi
} from '../features/five-stage/api/fiveStageApi'
import {
  buildEngineeringInputBundle,
  type BuildBundleContext,
  type EngineeringInputFormState,
  fieldPathToFormKey,
  stableBundlePayloadJson
} from '../features/five-stage/model/engineeringInputForm'
import { useWorkbenchContextStore } from './workbenchContext'

const IDEM_STORAGE_PREFIX = 'five_stage_idem_key'
const LAST_BUNDLE_STORAGE_PREFIX = 'five_stage_last_bundle'

export interface FiveStageFieldError {
  fieldPath: string
  formKey: string | null
  code: string
  message: string
}

export const useFiveStageExecutionStore = defineStore('fiveStageExecution', () => {
  const isExecuting = ref(false)
  const lastSuccess = ref<FiveStageExecutionSuccess | null>(null)
  const fieldError = ref<FiveStageFieldError | null>(null)
  const generalError = ref('')
  const lastSubmittedBundleJson = ref<string | null>(null)

  let executeAbort: AbortController | null = null

  const hasFieldError = computed(() => fieldError.value !== null)

  function idempotencyStorageKey(projectId: string, version: number): string {
    return `${IDEM_STORAGE_PREFIX}:${projectId}:${version}`
  }

  function lastBundleStorageKey(projectId: string, version: number): string {
    return `${LAST_BUNDLE_STORAGE_PREFIX}:${projectId}:${version}`
  }

  function getOrCreateIdempotencyKey(projectId: string, version: number): string {
    const storageKey = idempotencyStorageKey(projectId, version)
    const existing = sessionStorage.getItem(storageKey)
    if (existing) return existing
    const created = crypto.randomUUID()
    sessionStorage.setItem(storageKey, created)
    return created
  }

  function clearErrors(): void {
    fieldError.value = null
    generalError.value = ''
  }

  async function execute(
    form: EngineeringInputFormState,
    bundleContext: BuildBundleContext,
    fiveStageApi: FiveStageApi = createFiveStageApi()
  ): Promise<FiveStageExecutionSuccess | null> {
    const workbench = useWorkbenchContextStore()
    if (!workbench.projectId || workbench.versionNumber === null) {
      generalError.value = '项目上下文未就绪'
      return null
    }

    executeAbort?.abort()
    const controller = new AbortController()
    executeAbort = controller
    isExecuting.value = true
    clearErrors()

    const bundle = buildEngineeringInputBundle(form, bundleContext)
    const bundleJson = stableBundlePayloadJson(bundle)
    const idempotencyKey = getOrCreateIdempotencyKey(workbench.projectId, workbench.versionNumber)

    try {
      const response = await fiveStageApi.execute(
        workbench.projectId,
        workbench.versionNumber,
        {
          engineering_input_bundle: bundle,
          idempotency_key: idempotencyKey
        },
        controller.signal
      )

      if (controller.signal.aborted) return null

      if ('error' in response) {
        fieldError.value = {
          fieldPath: response.error.field_path,
          formKey: fieldPathToFormKey(response.error.field_path),
          code: response.error.code,
          message: response.error.message
        }
        generalError.value = response.error.message
        return null
      }

      lastSuccess.value = response
      lastSubmittedBundleJson.value = bundleJson
      sessionStorage.setItem(
        lastBundleStorageKey(workbench.projectId, workbench.versionNumber),
        bundleJson
      )
      return response
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return null
      }
      generalError.value = err instanceof Error ? err.message : '五阶段执行失败'
      return null
    } finally {
      if (!controller.signal.aborted) {
        isExecuting.value = false
      }
    }
  }

  function cancel(): void {
    executeAbort?.abort()
    isExecuting.value = false
  }

  function resetForTests(): void {
    executeAbort?.abort()
    isExecuting.value = false
    lastSuccess.value = null
    fieldError.value = null
    generalError.value = ''
    lastSubmittedBundleJson.value = null
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index)
      if (key?.startsWith(IDEM_STORAGE_PREFIX) || key?.startsWith(LAST_BUNDLE_STORAGE_PREFIX)) {
        sessionStorage.removeItem(key)
      }
    }
  }

  return {
    isExecuting,
    lastSuccess,
    fieldError,
    generalError,
    hasFieldError,
    lastSubmittedBundleJson,
    execute,
    cancel,
    clearErrors,
    getOrCreateIdempotencyKey,
    resetForTests
  }
})
