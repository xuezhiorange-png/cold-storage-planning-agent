import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  buildEngineeringInputBundle,
  createDefaultEngineeringInputFormState,
  stableBundlePayloadJson
} from '../features/five-stage/model/engineeringInputForm'
import { useFiveStageExecutionStore } from '../stores/fiveStageExecution'
import { useWorkbenchContextStore } from '../stores/workbenchContext'

const BUNDLE_CONTEXT = {
  projectId: 'proj-1',
  projectVersionId: 'ver-1',
  versionNumber: 1,
  versionStatus: 'draft',
  isArchived: false,
  actorPrincipal: 'test',
  correlationId: 'corr-1'
}

function filledForm() {
  const form = createDefaultEngineeringInputFormState()
  form.zonePlanning.dailyInboundMassKg = 20000
  form.coolingZones[0].zoneArea = 100
  form.equipment.condensingTemperatureC = 40
  form.equipment.systems[0].systemCode = 'S1'
  form.equipment.systems[0].systemName = 'Sys'
  form.equipment.systems[0].designEvaporatingTemperature = -25
  form.equipment.systems[0].zones[0].zoneCode = 'Z1'
  form.equipment.systems[0].zones[0].zoneName = 'Z'
  form.equipment.systems[0].zones[0].evaporatorCount = 2
  form.equipment.systems[0].zones[0].defrostMethod = 'electric'
  form.equipment.systems[0].zones[0].designCoolingLoadKwR = 120
  form.installedPower.compressorInputPowerKwE = 120
  form.installedPower.evaporatorFanPowerKwE = 10
  form.installedPower.condenserFanPowerKwE = 8
  form.investment.totalAreaM2 = 1000
  form.investment.refrigeratedAreaM2 = 800
  form.investment.frozenAreaM2 = 200
  form.investment.positionCount = 100
  form.investment.totalPowerKw = 150
  return form
}

describe('fiveStageExecution store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useWorkbenchContextStore().resetForTests()
    useFiveStageExecutionStore().resetForTests()
    sessionStorage.clear()
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('11111111-1111-4111-8111-111111111111')
      .mockReturnValueOnce('22222222-2222-4222-8222-222222222222')
      .mockReturnValueOnce('33333333-3333-4333-8333-333333333333')
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
      BUNDLE_CONTEXT,
      { execute }
    )

    expect(outcome).toBeNull()
    expect(execute).toHaveBeenCalledOnce()
    expect(store.fieldError?.code).toBe('MISSING_ENGINEERING_PARAMETER')
    expect(store.fieldError?.formKey).toBe('coolingZones.0.zoneArea')
  })

  it('reuses idempotency key when bundle payload is unchanged', () => {
    const store = useFiveStageExecutionStore()
    const bundleJson = stableBundlePayloadJson(
      buildEngineeringInputBundle(filledForm(), BUNDLE_CONTEXT)
    )

    const key1 = store.resolveIdempotencyKey('proj-1', 1, bundleJson)
    const key2 = store.resolveIdempotencyKey('proj-1', 1, bundleJson)

    expect(key1).toBe('11111111-1111-4111-8111-111111111111')
    expect(key2).toBe('11111111-1111-4111-8111-111111111111')
  })

  it('rotates idempotency key when bundle payload changes', async () => {
    const workbench = useWorkbenchContextStore()
    workbench.projectId = 'proj-1'
    workbench.versionNumber = 1

    const execute = vi.fn().mockResolvedValue({ success: true, idempotent_replay: false })
    const store = useFiveStageExecutionStore()

    const formA = filledForm()
    await store.execute(formA, BUNDLE_CONTEXT, { execute })
    const firstKey = execute.mock.calls[0][2].idempotency_key

    const formB = filledForm()
    formB.zonePlanning.dailyInboundMassKg = 25000
    await store.execute(formB, BUNDLE_CONTEXT, { execute })
    const secondKey = execute.mock.calls[1][2].idempotency_key

    expect(firstKey).toBe('11111111-1111-4111-8111-111111111111')
    expect(secondKey).toBe('22222222-2222-4222-8222-222222222222')
    expect(secondKey).not.toBe(firstKey)
  })

  it('sends rotated key on second execute of edited form', async () => {
    const workbench = useWorkbenchContextStore()
    workbench.projectId = 'proj-1'
    workbench.versionNumber = 1

    const execute = vi.fn().mockResolvedValue({ success: true, idempotent_replay: false })
    const store = useFiveStageExecutionStore()
    const form = filledForm()

    await store.execute(form, BUNDLE_CONTEXT, { execute })
    form.installedPower.compressorInputPowerKwE = 130
    await store.execute(form, BUNDLE_CONTEXT, { execute })

    expect(execute.mock.calls[0][2].idempotency_key).toBe('11111111-1111-4111-8111-111111111111')
    expect(execute.mock.calls[1][2].idempotency_key).toBe('22222222-2222-4222-8222-222222222222')
  })
})
