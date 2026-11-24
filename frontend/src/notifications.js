import { reactive } from 'vue'
import { apiFetch } from './api'
import { auth } from './auth'

// 顶栏铃铛与通知中心共用一份未读数：标记已读后两边要同时更新。
// 与 auth.js 一样用 reactive 单例，不引入状态库。
export const notificationState = reactive({ unread: 0 })

let generation = 0

export async function refreshUnread() {
  const seq = ++generation, revision = auth.revision
  const current = () => seq === generation && revision === auth.revision
  try {
    const { count } = await apiFetch('/notifications/unread-count')
    if (current()) notificationState.unread = count || 0
  } catch (e) {
    // 未登录或后端不可用时静默清零；铃铛不该变成错误提示
    if (current()) notificationState.unread = 0
  }
}

export function resetUnread() {
  generation++
  notificationState.unread = 0
}
