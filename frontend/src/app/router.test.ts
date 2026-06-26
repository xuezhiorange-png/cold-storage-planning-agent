import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import { createWorkbenchRouter } from './router'

describe('workbench router', () => {
  it('redirects the application root to the workbench project page', async () => {
    const router = createWorkbenchRouter(createMemoryHistory())

    await router.push('/')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('project')
    expect(router.currentRoute.value.fullPath).toBe('/workbench/project')
  }, 10000)

  it('redirects unknown paths to the workbench project page', async () => {
    const router = createWorkbenchRouter(createMemoryHistory())

    await router.push('/unknown/view')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('project')
    expect(router.currentRoute.value.fullPath).toBe('/workbench/project')
  })
})
