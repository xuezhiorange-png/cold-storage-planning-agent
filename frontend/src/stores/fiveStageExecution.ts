import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { FiveStageExecutionSuccess } from '../api/contracts/fiveStage'
import {
  createFiveStageApi,
  type FiveStageApi
} from '../features/five-stage/api/fiveStageApi'
import {
  buildEngineeringInputBundle,
  type BuildBundleContext,
  type EngineeringInputFormState,
  fieldPathToFormKey,
  stableBundlePayloadJson,
  stableEngineeringFieldsJson,
  type SubmitBundleContext
} from '../features/five-stage/model/engineeringInputForm'
import { useWorkbenchContextStore } from './workbenchContext'

const IDEM_STORAGE_PREFIX = 'five_stage_idem_key'
const LAST_BUNDLE_STORAGE_PREFIX = 'five_stage_last_bundle'
const CORRELATION_ID_STORAGE_PREFIX = 'five_stage_correlation_id'
const ENGINEERING_FIELDS_STORAGE_PREFIX = 'five_stage_engineering_fields'

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

  function correlationIdStorageKey(projectId: string, version: number): string {
    return `${CORRELATION_ID_STORAGE_PREFIX}:${projectId}:${version}`
  }

  function engineeringFieldsStorageKey(projectId: string, version: number): string {
    return `${ENGINEERING_FIELDS_STORAGE_PREFIX}:${projectId}:${version}`
  }

  function readStoredBundleJson(projectId: string, version: number): string | null {
    return (
      sessionStorage.getItem(lastBundleStorageKey(projectId, version)) ??
      lastSubmittedBundleJson.value
    )
  }

  function resolveCorrelationId(
    projectId: string,
    version: number,
    engineeringFieldsJson: string
  ): string {
    const correlationStorage = correlationIdStorageKey(projectId, version)
    const fieldsStorage = engineeringFieldsStorageKey(projectId, version)
    const storedCorrelationId = sessionStorage.getItem(correlationStorage)
    const storedFieldsJson = sessionStorage.getItem(fieldsStorage)

    if (storedCorrelationId && storedFieldsJson === engineeringFieldsJson) {
      return storedCorrelationId
    }

    const correlationId = crypto.randomUUID()
    sessionStorage.setItem(correlationStorage, correlationId)
    sessionStorage.setItem(fieldsStorage, engineeringFieldsJson)
    return correlationId
  }

  function resolveIdempotencyKey(projectId: string, version: number, bundleJson: string): string {
    const keyStorage = idempotencyStorageKey(projectId, version)
    const bundleStorage = lastBundleStorageKey(projectId, version)
    const storedKey = sessionStorage.getItem(keyStorage)
    const storedBundleJson = readStoredBundleJson(projectId, version)

    if (storedKey && storedBundleJson === bundleJson) {
      return storedKey
    }

    const newKey = crypto.randomUUID()
    sessionStorage.setItem(keyStorage, newKey)
    sessionStorage.setItem(bundleStorage, bundleJson)
    return newKey
  }

  function buildBundleContext(
    form: EngineeringInputFormState,
    submitContext: SubmitBundleContext
  ): BuildBundleContext {
    const engineeringFieldsJson = stableEngineeringFieldsJson(form)
    return {
      ...submitContext,
      correlationId: resolveCorrelationId(
        submitContext.projectId,
        submitContext.versionNumber,
        engineeringFieldsJson
      )
    }
  }

  function clearErrors(): void {
    fieldError.value = null
    generalError.value = ''
  }

  async function execute(
    form: EngineeringInputFormState,
    submitContext: SubmitBundleContext,
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

    const bundleContext = buildBundleContext(form, submitContext)
    const bundle = buildEngineeringInputBundle(form, bundleContext)
    const bundleJson = stableBundlePayloadJson(bundle)
    const idempotencyKey = resolveIdempotencyKey(
      workbench.projectId,
      workbench.versionNumber,
      bundleJson
    )

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
      sessionStorage.setItem(
        idempotencyStorageKey(workbench.projectId, workbench.versionNumber),
        idempotencyKey
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
      if (
        key?.startsWith(IDEM_STORAGE_PREFIX) ||
        key?.startsWith(LAST_BUNDLE_STORAGE_PREFIX) ||
        key?.startsWith(CORRELATION_ID_STORAGE_PREFIX) ||
        key?.startsWith(ENGINEERING_FIELDS_STORAGE_PREFIX)
      ) {
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
    buildBundleContext,
    resolveCorrelationId,
    resolveIdempotencyKey,
    resetForTests
  }
})
