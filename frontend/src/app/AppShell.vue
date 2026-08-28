<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

import AgentPanel from '../features/agent/components/AgentPanel.vue'
import './operator-workbench.css'
</script>

<template>
  <div class="application-shell">
    <header class="application-shell__header">
      <div class="application-shell__brand">
        <strong>冷库规划工作台</strong>
      </div>
      <nav aria-label="应用导航">
        <RouterLink to="/workbench/engineering-inputs">规划工作台</RouterLink>
      </nav>
      <AgentPanel />
    </header>

    <main class="application-shell__content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.application-shell {
  min-height: 100vh;
}

.application-shell__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 56px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--owb-navy-mid);
  color: #fff;
  background: var(--owb-navy-deep);
}

.application-shell__brand {
  display: flex;
  align-items: center;
}

.application-shell__brand strong {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.application-shell__header nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.application-shell__header a {
  border-radius: 6px;
  padding: 8px 12px;
  color: #dbe8f6;
  font-size: 13px;
  text-decoration: none;
  transition: background 0.15s;
}

.application-shell__header a:hover {
  background: rgba(255, 255, 255, 0.08);
}

.application-shell__header a.router-link-active {
  color: #fff;
  background: var(--owb-navy-mid);
}

.application-shell__content {
  min-width: 0;
}
</style>
