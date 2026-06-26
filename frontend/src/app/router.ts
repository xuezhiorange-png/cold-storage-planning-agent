import { createRouter, createWebHistory, type Router } from 'vue-router'

import LegacyWorkbench from '../features/workbench/LegacyWorkbench.vue'

export function createWorkbenchRouter(): Router {
  return createRouter({
    history: createWebHistory(),
    routes: [
      {
        path: '/',
        redirect: '/workbench'
      },
      {
        path: '/workbench',
        name: 'workbench',
        component: LegacyWorkbench
      },
      {
        path: '/:pathMatch(.*)*',
        redirect: '/workbench'
      }
    ]
  })
}

export const router = createWorkbenchRouter()
