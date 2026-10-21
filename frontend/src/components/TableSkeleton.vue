<template>
  <div aria-hidden="true">
    <span class="sr-only">表格加载中</span>
    <table class="table">
      <tbody>
        <tr v-for="row in rows" :key="row" class="skeleton-row">
          <td v-for="col in cols" :key="col">
            <div class="skeleton skeleton-line"></div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Number, default: 5 },
  cols: { type: Number, default: 4 }
})
</script>
