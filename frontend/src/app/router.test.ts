import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import { createWorkbenchRouter } from './router'

describe('workbench router', () => {
  it('redirects the application root to the workbench', async () => {
    const router = createWorkbenchRouter(createMemoryHistory())

    await router.push('/')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('workbench')
    expect(router.currentRoute.value.fullPath).toBe('/workbench')
  })

  it('redirects unknown paths without leaving a blank shell', async () => {
    const router = createWorkbenchRouter(createMemoryHistory())

    await router.push('/unknown/view')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('workbench')
    expect(router.currentRoute.value.fullPath).toBe('/workbench')
  })
})
