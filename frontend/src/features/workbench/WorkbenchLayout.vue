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
      <div class="workbench-layout__strip">
        <RouterLink
          v-for="(item, index) in navItems"
          :key="item.path"
          :to="item.path"
          class="workbench-layout__nav-link"
          active-class="workbench-layout__nav-link--active"
          exact-active-class="workbench-layout__nav-link--active"
        >
          <span class="workbench-layout__label">{{ item.label }}</span>
          <span class="workbench-layout__step">{{ index + 1 }}</span>
        </RouterLink>
      </div>
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
  min-height: calc(100vh - 56px);
  box-sizing: border-box;
}

.workbench-layout__nav {
  padding: 12px 20px;
  background: var(--owb-surface);
  border-bottom: 1px solid var(--owb-border);
}

.workbench-layout__strip {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 0;
  border: 1px solid var(--owb-border);
  border-radius: var(--owb-card-radius);
  background: #fff;
  overflow: hidden;
}

.workbench-layout__nav-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 auto;
  min-height: 40px;
  padding: 8px 14px;
  border-right: 1px solid var(--owb-border);
  background: #fff;
  color: var(--owb-navy-text);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
  flex-direction: row-reverse;
}

.workbench-layout__nav-link:last-child {
  border-right: none;
}

.workbench-layout__nav-link:hover {
  background: #ebf0f6;
}

.workbench-layout__nav-link--active {
  background: var(--owb-navy-mid);
  color: #fff;
}

.workbench-layout__nav-link--active .workbench-layout__step {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.workbench-layout__step {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--owb-surface);
  color: var(--owb-navy-mid);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.workbench-layout__label {
  white-space: nowrap;
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

  .workbench-layout__strip {
    flex-direction: column;
  }

  .workbench-layout__nav-link {
    border-right: none;
    border-bottom: 1px solid var(--owb-border);
  }

  .workbench-layout__nav-link:last-child {
    border-bottom: none;
  }
}
</style>
