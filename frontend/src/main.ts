// File Path: frontend/src/main.ts
// Timestamp: 2026-05-25T12:00:00+08:00
// Version: v0.1

import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";

import App from "./App.vue";
import router from "./router";

createApp(App).use(router).use(ElementPlus).mount("#app");
