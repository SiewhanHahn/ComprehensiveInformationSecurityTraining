import { reactive } from 'vue'
import { apiFetch } from './api'

// 顶栏铃铛与通知中心共用一份未读数：标记已读后两边要同时更新。
// 与 auth.js 一样用 reactive 单例，不引入状态库。
export const notificationState = reactive({ unread: 0 })

export async function refreshUnread() {
  try {
    notificationState.unread = (await apiFetch('/notifications/unread-count')).count || 0
  } catch (e) {
    // 未登录或后端不可用时静默清零；铃铛不该变成错误提示
    notificationState.unread = 0
  }
}

export function resetUnread() {
  notificationState.unread = 0
}
