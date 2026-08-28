import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_SRC = join(process.cwd(), 'src')

const EXPECTED_NAV_LABELS = [
  '工程输入',
  '计算结果',
  '方案比选',
  '投资估算',
  '用电配置',
  '报告输出'
]

describe('POST-V0.9 P8 frontend visual polish', () => {
  it('workbench nav lists six operator process steps in order', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/workbench/WorkbenchLayout.vue'),
      'utf8'
    )

    for (const label of EXPECTED_NAV_LABELS) {
      expect(content).toContain(`label: '${label}'`)
    }

    const firstLabelIndex = content.indexOf("label: '工程输入'")
    const lastLabelIndex = content.indexOf("label: '报告输出'")
    expect(firstLabelIndex).toBeGreaterThan(-1)
    expect(lastLabelIndex).toBeGreaterThan(firstLabelIndex)
  })

  it('does not restore 基本信息 or planning-run nav', () => {
    const layout = readFileSync(
      join(FRONTEND_SRC, 'features/workbench/WorkbenchLayout.vue'),
      'utf8'
    )
    expect(layout).not.toContain("label: '基本信息'")
    expect(layout).not.toContain('/workbench/project')

    const shell = readFileSync(join(FRONTEND_SRC, 'app/AppShell.vue'), 'utf8')
    expect(shell).not.toContain('to="/workbench/project"')
  })

  it('AppShell shows product name 冷库规划工作台', () => {
    const shell = readFileSync(join(FRONTEND_SRC, 'app/AppShell.vue'), 'utf8')
    expect(shell).toContain('冷库规划工作台')
    expect(shell).toContain('operator-workbench.css')
  })

  it('engineering input page title is 工程输入 without OperatorProcessInputV1 in header', () => {
    const page = readFileSync(
      join(FRONTEND_SRC, 'features/five-stage/components/EngineeringInputsPage.vue'),
      'utf8'
    )
    expect(page).toContain('工程输入')
    expect(page).not.toContain('OperatorProcessInputV1')
    expect(page).toMatch(/>\s*提交\s*</)
  })

  it('CalculationSummary does not use emoji icons', () => {
    const summary = readFileSync(
      join(FRONTEND_SRC, 'features/calculations/components/CalculationSummary.vue'),
      'utf8'
    )
    expect(summary).not.toMatch(/[\u{1F300}-\u{1FAFF}]/u)
    expect(summary).not.toContain('calculation-summary__icon')
  })

  it('power page drops English schema ids from visible card titles', () => {
    const power = readFileSync(
      join(FRONTEND_SRC, 'features/power/components/PowerPage.vue'),
      'utf8'
    )
    expect(power).toContain('规范装机功率')
    expect(power).toContain('补充用电配置')
    expect(power).not.toContain('CANONICAL_CALCULATOR_NAMES')
    expect(power).toContain('power_configuration')
  })
})
