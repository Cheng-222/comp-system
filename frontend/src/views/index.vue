<template>
  <div class="home-page">
    <competition-dashboard />
  </div>
</template>

<script setup>
import CompetitionDashboard from '@/views/competition/dashboard/index.vue'
</script>

<style scoped>
.home-page {
  min-height: calc(100vh - 84px);
}
</style>
