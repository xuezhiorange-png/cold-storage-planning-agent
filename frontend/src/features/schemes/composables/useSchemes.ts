import { computed, onUnmounted, ref, type Ref } from 'vue'
import { LatestRequestGate } from '../../../shared/composables/latestRequestGate'
import { createSchemesApi, type SchemesApi } from '../api/schemesApi'
import type { SchemeItemContract, SchemeComparisonResponse } from '../../../api/contracts/schemes'

export type SchemesState = 'idle' | 'loading' | 'success' | 'empty' | 'error' | 'unavailable'

export interface UseSchemesReturn {
  data: Ref<SchemeComparisonResponse | null>
  schemes: Ref<SchemeItemContract[]>
  state: Ref<SchemesState>
  error: Ref<string>
  load: () => Promise<void>
  abort: () => void
}

export function useSchemes(api: SchemesApi = createSchemesApi()): UseSchemesReturn {
  const gate = new LatestRequestGate()
  const data = ref<SchemeComparisonResponse | null>(null)
  const state = ref<SchemesState>('idle')
  const error = ref('')
  let isAlive = true
  let previousState: SchemesState = 'idle'

  onUnmounted(() => {
    isAlive = false
    gate.cancel()
  })

  const schemes = computed(() => data.value?.schemes ?? [])

  async function load() {
    previousState = state.value
    state.value = 'loading'
    error.value = ''
    const handle = gate.begin()
    try {
      const response = await api.getComparison(handle.signal)
      if (handle.isCurrent() && isAlive) {
        data.value = response
        state.value = response.schemes.length === 0 ? 'empty' : 'success'
        handle.finish()
      }
    } catch (err: unknown) {
      if (!isAlive || !handle.isCurrent()) {
        // Stale or unmounted — restore the state that the current request or
        // unmount set.
        return
      }
      if (err instanceof DOMException && err.name === 'AbortError') {
        // The request was externally aborted (e.g. via abort() or a new load).
        // Restore the state that was active before this load began.
        state.value = previousState
        return
      }
      state.value = 'error'
      error.value = err instanceof Error ? err.message : '加载方案数据失败'
    } finally {
      // If the handle is still current but we never entered either the success
      // or error paths, it means the request was orphaned without a terminal
      // state. This should not happen in practice, but guard against it.
      if (handle.isCurrent() && isAlive && state.value === 'loading') {
        state.value = 'error'
      }
    }
  }

  function abort() {
    gate.cancel()
    if (isAlive && state.value === 'loading') state.value = previousState
  }

  return { data, schemes, state, error, load, abort }
}
