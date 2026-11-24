import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire, registerHooks } from 'node:module'
import test from 'node:test'

// Compile the app's setup script and capture the real route guard without a browser or server.
const requireFrontend = createRequire(new URL('../frontend/package.json', import.meta.url))
const { compileScript, parse } = requireFrontend('@vue/compiler-sfc')
const { createRenderer, nextTick } = requireFrontend('vue')
const routerStub = 'data:text/javascript,' + encodeURIComponent(`
  export const createWebHistory = () => ({})
  export const route = { path: '/tasks', fullPath: '/tasks', meta: { roles: ['ANALYST'] } }
  export const router = {
    beforeEach(guard) { this.guard = guard },
    replacements: [],
    replace(location) { this.replacements.push(location) }
  }
  export const createRouter = () => router
  export const useRoute = () => route
  export const useRouter = () => router
`)
const hooks = registerHooks({
  resolve(spec, context, next) {
    if (context.parentURL?.includes('/frontend/src/')) {
      if (spec === 'vue-router') return next(routerStub, context)
      if (spec.startsWith('./') && !/\.(js|vue)$/.test(spec)) return next(`${spec}.js`, context)
    }
    return next(spec, context)
  },
  load(url, context, next) {
    if (url.endsWith('/frontend/src/App.vue')) {
      const filename = new URL(url)
      const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename: filename.pathname })
      return { format: 'module', shortCircuit: true, source: compileScript(descriptor, { id: 'session-app' }).content }
    }
    return next(url, context)
  }
})
const { auth } = await import('../frontend/src/auth.js')
const api = await import('../frontend/src/api.js')
const { apiFetch } = api
const { router } = await import('../frontend/src/router.js')
const { default: App } = await import('../frontend/src/App.vue')
const { refreshUnread, resetUnread, notificationState } = await import('../frontend/src/notifications.js')
hooks.deregister()

const analyst = { id: 1, username: 'analyst', roles: ['ANALYST'] }
const viewer = { id: 2, username: 'viewer', roles: ['VIEWER'] }
const tasks = { fullPath: '/tasks', meta: { roles: ['ANALYST', 'ADMIN'] } }
const me = '/api/v1/auth/me'
const action = '/api/v1/example-action'
const json = (body, status = 200) => new Response(JSON.stringify(body), { status })
const failure = (status, code) => json({ error: { code } }, status)

function browser(t) {
  const prevDocument = globalThis.document
  const prevFetch = globalThis.fetch
  const prevWindow = globalThis.window
  globalThis.document = Object.assign(new EventTarget(), { cookie: '', visibilityState: 'visible' })
  globalThis.window = new EventTarget()
  auth.clear()
  auth.ready = false
  t.after(() => {
    globalThis.document.cookie = ''
    auth.clear()
    globalThis.document = prevDocument
    globalThis.fetch = prevFetch
    globalThis.window = prevWindow
  })
  return (token) => { document.cookie = token ? `ww_csrf=${token}` : '' }
}

function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

test('same-account login in another tab refreshes CSRF before a normal write', async (t) => {
  const cookie = browser(t)
  cookie('first')
  auth.set(analyst, 'first')
  cookie('second')
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push([url, options.headers['X-CSRF-Token']])
    return url === me ? json({ user: analyst }) : json({ saved: true })
  }

  assert.deepEqual(await apiFetch(action, { method: 'POST' }), { saved: true })
  assert.deepEqual(calls, [[me, undefined], [action, 'second']])
  assert.equal(auth.csrf, 'second')
})

test('a new account in another tab updates role decisions even when auth was ready', async (t) => {
  const cookie = browser(t)
  cookie('first')
  auth.set(analyst, 'first')
  cookie('second')
  globalThis.fetch = async (url) => {
    assert.equal(url, me)
    return json({ user: viewer })
  }

  assert.equal(await router.guard(tasks), '/')
  assert.deepEqual(auth.user, viewer)
  assert.equal(auth.csrf, 'second')
})

test('an unsent action from the old account is not submitted under the new account', async (t) => {
  const cookie = browser(t)
  cookie('first')
  auth.set(analyst, 'first')
  cookie('second')
  const calls = []
  globalThis.fetch = async (url) => {
    calls.push(url)
    return json({ user: viewer })
  }

  await assert.rejects(() => apiFetch(action, { method: 'POST' }), { code: 'SESSION_CHANGED' })
  assert.deepEqual(calls, [me])
  assert.deepEqual(auth.user, viewer)
})

test('concurrent refreshes are deduplicated and a late result cannot restore an old account', async (t) => {
  const cookie = browser(t)
  const slow = deferred()
  const calls = []
  cookie('first')
  globalThis.fetch = async (url) => {
    assert.equal(url, me)
    calls.push(document.cookie)
    return calls.length === 1 ? slow.promise : json({ user: viewer })
  }
  const refresh = api.refreshAuth
  const first = refresh()
  const duplicate = refresh()
  cookie('second')
  await refresh()
  slow.resolve(json({ user: analyst }))
  await Promise.all([first, duplicate])

  assert.deepEqual(calls, ['ww_csrf=first', 'ww_csrf=second'])
  assert.deepEqual(auth.user, viewer)
  assert.equal(auth.csrf, 'second')
})

test('a delayed 401 from before a normal re-login does not clear the new session', async (t) => {
  const cookie = browser(t)
  const slow = deferred()
  cookie('first')
  auth.set(analyst, 'first')
  globalThis.fetch = async () => slow.promise
  const oldRequest = apiFetch('/notifications')
  cookie('second')
  auth.set(viewer, 'second')
  slow.resolve(failure(401, 'UNAUTHENTICATED'))
  await assert.rejects(oldRequest, { code: 'UNAUTHENTICATED' })
  assert.deepEqual(auth.user, viewer)
  assert.equal(auth.csrf, 'second')
})

for (const [label, fail] of [
  ['503', () => failure(503, 'DEPENDENCY_UNAVAILABLE')],
  ['network failure', () => { throw new TypeError('Failed to fetch') }]
]) {
  test(`auth initialization stays retryable after ${label}`, async (t) => {
    const cookie = browser(t)
    cookie('first')
    let calls = 0
    globalThis.fetch = async () => ++calls === 1 ? fail() : json({ user: analyst })

    assert.equal(await router.guard(tasks), true)
    assert.equal(auth.ready, false)
    assert.ok(auth.refreshError)
    assert.equal(await router.guard(tasks), true)
    assert.equal(calls, 2)
    assert.equal(auth.ready, true)
    assert.deepEqual(auth.user, analyst)
    assert.equal(auth.refreshError, '')
  })
}

test('a normal logout in another tab clears local auth after me confirms it', async (t) => {
  const cookie = browser(t)
  cookie('first')
  auth.set(analyst, 'first')
  cookie('')
  globalThis.fetch = async (url) => {
    assert.equal(url, me)
    return failure(401, 'UNAUTHENTICATED')
  }

  assert.deepEqual(await router.guard(tasks), { path: '/login', query: { redirect: '/tasks' } })
  assert.equal(auth.user, null)
  assert.equal(auth.csrf, '')
  assert.equal(auth.ready, true)
})


test('tab focus refreshes identity and rechecks the role for the already-open view', async (t) => {
  const cookie = browser(t)
  cookie('first')
  auth.set(analyst, 'first')
  const calls = []
  globalThis.fetch = async (url) => {
    calls.push(url)
    return url === me ? json({ user: viewer }) : json({ count: 0 })
  }
  router.replacements.length = 0
  const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {} })
  const app = renderer.createApp({ ...App, render: () => null })
  const tick = async () => { await new Promise(setImmediate); await nextTick() }
  app.mount({})
  try {
    cookie('second')
    window.dispatchEvent(new Event('focus'))
    document.dispatchEvent(new Event('visibilitychange'))
    await tick()
    assert.deepEqual(auth.user, viewer)
    assert.equal(auth.csrf, 'second')
    assert.deepEqual(router.replacements, ['/'])
    assert.equal(calls.filter((url) => url === me).length, 1)
  } finally {
    app.unmount()
  }
  window.dispatchEvent(new Event('focus'))
  document.dispatchEvent(new Event('visibilitychange'))
  await tick()
  assert.equal(calls.filter((url) => url === me).length, 1)
})

test('a login response cannot associate its old account with a newer cookie', async (t) => {
  const cookie = browser(t)
  cookie('second')
  // The first login response is consumed after the other tab's cookie has already won.
  auth.set(analyst, 'first')
  const calls = []
  globalThis.fetch = async (url) => {
    calls.push(url)
    return json({ user: viewer })
  }

  await assert.rejects(() => apiFetch(action, { method: 'POST' }), { code: 'SESSION_CHANGED' })
  assert.deepEqual(calls, [me])
  assert.deepEqual(auth.user, viewer)
})

test('a stale refresh hands off to the current cookie without retrying a dependency failure', async (t) => {
  const cookie = browser(t)
  const slow = deferred()
  cookie('first')
  let calls = 0
  globalThis.fetch = async () => ++calls === 1 ? slow.promise : failure(503, 'DEPENDENCY_UNAVAILABLE')
  const first = api.refreshAuth()
  cookie('second')
  slow.resolve(json({ user: analyst }))

  await assert.rejects(first, { code: 'DEPENDENCY_UNAVAILABLE' })
  assert.equal(calls, 2)
  assert.equal(auth.ready, false)
  assert.equal(auth.user, null)
  assert.ok(auth.refreshError)
})

test('an old unread response cannot overwrite the new badge or a reset', async (t) => {
  const setCookie = browser(t); setCookie('a'); auth.set(analyst, 'a', 'a'); resetUnread()
  const results = []; globalThis.fetch = () => { const q = deferred(); results.push(q); return q.promise }
  const old = refreshUnread(); setCookie('b'); auth.set(viewer, 'b', 'b')
  const now = refreshUnread(); results[1].resolve(json({count: 4})); await now
  results[0].resolve(json({count: 27})); await old; assert.equal(notificationState.unread, 4)
  const pending = refreshUnread(); resetUnread(); results[2].resolve(json({count: 8})); await pending
  assert.equal(notificationState.unread, 0)
})
