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
