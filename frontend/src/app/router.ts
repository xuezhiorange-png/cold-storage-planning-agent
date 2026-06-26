import {
  createRouter,
  createWebHistory,
  type Router,
  type RouterHistory
} from 'vue-router'

import LegacyWorkbench from '../features/workbench/LegacyWorkbench.vue'

export function createWorkbenchRouter(history: RouterHistory = createWebHistory()): Router {
  return createRouter({
    history,
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
