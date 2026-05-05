<template>
  <div class="space-y-6">
    <el-card shadow="never" class="rounded-2xl border border-slate-200/90">
      <template #header>
        <div class="text-lg font-semibold text-slate-800">我要掛號</div>
        <p class="mt-1 text-sm text-slate-500">
          需先允許瀏覽器定位；後端目前以每人 5 分鐘估算等候時間（交通時間串接後可再細化）。
        </p>
      </template>

      <el-form label-position="top" class="max-w-xl">
        <el-form-item label="姓名">
          <el-input v-model="name" maxlength="120" placeholder="必填" />
        </el-form-item>

        <el-form-item label="Email">
          <el-input
            v-model="email"
            type="email"
            placeholder="與 LINE User ID 擇一或兩者皆填"
            clearable
          />
        </el-form-item>

        <el-form-item label="LINE User ID（官方帳一對一聊取得）">
          <el-input
            v-model="lineId"
            placeholder="請加官方帳並傳訊取得 U 開頭 ID；若只用 Email 可留空"
            clearable
          />
          <p class="mt-1 text-xs text-slate-500">
            與「好友設定的顯示名稱／LINE ID (@xxx)」不同；後端發預警前須先有正確 User ID。
          </p>
        </el-form-item>

        <el-form-item label="交通方式">
          <el-select v-model="travelMode" class="w-full" placeholder="請選擇">
            <el-option
              v-for="o in travelOptions"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="定位狀態">
          <div class="flex flex-wrap items-center gap-3">
            <el-button type="primary" plain @click="requestLocation" :loading="geoLoading">
              取得目前位置
            </el-button>
            <el-tag v-if="geoOk" type="success" effect="dark" round>
              已取得 · {{ coordsText }}
            </el-tag>
            <el-tag v-else type="warning" effect="plain" round>尚未取得</el-tag>
          </div>
          <p v-if="geoError" class="mt-2 text-sm text-amber-700">{{ geoError }}</p>
        </el-form-item>

        <div class="flex flex-wrap gap-3 pt-2">
          <el-button
            type="primary"
            size="large"
            :loading="submitting"
            :disabled="!canSubmit"
            @click="submit"
          >
            送出掛號
          </el-button>
          <span v-if="!canSubmit && !submitting" class="self-center text-xs text-slate-400">
            請完成定位後才可送出
          </span>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { apiRegister } from "../api/client";

const router = useRouter();

const name = ref("");
const email = ref("");
const lineId = ref("");
const travelMode = ref("driving");

const travelOptions = [
  { label: "汽車 / 機車（driving）", value: "driving" },
  { label: "大眾運輸（transit）", value: "transit" },
  { label: "腳踏車（bicycling）", value: "bicycling" },
  { label: "步行（walking）", value: "walking" },
];

const lat = ref(null);
const lng = ref(null);
const geoLoading = ref(false);
const geoOk = computed(() => lat.value !== null && lng.value !== null);
const geoError = ref("");

const coordsText = computed(() => {
  if (!geoOk.value) return "";
  return `${lat.value.toFixed(5)}, ${lng.value.toFixed(5)}`;
});

const canSubmit = computed(() => {
  return name.value.trim().length > 0 && geoOk.value;
});

const submitting = ref(false);

function requestLocation() {
  geoError.value = "";
  if (!navigator.geolocation) {
    geoError.value = "此瀏覽器不支援定位。";
    return;
  }
  geoLoading.value = true;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      lat.value = pos.coords.latitude;
      lng.value = pos.coords.longitude;
      geoLoading.value = false;
      ElMessage.success("已取得定位");
    },
    (err) => {
      geoLoading.value = false;
      const map = {
        1: "使用者拒絕定位權限。",
        2: "無法取得位置（裝置原因）。",
        3: "定位逾時。",
      };
      geoError.value = map[err.code] ?? "定位失敗，請稍後再試。";
      ElMessage.error(geoError.value);
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
  );
}

async function submit() {
  if (!canSubmit.value) return;

  const e = email.value.trim();
  const l = lineId.value.trim();
  if (!e && !l) {
    ElMessage.warning("請至少填寫 Email 或 LINE User ID（U…）其中一項。");
    return;
  }

  submitting.value = true;
  try {
    const payload = {
      name: name.value.trim(),
      email: e.length ? e : null,
      line_id: l.length ? l : null,
      latitude: lat.value,
      longitude: lng.value,
      travel_mode: travelMode.value,
    };
    const res = await apiRegister(payload);
    ElMessage.success(`掛號成功，號碼 ${res.queue.queue_number}`);
    router.push({ name: "lobby", params: { queueId: String(res.queue.id) } });
  } catch (err) {
    ElMessage.error(err.message || "掛號失敗");
  } finally {
    submitting.value = false;
  }
}
</script>
