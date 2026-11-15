import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const FRONTEND = path.join(ROOT, 'frontend')

const requireFromFrontend = createRequire(path.join(FRONTEND, 'package.json'))
const sfc = requireFromFrontend('@vue/compiler-sfc')
const vueRuntime = requireFromFrontend('vue')
const { renderToString } = requireFromFrontend('vue/server-renderer')

function compileVueTemplate(relPath) {
  const fullPath = path.join(FRONTEND, relPath)
  const source = fs.readFileSync(fullPath, 'utf-8')
  const { descriptor } = sfc.parse(source, { filename: fullPath })
  const compiled = sfc.compileTemplate({
    source: descriptor.template.content,
    filename: fullPath,
    id: `test-${path.basename(relPath)}`,
    compilerOptions: {
      isCustomElement: (tag) => tag === 'router-link',
    },
  })
  assert.equal(compiled.errors.length, 0, `Template compile errors: ${compiled.errors.join('; ')}`)
  const code = compiled.code
    .replace(/import\s*\{([^}]+)\}\s*from\s*"vue"/g, (_, names) => `const { ${names.replace(/\s+as\s+/g, ': ')} } = vueRuntime`)
    .replace(/export function render\(/, 'return function render(')
  return new Function('vueRuntime', code)(vueRuntime)
}

test('WarningDetail.vue does not crash when taskError is set and currentTask is null', async () => {
  const render = compileVueTemplate('src/views/WarningDetail.vue')
  const stub = { template: '<div><slot /></div>' }
  const app = vueRuntime.createSSRApp({
    data() {
      return {
        loading: false,
        w: {
          public_id: 'abc123def456ghi789jkl01234',
          hazard_type: 'RAINSTORM',
          status: 'PUBLISHED',
          title: '测试预警',
          area_text: '长沙市',
          impact_text: '',
          reasoning_text: '达到阈值',
          city_code: 'CHANGSHA',
          valid_date: '2024-03-27',
          fused_mm: 29.625,
          risk_level: 'YELLOW',
          created_by: 'analyst_demo',
          dataset_version: '2026-09-30.2',
          models: [],
          baseline_mm: null,
          proxy_label_mm: null,
        },
        error: '',
        notice: '',
        busy: false,
        comment: '',
        feedbackStatus: 'RECEIVED',
        feedbackContent: '',
        isMine: false,
        canUseTasks: true,
        taskError: '响应任务接口超时',
        currentTask: null,
        canActOnTask: false,
        taskNote: '',
        taskBusy: null,
        feedbacks: [],
        stages: [],
        modelBarOption: {},
        auth: {
          user: { username: 'reviewer_demo', roles: ['REVIEWER'] },
          hasAnyRole: () => true,
          hasRole: () => false,
        },
        act: () => {},
        actOnTask: () => {},
        hazardLabel: (v) => v,
        cityName: (v) => v,
        formatDate: (v) => v,
        formatDateTime: (v) => v,
        shortId: (v) => v,
      }
    },
    render,
  })
  app.component('ClosedLoopStepper', stub)
  app.component('StatusBadge', stub)
  app.component('EmptyState', stub)
  app.component('ChartPanel', stub)

  const html = await renderToString(app)
  assert.match(html, /响应任务加载失败：响应任务接口超时/)
  assert.doesNotMatch(html, /尚未派发任务/)
})

function instantiateSetupScript(relPath, moduleMocks = {}) {
  const fullPath = path.join(FRONTEND, relPath)
  const source = fs.readFileSync(fullPath, 'utf-8')
  const { descriptor } = sfc.parse(source, { filename: fullPath })
  const compiled = sfc.compileScript(descriptor, {
    id: `test-${path.basename(relPath)}`,
    inlineTemplate: false,
  })
  const mountedHooks = []
  const unmountedHooks = []
  const stubComp = { template: '<div><slot /></div>' }
  const vueMock = {
    ...vueRuntime,
    onMounted: (fn) => mountedHooks.push(fn),
    onUnmounted: (fn) => unmountedHooks.push(fn),
  }

  let code = compiled.content
  let idx = 0
  const modArgs = []
  const resolveMock = (spec) => {
    if (spec === 'vue') return vueMock
    if (spec in moduleMocks) return moduleMocks[spec]
    if (spec.endsWith('.vue')) return stubComp
    return new Proxy({}, { get: (_, prop) => (typeof prop === 'string' ? () => {} : undefined) })
  }

  code = code.replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"][^\S\r\n]*;?/gm, (_, names, spec) => {
    const argName = `__mod_${idx++}`
    modArgs.push([argName, resolveMock(spec)])
    const mapped = names
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => s.replace(/\s+as\s+/g, ': '))
      .join(', ')
    return `const { ${mapped} } = ${argName};`
  })
  code = code.replace(/^import\s+\*\s+as\s+([A-Za-z0-9_$]+)\s+from\s+['"]([^'"]+)['"][^\S\r\n]*;?/gm, (_, name, spec) => {
    const argName = `__mod_${idx++}`
    modArgs.push([argName, resolveMock(spec)])
    return `const ${name} = ${argName};`
  })
  code = code.replace(/^import\s+([A-Za-z0-9_$]+)\s+from\s+['"]([^'"]+)['"][^\S\r\n]*;?/gm, (_, name, spec) => {
    const argName = `__mod_${idx++}`
    const mock = resolveMock(spec)
    modArgs.push([argName, mock?.default ?? mock])
    return `const ${name} = ${argName};`
  })
  code = code.replace(/export default\s+/, 'return ')

  const fn = new Function(...modArgs.map(([k]) => k), code)
  const componentDef = fn(...modArgs.map(([, v]) => v))
  const scope = vueRuntime.effectScope()
  const exposed = scope.run(() => componentDef.setup({}, { expose: () => {} }))
  return { exposed, scope, mountedHooks, unmountedHooks }
}

test('Notifications.vue allows REVIEWER to open withdrawn warnings and hides /tasks link from VIEWER', async () => {
  const viewerAuth = vueRuntime.reactive({
    user: { username: 'viewer_demo', roles: ['VIEWER'] },
    hasRole: (r) => viewerAuth.user.roles.includes(r),
    hasAnyRole: (...roles) => roles.some((r) => viewerAuth.user.roles.includes(r)),
  })
  const notifMocks = (authObj) => ({
    '../auth': { auth: authObj },
    '../api': { apiFetch: async () => [] },
    '../notifications': { notificationState: vueRuntime.reactive({ unread: 0 }), refreshUnread: async () => {} },
    '../ui/labels': { HAZARD_TYPE: { RAINSTORM: '暴雨' }, formatDateTime: (v) => String(v || '') },
  })

  // 1) VIEWER cannot open /tasks from response_task notifications
  const viewerRender = compileVueTemplate('src/views/Notifications.vue')
  const { exposed: viewerSetup, scope: viewerScope } = instantiateSetupScript(
    'src/views/Notifications.vue',
    notifMocks(viewerAuth),
  )
  try {
    viewerSetup.items.value = [
      {
        id: 1,
        kind: 'TASK_ASSIGNED',
        title: '响应任务已派发',
        body: '请处理',
        resource_type: 'response_task',
        resource_id: 'task-1',
        read_at: null,
        created_at: '2024-03-27T00:00:00Z',
      },
      {
        id: 2,
        kind: 'WARNING_PUBLISHED',
        title: '预警已发布',
        body: '暴雨预警',
        resource_type: 'warning',
        resource_id: 'warn-withdrawn',
        read_at: null,
        created_at: '2024-03-27T00:01:00Z',
      },
      {
        id: 3,
        kind: 'WARNING_WITHDRAWN',
        title: '预警已撤回',
        body: '已撤回',
        resource_type: 'warning',
        resource_id: 'warn-withdrawn',
        read_at: null,
        created_at: '2024-03-27T00:02:00Z',
      },
    ]
    assert.equal(viewerSetup.canOpenWarning(viewerSetup.items.value[1]), false)

    const stub = { template: '<div><slot /></div>' }
    const viewerApp = vueRuntime.createSSRApp({ setup: () => ({ ...viewerSetup }), render: viewerRender })
    viewerApp.component('EmptyState', stub)
    viewerApp.component('PaginationBar', stub)
    viewerApp.component('StatusBadge', stub)
    viewerApp.component('TableSkeleton', stub)
    const viewerHtml = await renderToString(viewerApp)
    assert.doesNotMatch(viewerHtml, /查看任务/)
  } finally {
    viewerScope.stop()
  }

  // 2) REVIEWER must still be able to open withdrawn warnings and response_task links
  const reviewerAuth = vueRuntime.reactive({
    user: { username: 'reviewer_demo', roles: ['REVIEWER'] },
    hasRole: (r) => reviewerAuth.user.roles.includes(r),
    hasAnyRole: (...roles) => roles.some((r) => reviewerAuth.user.roles.includes(r)),
  })
  const { exposed: reviewerSetup, scope: reviewerScope } = instantiateSetupScript(
    'src/views/Notifications.vue',
    notifMocks(reviewerAuth),
  )
  try {
    reviewerSetup.items.value = [
      { id: 1, kind: 'WARNING_PUBLISHED', resource_type: 'warning', resource_id: 'warn-withdrawn' },
      { id: 2, kind: 'WARNING_WITHDRAWN', resource_type: 'warning', resource_id: 'warn-withdrawn' },
    ]
    assert.equal(reviewerSetup.canOpenWarning(reviewerSetup.items.value[0]), true)
    assert.equal(reviewerSetup.canOpenWarning(reviewerSetup.items.value[1]), true)
  } finally {
    reviewerScope.stop()
  }
})

test('App.vue redirects to /login?redirect=... when session clears, and Login.vue honors safe redirect', async () => {
  const authObj = vueRuntime.reactive({
    user: { username: 'analyst_demo', roles: ['ANALYST'] },
    ready: true,
    csrf: 'c',
    clear() {
      this.user = null
      this.csrf = ''
      this.ready = true
    },
    set(user, csrf) {
      this.user = user
      this.csrf = csrf || ''
      this.ready = true
    },
    hasRole: (r) => Boolean(authObj.user?.roles?.includes(r)),
    hasAnyRole: (...roles) => roles.some((r) => authObj.hasRole(r)),
  })
  const replaced = []
  const pushed = []
  const routeMock = vueRuntime.reactive({ path: '/warnings', fullPath: '/warnings?status=DRAFT', meta: {}, query: {} })
  const routerMock = {
    replace: (loc) => replaced.push(loc),
    push: (loc) => pushed.push(loc),
  }

  const { scope: appScope } = instantiateSetupScript('src/App.vue', {
    'vue-router': { useRoute: () => routeMock, useRouter: () => routerMock },
    './auth': { auth: authObj },
    './api': { apiFetch: async () => ({}) },
    './notifications': {
      notificationState: vueRuntime.reactive({ unread: 0 }),
      refreshUnread: async () => {},
      resetUnread: () => {},
    },
    './ui/labels': { roleLabel: (r) => r },
  })
  try {
    authObj.clear()
    await vueRuntime.nextTick()
    assert.equal(replaced.length, 1)
    assert.deepEqual(replaced[0], { path: '/login', query: { redirect: '/warnings?status=DRAFT' } })
  } finally {
    appScope.stop()
  }

  // Login.vue redirect honoring + open-redirect protection
  routeMock.path = '/login'
  routeMock.fullPath = '/login?redirect=%2Ftasks'
  routeMock.query = { redirect: '/tasks' }
  const { exposed: loginOk, scope: loginOkScope } = instantiateSetupScript('src/views/Login.vue', {
    'vue-router': { useRoute: () => routeMock, useRouter: () => routerMock },
    '../auth': { auth: authObj },
    '../api': { apiFetch: async () => ({ user: { username: 'u', roles: ['ANALYST'] }, csrf_token: 'tok' }) },
  })
  try {
    await loginOk.submit()
    assert.equal(pushed.at(-1), '/tasks')
  } finally {
    loginOkScope.stop()
  }

  routeMock.query = { redirect: '//evil.example/phish' }
  const { exposed: loginEvil, scope: loginEvilScope } = instantiateSetupScript('src/views/Login.vue', {
    'vue-router': { useRoute: () => routeMock, useRouter: () => routerMock },
    '../auth': { auth: authObj },
    '../api': { apiFetch: async () => ({ user: { username: 'u', roles: ['ANALYST'] }, csrf_token: 'tok' }) },
  })
  try {
    await loginEvil.submit()
    assert.equal(pushed.at(-1), '/')
  } finally {
    loginEvilScope.stop()
  }
})

test('Replay.vue hides draft link without risk_level & uses result threshold; Warnings.vue invalidates/refreshes stale preview', async () => {
  const fullReplay = path.join(FRONTEND, 'src/views/Replay.vue')
  const replaySrc = fs.readFileSync(fullReplay, 'utf-8')
  const { descriptor } = sfc.parse(replaySrc, { filename: fullReplay })
  const compiled = sfc.compileTemplate({
    source: descriptor.template.content,
    filename: fullReplay,
    id: 'test-replay-components',
    compilerOptions: { isCustomElement: () => false },
  })
  assert.equal(compiled.errors.length, 0)
  const renderReplay = new Function(
    'vueRuntime',
    compiled.code
      .replace(/import\s*\{([^}]+)\}\s*from\s*"vue"/g, (_, names) => `const { ${names.replace(/\s+as\s+/g, ': ')} } = vueRuntime`)
      .replace(/export function render\(/, 'return function render('),
  )(vueRuntime)

  const makeReplayApp = (result, thresholdVal = 'STORM') => {
    const stub = { template: '<div><slot /></div>' }
    const app = vueRuntime.createSSRApp({
      data() {
        return {
          cities: [{ code: 'CHANGSHA', name: '长沙' }],
          city: 'CHANGSHA',
          date: '2024-03-27',
          threshold: thresholdVal,
          loading: false,
          error: '',
          result,
          replayStages: [],
          modelBarOption: {},
          modelRadarOption: {},
          auth: { hasAnyRole: () => true },
          load: () => {},
        }
      },
      render: renderReplay,
    })
    app.component('router-link', { props: ['to'], template: '<a :data-to="JSON.stringify(to)"><slot /></a>' })
    app.component('StatusBadge', stub)
    app.component('ClosedLoopStepper', stub)
    app.component('ChartPanel', stub)
    return app
  }

  const noRiskHtml = await renderToString(
    makeReplayApp({
      data_status: 'COMPLETE',
      risk_level: null,
      city: { code: 'CHANGSHA', name: '长沙' },
      valid_date: '2024-03-27',
      threshold: { code: 'HEAVY', label: '大雨' },
      models: [],
      fused_mm: 5,
    }),
  )
  assert.doesNotMatch(noRiskHtml, /基于此回放创建预警/)

  const riskHtml = await renderToString(
    makeReplayApp(
      {
        data_status: 'COMPLETE',
        risk_level: 'YELLOW',
        city: { code: 'CHANGSHA', name: '长沙' },
        valid_date: '2024-03-27',
        threshold: { code: 'HEAVY', label: '大雨' },
        models: [],
        fused_mm: 30,
      },
      'STORM',
    ),
  )
  assert.match(riskHtml, /threshold&quot;:&quot;HEAVY&quot;/)

  // Warnings.vue stale preview refresh when form city/date/threshold changes
  const apiCalls = []
  const routeMock = vueRuntime.reactive({
    query: { city: 'CHANGSHA', date: '2024-03-27', threshold: 'HEAVY' },
  })
  const { exposed, scope, mountedHooks } = instantiateSetupScript('src/views/Warnings.vue', {
    'vue-router': { useRoute: () => routeMock, useRouter: () => ({ push: () => {} }) },
    '../auth': {
      auth: { hasRole: () => false, hasAnyRole: () => true },
    },
    '../api': {
      apiFetch: async (url) => {
        apiCalls.push(url)
        if (url.startsWith('/replay?city_code=WUHAN')) {
          return { data_status: 'COMPLETE', city: { code: 'WUHAN', name: '武汉' }, valid_date: '2024-03-27', models: [] }
        }
        if (url.startsWith('/replay')) {
          return { data_status: 'PARTIAL', city: { code: 'CHANGSHA', name: '长沙' }, valid_date: '2024-03-27', models: [] }
        }
        return []
      },
    },
    '../ui/labels': { formatDate: (v) => v, modelLabel: (v) => v },
  })
  try {
    await Promise.all(mountedHooks.map((fn) => fn()))
    assert.equal(exposed.preview.value.data_status, 'PARTIAL')
    assert.equal(exposed.canCreate.value, false)

    exposed.form.city = 'WUHAN'
    await vueRuntime.nextTick()
    // Wait for async reload
    await new Promise((r) => setTimeout(r, 10))
    assert.ok(apiCalls.some((u) => u.includes('/replay?city_code=WUHAN')))
    assert.equal(exposed.preview.value.city.code, 'WUHAN')
    assert.equal(exposed.canCreate.value, true)
  } finally {
    scope.stop()
  }
})

test('ui/labels.js includes SYSTEM role and USER resource_type', async () => {
  const { ROLE_LABELS, RESOURCE_TYPE, roleLabel } = await import('../frontend/src/ui/labels.js')
  assert.equal(roleLabel('SYSTEM'), '系统定时任务')
  assert.equal(ROLE_LABELS.SYSTEM, '系统定时任务')
  assert.equal(RESOURCE_TYPE.USER?.label, '用户')
})

test('Tasks.vue renders both overdue and escalated badges simultaneously', async () => {
  const render = compileVueTemplate('src/views/Tasks.vue')
  const stub = { template: '<div><slot /></div>' }
  const app = vueRuntime.createSSRApp({
    data() {
      return {
        loading: false,
        error: '',
        activeTab: '',
        tabs: [{ value: '', label: '全部' }],
        emptyTitle: '暂无任务',
        emptyDescription: '',
        rows: [
          {
            id: 1,
            public_id: 'task-overdue-escalated',
            warning_public_id: null,
            warning_title: '暴雨预警',
            assignee: 'analyst_demo',
            due_at: '2024-03-27T00:00:00Z',
            status: 'PENDING',
            overdue: true,
            escalation_level: 1,
            updated_at: '2024-03-27T00:00:00Z',
          },
        ],
        busyId: null,
        notes: {},
        switchTab: () => {},
        load: () => {},
        shortId: (v) => v,
        formatDateTime: (v) => v,
        canAct: () => false,
        act: () => {},
      }
    },
    render,
  })
  app.component('StatusBadge', stub)
  app.component('EmptyState', stub)
  app.component('TableSkeleton', stub)

  const html = await renderToString(app)
  assert.match(html, /已逾期/)
  assert.match(html, /已升级/)
})

test('App.vue navGroups filters /review and /tasks dropdown entries by role', async () => {
  const authObj = vueRuntime.reactive({
    user: { username: 'viewer_demo', roles: ['VIEWER'] },
    ready: true,
    csrf: 'c',
    clear() {
      this.user = null
      this.csrf = ''
      this.ready = true
    },
    hasRole: (r) => Boolean(authObj.user?.roles?.includes(r)),
    hasAnyRole: (...roles) => roles.some((r) => authObj.hasRole(r)),
  })
  const routeMock = vueRuntime.reactive({ path: '/', fullPath: '/', meta: {}, query: {} })
  const { exposed, scope } = instantiateSetupScript('src/App.vue', {
    'vue-router': { useRoute: () => routeMock, useRouter: () => ({ replace: () => {}, push: () => {} }) },
    './auth': { auth: authObj },
    './api': { apiFetch: async () => ({}) },
    './notifications': {
      notificationState: vueRuntime.reactive({ unread: 0 }),
      refreshUnread: async () => {},
      resetUnread: () => {},
    },
    './ui/labels': { roleLabel: (r) => r },
  })
  try {
    const warnPaths = () =>
      exposed.navGroups.value.find((g) => g.label === '预警')?.children.map((c) => c.path) || []

    assert.deepEqual(warnPaths(), ['/warnings', '/hazards', '/notifications'])

    authObj.user = { username: 'analyst_demo', roles: ['ANALYST'] }
    await vueRuntime.nextTick()
    assert.deepEqual(warnPaths(), ['/warnings', '/tasks', '/hazards', '/notifications'])

    authObj.user = { username: 'reviewer_demo', roles: ['REVIEWER'] }
    await vueRuntime.nextTick()
    assert.deepEqual(warnPaths(), ['/warnings', '/review', '/tasks', '/hazards', '/notifications'])
  } finally {
    scope.stop()
  }
})

test('WarningDetail.vue enforces ANALYST/ADMIN for submit, hides self-review, and distinguishes withdrawn closed tasks', async () => {
  const authObj = vueRuntime.reactive({
    user: { username: 'reviewer_demo', roles: ['REVIEWER'] },
    hasRole: (r) => Boolean(authObj.user?.roles?.includes(r)),
    hasAnyRole: (...roles) => roles.some((r) => authObj.hasRole(r)),
  })
  const render = compileVueTemplate('src/views/WarningDetail.vue')
  const { exposed, scope } = instantiateSetupScript('src/views/WarningDetail.vue', {
    'vue-router': { useRoute: () => ({ params: { id: 'warn-1' } }), useRouter: () => ({ push: () => {} }) },
    '../auth': { auth: authObj },
    '../api': { apiFetch: async () => ({}) },
    '../ui/labels': {
      HAZARD_TYPE: { RAINSTORM: '暴雨' },
      RISK_LEVEL: { MODERATE: { label: '中等' } },
      warningStatusLabel: (s) => s,
      hazardLabel: (h) => h,
      cityName: (c) => c,
      formatDate: (d) => d || '',
      formatDateTime: (d) => d || '',
      shortId: (v) => v || '',
    },
  })
  const stub = { template: '<div><slot /></div>' }
  const renderHtml = async () => {
    const app = vueRuntime.createSSRApp({ setup: () => ({ ...exposed }), render })
    app.component('EmptyState', stub)
    app.component('ClosedLoopStepper', stub)
    app.component('StatusBadge', stub)
    app.component('ChartPanel', stub)
    app.component('RouterLink', { template: '<a><slot /></a>' })
    return renderToString(app)
  }
  try {
    exposed.loading.value = false
    exposed.error.value = ''
    exposed.taskError.value = ''
    exposed.w.value = {
      public_id: 'warn-1',
      title: '测试预警',
      status: 'DRAFT',
      created_by: 'reviewer_demo',
      hazard_type: 'RAINSTORM',
      city_code: 'WUHAN',
      valid_date: '2024-03-27',
      fused_mm: 55,
      risk_level: 'MODERATE',
      area_text: '市区',
      impact_text: '',
      reasoning_text: '达到阈值',
      models: [],
      feedbacks: [],
    }
    exposed.tasks.value = []

    // 1) REVIEWER cannot submit own DRAFT even if isMine
    const draftHtml = await renderHtml()
    assert.doesNotMatch(draftHtml, /<button[^>]*>\s*提交审核\s*<\/button>/)

    // 2) Creator (even ADMIN) must not see self-review approve/reject controls,
    //    while another reviewer sees them
    authObj.user = { username: 'admin_demo', roles: ['ADMIN'] }
    exposed.w.value = { ...exposed.w.value, status: 'PENDING_REVIEW', created_by: 'admin_demo' }
    await vueRuntime.nextTick()
    const selfReviewHtml = await renderHtml()
    assert.doesNotMatch(selfReviewHtml, /<button[^>]*>\s*批准\s*<\/button>/)
    assert.doesNotMatch(selfReviewHtml, /<button[^>]*>\s*驳回\s*<\/button>/)

    authObj.user = { username: 'reviewer_demo', roles: ['REVIEWER'] }
    await vueRuntime.nextTick()
    const peerReviewHtml = await renderHtml()
    assert.match(peerReviewHtml, /<button[^>]*>\s*批准\s*<\/button>/)
    assert.match(peerReviewHtml, /<button[^>]*>\s*驳回\s*<\/button>/)

    // 3) Stepper notes task closed upon withdrawal as 已随撤回关闭,
    //    while normally completed task (with acked_at) stays 已完成处置
    exposed.w.value = {
      ...exposed.w.value,
      status: 'WITHDRAWN',
      withdrawn_at: '2024-03-27T01:00:00Z',
    }
    exposed.tasks.value = [
      {
        id: 9,
        status: 'COMPLETED',
        acked_at: null,
        completed_at: '2024-03-27T01:00:00Z',
        due_at: '2024-03-27T06:00:00Z',
        assignee: 'analyst_demo',
        overdue: false,
        escalation_level: 0,
      },
    ]
    await vueRuntime.nextTick()
    const responseStage = exposed.stages.value.find((s) => s.key === 'response')
    assert.equal(responseStage?.note, '已随撤回关闭')

    exposed.tasks.value = [
      {
        id: 9,
        status: 'COMPLETED',
        acked_at: '2024-03-27T00:30:00Z',
        completed_at: '2024-03-27T00:45:00Z',
        due_at: '2024-03-27T06:00:00Z',
        assignee: 'analyst_demo',
        overdue: false,
        escalation_level: 0,
      },
    ]
    await vueRuntime.nextTick()
    const ackedStage = exposed.stages.value.find((s) => s.key === 'response')
    assert.equal(ackedStage?.note, '已完成处置')
  } finally {
    scope.stop()
  }
})

test('Review.vue hides self-review approve/reject controls and marks own pending warning', async () => {
  const authObj = vueRuntime.reactive({
    user: { username: 'reviewer_demo', roles: ['REVIEWER'] },
    hasRole: (r) => Boolean(authObj.user?.roles?.includes(r)),
    hasAnyRole: (...roles) => roles.some((r) => authObj.hasRole(r)),
  })
  const render = compileVueTemplate('src/views/Review.vue')
  const { exposed, scope } = instantiateSetupScript('src/views/Review.vue', {
    '../auth': { auth: authObj },
    '../api': { apiFetch: async () => [] },
    '../ui/labels': {
      cityName: (c) => c,
      formatDate: (d) => d || '',
      formatDateTime: (d) => d || '',
      shortId: (v) => v || '',
    },
  })
  const stub = { template: '<div><slot /></div>' }
  const renderHtml = async () => {
    const app = vueRuntime.createSSRApp({ setup: () => ({ ...exposed }), render })
    app.component('StatusBadge', stub)
    app.component('EmptyState', stub)
    app.component('TableSkeleton', stub)
    app.component('RouterLink', { template: '<a><slot /></a>' })
    return renderToString(app)
  }
  try {
    exposed.loading.value = false
    exposed.activeTab.value = 'PENDING_REVIEW'
    exposed.rows.value = [
      {
        public_id: 'warn-self',
        title: '本人待审预警',
        city_code: 'WUHAN',
        valid_date: '2024-03-27',
        fused_mm: 60,
        risk_level: 'HIGH',
        created_by: 'reviewer_demo',
        status: 'PENDING_REVIEW',
      },
    ]
    const selfOnlyHtml = await renderHtml()
    assert.match(selfOnlyHtml, /不可自审/)
    assert.doesNotMatch(selfOnlyHtml, /批准/)
    assert.doesNotMatch(selfOnlyHtml, /驳回/)

    exposed.rows.value.push({
      public_id: 'warn-other',
      title: '他人待审预警',
      city_code: 'WUHAN',
      valid_date: '2024-03-27',
      fused_mm: 60,
      risk_level: 'HIGH',
      created_by: 'analyst_demo',
      status: 'PENDING_REVIEW',
    })
    const mixedHtml = await renderHtml()
    assert.match(mixedHtml, /批准/)
    assert.match(mixedHtml, /驳回/)
  } finally {
    scope.stop()
  }
})

test('api.js ERROR_ZH maps LOGIN_RATE_LIMITED, METHOD_NOT_ALLOWED, and HTTP_ERROR', async () => {
  const { registerHooks } = await import('node:module')
  registerHooks({
    resolve(specifier, context, nextResolve) {
      if (specifier.startsWith('./') && !specifier.endsWith('.js') && context.parentURL?.includes('/frontend/src/')) {
        return nextResolve(`${specifier}.js`, context)
      }
      return nextResolve(specifier, context)
    },
  })
  const prevFetch = globalThis.fetch
  const prevDoc = globalThis.document
  globalThis.document = { cookie: '' }
  try {
    const { apiFetch } = await import('../frontend/src/api.js')
    const cases = [
      { status: 429, code: 'LOGIN_RATE_LIMITED', expected: '尝试过于频繁，请稍后再试' },
      { status: 405, code: 'METHOD_NOT_ALLOWED', expected: '请求方法不被允许' },
      { status: 502, code: 'HTTP_ERROR', expected: '请求失败' },
    ]
    for (const c of cases) {
      globalThis.fetch = async () =>
        new Response(JSON.stringify({ error: { code: c.code, message: '' } }), {
          status: c.status,
          headers: { 'content-type': 'application/json' },
        })
      await assert.rejects(
        () => apiFetch(`/test-${c.code.toLowerCase()}`, { method: 'POST' }),
        (err) => err?.message === c.expected && err?.code === c.code,
      )
    }
  } finally {
    globalThis.fetch = prevFetch
    globalThis.document = prevDoc
  }
})

test('Monitor.vue renders badge--danger for FAILED dataset quality_status', async () => {
  const render = compileVueTemplate('src/views/Monitor.vue')
  const { exposed, scope } = instantiateSetupScript('src/views/Monitor.vue', {
    '../api': { apiFetch: async () => ({}) },
    '../ui/useCountUp': { useCountUp: (v) => v },
    '../ui/labels': {
      datasetTypeLabel: (v) => v,
      formatDate: (v) => v || '',
      formatDateTime: (v) => v || '',
      modelLabel: (v) => v,
      sourceTypeLabel: (v) => v,
    },
    '../charts/options': { coverageBar: () => ({}) },
  })
  try {
    exposed.loading.value = false
    exposed.error.value = ''
    exposed.status.value = {
      generated_at: '2024-03-27T00:00:00Z',
      records: {
        forecast: 10,
        observation: 10,
        latest_observed_date: '2024-03-27',
        latest_forecast_valid_at: '2024-03-27T00:00:00Z',
      },
      sources: [],
      datasets: [
        {
          id: 1,
          dataset_type: 'FORECAST',
          source_type: 'DEMO_SAMPLE',
          version: 'v-bad',
          quality_status: 'FAILED',
          row_count: 0,
          ingested_at: '2024-03-27T00:00:00Z',
        },
      ],
      coverage: {
        models: [],
        expected_models: ['ECMWF'],
        cities: [],
        per_city: [],
        partial_days: 0,
        dataset_version: 'v-bad',
        completeness: 'PARTIAL',
      },
    }
    const stub = { template: '<div><slot /></div>' }
    const app = vueRuntime.createSSRApp({ setup: () => ({ ...exposed }), render })
    app.component('StatusBadge', stub)
    app.component('EmptyState', stub)
    app.component('ChartPanel', stub)
    app.component('TableSkeleton', stub)
    app.component('RouterLink', { template: '<a><slot /></a>' })
    const html = await renderToString(app)
    assert.match(html, /class="badge badge--sm badge--danger"[^>]*>\s*FAILED\s*</)
  } finally {
    scope.stop()
  }
})

test('Users.vue reuses shared roleLabel so VIEWER displays 查看用户', async () => {
  const labels = await import('../frontend/src/ui/labels.js')
  const render = compileVueTemplate('src/views/Users.vue')
  const { exposed, scope } = instantiateSetupScript('src/views/Users.vue', {
    '../auth': { auth: { user: { username: 'admin_demo', roles: ['ADMIN'] } } },
    '../api': { apiFetch: async () => ({ items: [], total: 0 }) },
    '../ui/labels': labels,
  })
  try {
    assert.equal(exposed.roleName('VIEWER'), '查看用户')
    exposed.loading.value = false
    exposed.users.value = [
      { id: 1, username: 'viewer_demo', display_name: '查看演示', roles: ['VIEWER'], is_active: true },
    ]
    exposed.total.value = 1
    const stub = { template: '<div><slot /></div>' }
    const app = vueRuntime.createSSRApp({ setup: () => ({ ...exposed }), render })
    app.component('EmptyState', stub)
    app.component('TableSkeleton', stub)
    app.component('PaginationBar', stub)
    const html = await renderToString(app)
    assert.match(html, /查看用户/)
    assert.doesNotMatch(html, /查看员/)
  } finally {
    scope.stop()
  }
})
