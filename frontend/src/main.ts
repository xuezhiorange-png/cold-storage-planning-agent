import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import AppShell from './app/AppShell.vue'
import { router } from './app/router'
import './style.css'

const app = createApp(AppShell)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')
