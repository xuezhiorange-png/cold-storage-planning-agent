import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { createDefaultEngineeringInputFormState } from '../features/five-stage/model/engineeringInputForm'
import { useFiveStageExecutionStore } from '../stores/fiveStageExecution'
import { useWorkbenchContextStore } from '../stores/workbenchContext'

describe('fiveStageExecution store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useWorkbenchContextStore().resetForTests()
    useFiveStageExecutionStore().resetForTests()
    sessionStorage.clear()
  })

  it('posts five-stage-execution and surfaces field_path errors', async () => {
    const workbench = useWorkbenchContextStore()
    workbench.projectId = 'proj-1'
    workbench.versionNumber = 1

    const execute = vi.fn().mockResolvedValue({
      error: {
        code: 'MISSING_ENGINEERING_PARAMETER',
        message: 'zone area required',
        field_path: 'cooling_load_inputs.zones[0].zone_area'
      }
    })

    const store = useFiveStageExecutionStore()
    const outcome = await store.execute(
      createDefaultEngineeringInputFormState(),
      {
        projectId: 'proj-1',
        projectVersionId: 'ver-1',
        versionNumber: 1,
        versionStatus: 'draft',
        isArchived: false,
        actorPrincipal: 'test',
        correlationId: 'corr-1'
      },
      { execute }
    )

    expect(outcome).toBeNull()
    expect(execute).toHaveBeenCalledOnce()
    expect(store.fieldError?.code).toBe('MISSING_ENGINEERING_PARAMETER')
    expect(store.fieldError?.formKey).toBe('coolingZones.0.zoneArea')
  })

  it('reuses idempotency key for the same project version', async () => {
    const workbench = useWorkbenchContextStore()
    workbench.projectId = 'proj-1'
    workbench.versionNumber = 1

    const store = useFiveStageExecutionStore()
    const key1 = store.getOrCreateIdempotencyKey('proj-1', 1)
    const key2 = store.getOrCreateIdempotencyKey('proj-1', 1)
    expect(key1).toBe(key2)
  })
})
