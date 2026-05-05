import { createRouter, createWebHistory } from "vue-router";
import RegisterPage from "../views/RegisterPage.vue";
import LobbyPage from "../views/LobbyPage.vue";

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "register", component: RegisterPage },
    {
      path: "/lobby/:queueId",
      name: "lobby",
      component: LobbyPage,
      props: true,
    },
  ],
});
