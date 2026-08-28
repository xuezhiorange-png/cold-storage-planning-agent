import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_SRC = join(process.cwd(), 'src')

const P1_VUE_SCAN_FILES = [
  'features/workbench/WorkbenchLayout.vue',
  'app/AppShell.vue',
  'features/investment/components/InvestmentPage.vue'
]

const FORBIDDEN_FORMULA_PATTERNS = [
  /Math\.ceil/,
  /\*\s*1\.56/,
  /\*\s*2\.5/,
  /\*\s*55/,
  /\/\s*400/,
  /\/\s*16/,
  /\butilization_factor\s*[:=]/,
  /\breserve_factor\s*[:=]/
]

describe('POST-V0.9 P1 hide planning-run nav guards', () => {
  it('P1 allowlist Vue files do not embed engineering formulas', () => {
    for (const relativePath of P1_VUE_SCAN_FILES) {
      const content = readFileSync(join(FRONTEND_SRC, relativePath), 'utf8')
      for (const pattern of FORBIDDEN_FORMULA_PATTERNS) {
        expect(pattern.test(content), `${relativePath} matched ${pattern}`).toBe(false)
      }
    }
  })

  it('workbench nav starts with 工程输入 and hides 基本信息', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/workbench/WorkbenchLayout.vue'),
      'utf8'
    )
    expect(content).toContain("label: '工程输入'")
    expect(content).not.toContain("label: '基本信息'")
    expect(content).not.toContain('/workbench/project')
  })

  it('router and app shell default landing targets engineering inputs', () => {
    const router = readFileSync(join(FRONTEND_SRC, 'app/router.ts'), 'utf8')
    expect(router).toContain("redirect: '/workbench/engineering-inputs'")
    expect(router).not.toMatch(/redirect:\s*['"]\/workbench\/project['"]/)

    const shell = readFileSync(join(FRONTEND_SRC, 'app/AppShell.vue'), 'utf8')
    expect(shell).toContain('to="/workbench/engineering-inputs"')
    expect(shell).not.toContain('to="/workbench/project"')
  })

  it('investment empty state points operators to 工程输入', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/investment/components/InvestmentPage.vue'),
      'utf8'
    )
    expect(content).toContain('暂无投资估算数据')
    expect(content).toContain('工程输入')
    expect(content).not.toContain('基本信息')
    expect(content).not.toContain('OperatorProcessInputV1')
  })
})
