<template>
  <div class="min-h-full bg-slate-50">
    <header
      class="border-b border-slate-200/80 bg-white/90 backdrop-blur-sm shadow-sm"
    >
      <div
        class="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-3"
      >
        <router-link to="/" class="flex items-center gap-2">
          <span
            class="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-sky-500 text-lg font-semibold text-white shadow-sm"
            >門</span
          >
          <div class="leading-tight">
            <div class="text-sm font-semibold text-slate-800">
              MedIntro · 線上掛號
            </div>
            <div class="text-xs text-slate-500">POC · 時間預警示範</div>
          </div>
        </router-link>
        <el-tag type="success" effect="plain" round>明亮簡約</el-tag>
      </div>
    </header>

    <main class="mx-auto max-w-3xl px-4 py-8">
      <router-view />
    </main>

    <footer class="mx-auto max-w-3xl px-4 pb-8 text-center text-xs text-slate-400">
      開發環境請先啟動後端：<code class="rounded bg-slate-100 px-1">uvicorn app.main:app --reload --port 8000</code>
    </footer>
  </div>
</template>

<script setup></script>
