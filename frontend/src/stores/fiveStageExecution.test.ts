import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  buildOperatorProcessInput,
  buildWorkbenchSubmitContext,
  createDefaultEngineeringInputFormState,
  stableOperatorProcessFieldsJson,
  stableOperatorProcessPayloadJson
} from '../features/five-stage/model/engineeringInputForm'
import { useFiveStageExecutionStore } from '../stores/fiveStageExecution'
import { useWorkbenchContextStore } from '../stores/workbenchContext'

const SUBMIT_CONTEXT = buildWorkbenchSubmitContext({
  projectId: 'proj-1',
  projectVersionId: 'ver-1',
  versionNumber: 1,
  versionStatus: 'draft',
  isArchived: false,
  actorPrincipal: 'test'
})

function filledOperatorForm() {
  const form = createDefaultEngineeringInputFormState()
  form.zonePlanning.dailyInboundMassKg = 20000
  form.zonePlanning.workingTimeHPerDay = 16
  form.zonePlanning.finishedStorageDays = 7
  form.zonePlanning.packagingStorageDays = 1
  form.zonePlanning.precoolingRequiredRatio = 0.6
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
      .mockReturnValueOnce('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
  })

  it('posts operator_process_input and surfaces field_path errors', async () => {
    const workbench = useWorkbenchContextStore()
    workbench.projectId = 'proj-1'
    workbench.versionNumber = 1

    const execute = vi.fn().mockResolvedValue({
      error: {
        code: 'MISSING_ENGINEERING_PARAMETER',
        message: 'daily inbound mass required',
        field_path: 'zone_planning_inputs.daily_inbound_mass_kg'
      }
    })

    const store = useFiveStageExecutionStore()
    const outcome = await store.execute(
      createDefaultEngineeringInputFormState(),
      SUBMIT_CONTEXT,
      { execute }
    )

    expect(outcome).toBeNull()
    expect(execute).toHaveBeenCalledOnce()
    expect(execute.mock.calls[0][2]).toMatchObject({
      operator_process_input: {
        schema_id: 'OperatorProcessInputV1',
        schema_version: '1.0.0'
      },
      idempotency_key: '11111111-1111-4111-8111-111111111111'
    })
    expect(execute.mock.calls[0][2].engineering_input_bundle).toBeUndefined()
    expect(store.fieldError?.code).toBe('MISSING_ENGINEERING_PARAMETER')
    expect(store.fieldError?.formKey).toBe('zonePlanning.dailyInboundMassKg')
  })

  it('reuses idempotency key when operator five-KEY payload is unchanged', () => {
    const store = useFiveStageExecutionStore()
    const form = filledOperatorForm()
    const operatorInput = buildOperatorProcessInput(form)
    const fieldsJson = stableOperatorProcessFieldsJson(form)
    const payloadJson = stableOperatorProcessPayloadJson(operatorInput)

    const key1 = store.resolveIdempotencyKey('proj-1', 1, fieldsJson, payloadJson)
    const key2 = store.resolveIdempotencyKey('proj-1', 1, fieldsJson, payloadJson)

    expect(key1).toBe('11111111-1111-4111-8111-111111111111')
    expect(key2).toBe('11111111-1111-4111-8111-111111111111')
  })

  it('reuses idempotency_key on retry with unchanged operator form', async () => {
    const workbench = useWorkbenchContextStore()
    workbench.projectId = 'proj-1'
    workbench.versionNumber = 1

    const execute = vi.fn().mockResolvedValue({ success: true, idempotent_replay: false })
    const store = useFiveStageExecutionStore()
    const form = filledOperatorForm()

    await store.execute(form, SUBMIT_CONTEXT, { execute })
    await store.execute(form, SUBMIT_CONTEXT, { execute })

    const firstRequest = execute.mock.calls[0][2]
    const secondRequest = execute.mock.calls[1][2]

    expect(firstRequest.operator_process_input.schema_id).toBe('OperatorProcessInputV1')
    expect(secondRequest.operator_process_input).toEqual(firstRequest.operator_process_input)
    expect(firstRequest.idempotency_key).toBe('11111111-1111-4111-8111-111111111111')
    expect(secondRequest.idempotency_key).toBe(firstRequest.idempotency_key)
  })

  it('rotates idempotency key when operator five-KEY payload changes', async () => {
    const workbench = useWorkbenchContextStore()
    workbench.projectId = 'proj-1'
    workbench.versionNumber = 1

    const execute = vi.fn().mockResolvedValue({ success: true, idempotent_replay: false })
    const store = useFiveStageExecutionStore()

    const formA = filledOperatorForm()
    await store.execute(formA, SUBMIT_CONTEXT, { execute })
    const firstKey = execute.mock.calls[0][2].idempotency_key

    const formB = filledOperatorForm()
    formB.zonePlanning.dailyInboundMassKg = 25000
    await store.execute(formB, SUBMIT_CONTEXT, { execute })
    const secondKey = execute.mock.calls[1][2].idempotency_key

    expect(firstKey).toBe('11111111-1111-4111-8111-111111111111')
    expect(secondKey).toBe('22222222-2222-4222-8222-222222222222')
    expect(secondKey).not.toBe(firstKey)
  })

  it('sends rotated key on second execute of edited operator form', async () => {
    const workbench = useWorkbenchContextStore()
    workbench.projectId = 'proj-1'
    workbench.versionNumber = 1

    const execute = vi.fn().mockResolvedValue({ success: true, idempotent_replay: false })
    const store = useFiveStageExecutionStore()
    const form = filledOperatorForm()

    await store.execute(form, SUBMIT_CONTEXT, { execute })
    form.zonePlanning.workingTimeHPerDay = 18
    await store.execute(form, SUBMIT_CONTEXT, { execute })

    expect(execute.mock.calls[0][2].idempotency_key).toBe('11111111-1111-4111-8111-111111111111')
    expect(execute.mock.calls[1][2].idempotency_key).toBe('22222222-2222-4222-8222-222222222222')
  })
})
