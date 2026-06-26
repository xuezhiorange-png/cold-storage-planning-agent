import {
  createRouter,
  createWebHistory,
  type Router,
  type RouterHistory
} from 'vue-router'

import WorkbenchLayout from '../features/workbench/WorkbenchLayout.vue'

export function createWorkbenchRouter(history: RouterHistory = createWebHistory()): Router {
  return createRouter({
    history,
    routes: [
      {
        path: '/',
        redirect: '/workbench/project'
      },
      {
        path: '/workbench',
        component: WorkbenchLayout,
        children: [
          {
            path: '',
            redirect: '/workbench/project'
          },
          {
            path: 'project',
            name: 'project',
            component: () => import('../features/project/components/ProjectPage.vue')
          },
          {
            path: 'calculations',
            name: 'calculations',
            component: () => import('../features/calculations/components/CalculationsPage.vue')
          },
          {
            path: 'schemes',
            name: 'schemes',
            component: () => import('../features/schemes/components/SchemesPage.vue')
          },
          {
            path: 'investment',
            name: 'investment',
            component: () => import('../features/investment/components/InvestmentPage.vue')
          },
          {
            path: 'power',
            name: 'power',
            component: () => import('../features/power/components/PowerPage.vue')
          },
          {
            path: 'reports',
            name: 'reports',
            component: () => import('../features/reports/components/ReportsPage.vue')
          }
        ]
      },
      {
        path: '/:pathMatch(.*)*',
        redirect: '/workbench/project'
      }
    ]
  })
}

export const router = createWorkbenchRouter()
