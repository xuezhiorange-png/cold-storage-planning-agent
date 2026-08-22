import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import CalculationsPage from './CalculationsPage.vue'
import InvestmentPage from '../../investment/components/InvestmentPage.vue'
import PowerPage from '../../power/components/PowerPage.vue'
import { usePlanningWorkflowStore } from '../../../stores/planningWorkflow'
import { usePersistedPlanningResultsStore } from '../../../stores/persistedPlanningResults'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import {
  installWorkbenchFetchMock,
  samplePlanningRunResponse
} from '../../../../tests/helpers/workbenchFetchMock'

describe('persisted planning result pages', () => {
  const pinia = createPinia()

  beforeEach(() => {
    setActivePinia(pinia)
    vi.restoreAllMocks()
    const workbench = useWorkbenchContextStore(pinia)
    workbench.resetForTests()
    workbench.projectId = 'proj-test'
    workbench.versionNumber = 1
    usePlanningWorkflowStore(pinia).reset()
    usePersistedPlanningResultsStore(pinia).resetForTests()
  })

  it('renders calculations, investment, and power from persisted API without pinia latestResponse', async () => {
    const persisted = samplePlanningRunResponse()
    installWorkbenchFetchMock(vi.spyOn(globalThis, 'fetch'), {
      persistedPlanningResponse: persisted
    })

    const planning = usePlanningWorkflowStore(pinia)
    expect(planning.latestResponse).toBeNull()

    await usePersistedPlanningResultsStore(pinia).load()
    await flushPromises()

    const calculations = mount(CalculationsPage, { global: { plugins: [pinia] } })
    await flushPromises()
    expect(calculations.text()).toContain('200')
    expect(calculations.text()).toContain('原料暂存')
    expect(calculations.find('.calculations-page__empty').exists()).toBe(false)

    const investment = mount(InvestmentPage, { global: { plugins: [pinia] } })
    await flushPromises()
    expect(investment.text()).toContain('土建')
    expect(investment.find('.investment-page__empty').exists()).toBe(false)

    const power = mount(PowerPage, { global: { plugins: [pinia] } })
    await flushPromises()
    expect(power.text()).toContain('1350')
    expect(power.find('.power-page__empty').exists()).toBe(false)
  })
})
