import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import zhTw from "element-plus/es/locale/lang/zh-tw";
import "./style.css";
import App from "./App.vue";
import router from "./router";

createApp(App).use(ElementPlus, { locale: zhTw }).use(router).mount("#app");
