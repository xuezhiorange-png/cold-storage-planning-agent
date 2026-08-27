<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'

import WorkflowGuidancePanel from '../workflow/components/WorkflowGuidancePanel.vue'
import KnowledgeProvenancePanel from '../workflow/components/KnowledgeProvenancePanel.vue'
import { useWorkbenchContextStore } from '../../stores/workbenchContext'

interface NavItem {
  path: string
  label: string
}

const navItems: NavItem[] = [
  { path: '/workbench/project', label: '基本信息' },
  { path: '/workbench/engineering-inputs', label: '工程输入' },
  { path: '/workbench/calculations', label: '计算结果' },
  { path: '/workbench/schemes', label: '方案比选' },
  { path: '/workbench/investment', label: '投资估算' },
  { path: '/workbench/power', label: '用电配置' },
  { path: '/workbench/reports', label: '报告输出' }
]

const workbench = useWorkbenchContextStore()

onMounted(() => {
  if (!workbench.isReady) {
    workbench.initialize()
  }
})
</script>

<template>
  <div class="workbench-layout">
    <nav class="workbench-layout__nav" aria-label="主流程导航">
      <RouterLink
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="workbench-layout__nav-link"
        active-class="workbench-layout__nav-link--active"
        exact-active-class="workbench-layout__nav-link--active"
      >
        {{ item.label }}
      </RouterLink>
    </nav>
    <div class="workbench-layout__body">
      <aside class="workbench-layout__aside" aria-label="工作流与溯源">
        <WorkflowGuidancePanel />
        <KnowledgeProvenancePanel />
      </aside>
      <section class="workbench-layout__main">
        <RouterView />
      </section>
    </div>
  </div>
</template>

<style scoped>
.workbench-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: calc(100vh - 52px);
  box-sizing: border-box;
}

.workbench-layout__nav {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  align-items: center;
  padding: 10px 20px;
  background: #f3f7fb;
  border-bottom: 1px solid #c7d4e3;
}

.workbench-layout__nav-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 6px 14px;
  border: 1px solid #c7d4e3;
  border-radius: 6px;
  background: #fff;
  color: #163f68;
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.workbench-layout__nav-link:hover {
  background: #ebf0f6;
  border-color: #8aa8c4;
}

.workbench-layout__nav-link--active {
  background: #123a63;
  border-color: #123a63;
  color: #fff;
}

.workbench-layout__body {
  display: grid;
  grid-template-columns: minmax(260px, 22rem) minmax(0, 1fr);
  gap: 16px 20px;
  align-items: start;
  flex: 1 1 auto;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  padding: 16px 20px 24px;
  box-sizing: border-box;
}

.workbench-layout__aside {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.workbench-layout__main {
  min-width: 0;
  width: 100%;
}

@media (min-width: 961px) {
  .workbench-layout__aside {
    position: sticky;
    top: 12px;
  }
}

@media (max-width: 960px) {
  .workbench-layout__body {
    grid-template-columns: 1fr;
  }

  .workbench-layout__nav {
    padding: 10px 12px;
  }

  .workbench-layout__body {
    padding: 12px;
  }
}
</style>
