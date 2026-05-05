<template>
  <div class="space-y-6">
    <el-card shadow="never" class="rounded-2xl border border-slate-200/90">
      <template #header>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="text-lg font-semibold text-slate-800">候診大廳</div>
            <p class="mt-1 text-sm text-slate-500">
              約每 {{ pollSec }} 秒向伺服器更新；下方倒數為「依隊列推算的等候秒數」（每人 5 分鐘）。
            </p>
          </div>
          <router-link to="/">
            <el-button text type="primary">返回掛號</el-button>
          </router-link>
        </div>
      </template>

      <el-alert
        v-if="loadError"
        type="error"
        :closable="false"
        show-icon
        class="mb-4"
      >
        {{ loadError }}
      </el-alert>

      <div
        v-else
        class="grid gap-4 sm:grid-cols-3"
      >
        <div
          class="rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-5 shadow-sm"
        >
          <div class="text-xs font-medium uppercase tracking-wide text-slate-400">
            目前看診號碼
          </div>
          <div class="mt-2 text-4xl font-bold tabular-nums text-sky-600">
            {{ status?.current_serving_number ?? "—" }}
          </div>
        </div>
        <div
          class="rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-emerald-50/60 p-5 shadow-sm"
        >
          <div class="text-xs font-medium uppercase tracking-wide text-slate-400">
            您的號碼
          </div>
          <div class="mt-2 text-4xl font-bold tabular-nums text-emerald-600">
            {{ status?.your_queue_number ?? "—" }}
          </div>
          <div class="mt-2 text-xs text-slate-500">
            queue_id：<span class="font-mono">{{ queueId }}</span>
          </div>
        </div>
        <div
          class="rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-amber-50/50 p-5 shadow-sm"
        >
          <div class="text-xs font-medium uppercase tracking-wide text-slate-400">
            在您之前（估）
          </div>
          <div class="mt-2 text-4xl font-bold tabular-nums text-amber-700">
            {{ status?.people_before_you ?? "—" }}
          </div>
          <div class="mt-2 text-xs text-slate-500">
            預估等待 {{ status ? status.estimated_wait_minutes : "—" }} 分鐘
          </div>
        </div>
      </div>

      <div
        v-if="!loadError"
        class="mt-8 rounded-2xl border border-sky-100 bg-sky-50/80 p-6 text-center"
      >
        <div class="text-sm font-medium text-sky-900">預估等候倒數（隊列）</div>
        <div class="mt-3 text-5xl font-semibold tabular-nums tracking-tight text-sky-700">
          {{ countdownText }}
        </div>
        <p class="mx-auto mt-3 max-w-md text-xs leading-relaxed text-slate-600">
          交通時間（Google Maps）接上後，可改為「建議出發時間」與預警邏輯；此處僅示範排隊等待的動態倒數。
        </p>
      </div>

      <div class="mt-8 flex flex-wrap gap-3 border-t border-slate-100 pt-6">
        <el-button
          type="primary"
          plain
          :loading="advancing"
          @click="simulateAdvance"
        >
          模擬：下一位看診（測試用）
        </el-button>
        <el-button :loading="refreshing" @click="refreshNow">立即重新整理</el-button>
        <span v-if="lastUpdated" class="self-center text-xs text-slate-400">
          上次更新：{{ lastUpdated }}
        </span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { apiAdvanceNext, apiHall } from "../api/client";

const props = defineProps({
  queueId: { type: String, required: true },
});

const pollSec = 4;
const status = ref(null);
const loadError = ref("");
const refreshing = ref(false);
const advancing = ref(false);
const lastUpdated = ref("");

const waitSeconds = ref(0);
let pollTimer = null;
let tickTimer = null;

const countdownText = computed(() => {
  const s = Math.max(0, Math.floor(waitSeconds.value));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
});

function applyServerStatus(s) {
  status.value = s;
  const sec = Math.max(0, Math.round((s.estimated_wait_minutes ?? 0) * 60));
  waitSeconds.value = sec;
  lastUpdated.value = new Date().toLocaleTimeString("zh-TW", { hour12: false });
}

async function fetchHall() {
  loadError.value = "";
  refreshing.value = true;
  try {
    const data = await apiHall(props.queueId);
    applyServerStatus(data);
  } catch (e) {
    loadError.value = e.message || "無法載入候診資訊";
  } finally {
    refreshing.value = false;
  }
}

async function refreshNow() {
  await fetchHall();
}

async function simulateAdvance() {
  advancing.value = true;
  try {
    await apiAdvanceNext();
    ElMessage.success("已將叫號 +1（模擬）");
    await fetchHall();
  } catch (e) {
    ElMessage.error(e.message || "呼叫失敗");
  } finally {
    advancing.value = false;
  }
}

function startTick() {
  stopTick();
  tickTimer = setInterval(() => {
    if (waitSeconds.value <= 0) return;
    waitSeconds.value -= 1;
  }, 1000);
}

function stopTick() {
  if (tickTimer) clearInterval(tickTimer);
  tickTimer = null;
}

function startPoll() {
  stopPoll();
  pollTimer = setInterval(fetchHall, pollSec * 1000);
}

function stopPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

watch(
  () => props.queueId,
  async () => {
    await fetchHall();
  }
);

watch(status, () => {
  startTick();
});

onMounted(async () => {
  await fetchHall();
  startPoll();
  startTick();
});

onUnmounted(() => {
  stopPoll();
  stopTick();
});
</script>
