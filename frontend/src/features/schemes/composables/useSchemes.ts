import { computed, onUnmounted, ref, type Ref } from 'vue'
import { ApiError } from '../../../api/errors'
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
      data.value = null
      if (err instanceof ApiError) {
        if (err.status === 404 || err.status === 501 || err.code === 'FEATURE_DISABLED') {
          state.value = 'unavailable'
          error.value = '方案比选服务当前不可用'
        } else {
          state.value = 'error'
          error.value = err instanceof Error ? err.message : '加载方案数据失败'
        }
      } else {
        state.value = 'error'
        error.value = err instanceof Error ? err.message : '加载方案数据失败'
      }
    } finally {
      // If the handle is still current but loading was never progressed,
      // the request was orphaned. If stale or unmounted, restore state.
      if (state.value === 'loading') {
        state.value = handle.isCurrent() && isAlive ? 'error' : previousState
      }
    }
  }

  function abort() {
    gate.cancel()
    if (isAlive && state.value === 'loading') state.value = previousState
  }

  return { data, schemes, state, error, load, abort }
}
