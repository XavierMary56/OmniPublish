<script setup lang="ts">
import { ref } from 'vue'

const accounts = ref([
  { platform:'91视频web', url:'https://91*****.xxx/api', user:'adm***91', status:'已登录', statusCls:'badge-green', lastLogin:'2026-04-09 09:00', actionLabel:'重新登录', actionCls:'btn-ghost' },
  { platform:'海角社区', url:'https://hai*****.xxx/api', user:'edi***hj', status:'已登录', statusCls:'badge-green', lastLogin:'2026-04-09 08:45', actionLabel:'重新登录', actionCls:'btn-ghost' },
  { platform:'黑料情报局', url:'https://hei*****.xxx/api', user:'pub***hl', status:'已过期', statusCls:'badge-red', lastLogin:'2026-04-08 16:20', actionLabel:'重新登录', actionCls:'action-orange', warn:'⚠️ 发帖前需重新登录' },
  { platform:'91porn', url:'https://91p*****.xxx/api', user:'upl***91p', status:'已登录', statusCls:'badge-green', lastLogin:'2026-04-09 09:15', actionLabel:'重新登录', actionCls:'btn-ghost' },
  { platform:'糖心', url:'https://tan*****.xxx/api', user:'tx_***or', status:'已登录', statusCls:'badge-green', lastLogin:'2026-04-09 08:30', actionLabel:'重新登录', actionCls:'btn-ghost' },
])
</script>

<template>
<div>
  <div class="section-header">
    <div class="section-title">账号管理</div>
    <button class="btn btn-primary">＋ 添加账号</button>
  </div>
  <p style="font-size:12px;color:var(--t2);margin-bottom:16px">各平台后台登录凭据管理，发布时自动使用对应账号。</p>

  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>平台</th><th>入口 URL</th><th>用户名</th><th>登录状态</th><th>上次登录</th><th>操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="a in accounts" :key="a.platform">
          <td class="t1">{{ a.platform }}</td>
          <td style="color:var(--t3)">{{ a.url }}</td>
          <td>{{ a.user }}</td>
          <td>
            <span class="badge" :class="a.statusCls">{{ a.status }}</span>
            <span v-if="a.warn" style="font-size:10px;color:var(--red);margin-left:6px">{{ a.warn }}</span>
          </td>
          <td>{{ a.lastLogin }}</td>
          <td><button class="btn btn-sm" :class="a.actionCls">{{ a.actionLabel }}</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
</template>

<style scoped>
.action-orange{color:var(--orange)!important;border:1px solid var(--orange)!important;background:transparent!important}
</style>
