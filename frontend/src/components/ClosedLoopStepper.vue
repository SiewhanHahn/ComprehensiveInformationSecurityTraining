<template>
  <ol class="stepper" :class="{ 'stepper--compact': compact }" aria-label="预警闭环进度">
    <li
      v-for="(stage, index) in stages"
      :key="stage.key"
      class="stepper-item"
      :class="`is-${stage.state || 'pending'}`"
    >
      <span class="stepper-marker" aria-hidden="true">
        <svg v-if="stage.state === 'done'" viewBox="0 0 20 20" fill="none">
          <path d="m5 10.5 3.2 3.2L15 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span v-else>{{ index + 1 }}</span>
      </span>
      <span class="stepper-body">
        <span class="stepper-title">{{ stage.label }}</span>
        <span v-if="stage.time" class="stepper-meta">{{ stage.time }}</span>
        <span v-if="stage.role" class="stepper-meta">{{ stage.role }}</span>
        <span v-if="stage.note" class="stepper-note">{{ stage.note }}</span>
      </span>
    </li>
  </ol>
</template>

<script setup>
defineProps({
  stages: { type: Array, required: true },
  compact: { type: Boolean, default: false }
})
</script>

<style scoped>
.stepper {
  display: flex;
  gap: 8px;
  margin: 0;
  padding: 4px 0 2px;
  list-style: none;
  overflow-x: auto;
}

.stepper-item {
  position: relative;
  flex: 1 1 0;
  min-width: 108px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 6px;
}

.stepper-item:not(:last-child)::after {
  content: "";
  position: absolute;
  top: 14px;
  left: calc(50% + 14px);
  width: calc(100% - 28px);
  height: 2px;
  background: #e2e8f0;
  border-radius: 2px;
}

.stepper-item.is-done:not(:last-child)::after {
  background: #a7f3d0;
}

.stepper-marker {
  position: relative;
  z-index: 1;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  background: #f1f5f9;
  color: #94a3b8;
  border: 2px solid #e2e8f0;
  transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}

.stepper-marker svg {
  width: 16px;
  height: 16px;
}

.stepper-item.is-done .stepper-marker {
  background: #059669;
  border-color: #059669;
  color: #fff;
}

.stepper-item.is-current .stepper-marker {
  background: #eff6ff;
  border-color: #2563eb;
  color: #2563eb;
  box-shadow: 0 0 0 4px rgb(37 99 235 / 0.12);
}

.stepper-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 0;
  padding-top: 4px;
}

.stepper-title {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.stepper-item.is-done .stepper-title,
.stepper-item.is-current .stepper-title {
  color: #0f172a;
}

.stepper-meta {
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
}

.stepper-note {
  font-size: 11px;
  color: #64748b;
  white-space: normal;
}

.stepper--compact .stepper-item {
  min-width: 92px;
}

.stepper--compact .stepper-marker {
  width: 24px;
  height: 24px;
  font-size: 11px;
}

.stepper--compact .stepper-item:not(:last-child)::after {
  top: 12px;
  left: calc(50% + 12px);
  width: calc(100% - 24px);
}

.stepper--compact .stepper-title {
  font-size: 12px;
}

@media (max-width: 720px) {
  .stepper {
    flex-wrap: wrap;
  }

  .stepper-item {
    flex: 1 1 45%;
    min-width: 140px;
  }

  .stepper-item:not(:last-child)::after {
    display: none;
  }
}
</style>
