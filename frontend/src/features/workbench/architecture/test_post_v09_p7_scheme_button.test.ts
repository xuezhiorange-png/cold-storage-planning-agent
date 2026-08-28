import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_SRC = join(process.cwd(), 'src')

const P7_SCAN_FILES = [
  'features/five-stage/components/ProductionSchemeRunPanel.vue',
  'features/workflow/components/WorkflowGuidancePanel.vue'
]

const FORBIDDEN_FORMULA_PATTERNS = [
  /Math\.ceil/,
  /\*\s*1\.56/,
  /\*\s*2\.5/,
  /\*\s*55/,
  /\/\s*400/,
  /\/\s*16/
]

describe('POST-V0.9 P7 scheme button guards', () => {
  it('P7 Vue files do not embed engineering formulas', () => {
    for (const relativePath of P7_SCAN_FILES) {
      const content = readFileSync(join(FRONTEND_SRC, relativePath), 'utf8')
      for (const pattern of FORBIDDEN_FORMULA_PATTERNS) {
        expect(pattern.test(content), `${relativePath} matched ${pattern}`).toBe(false)
      }
    }
  })

  it('ProductionSchemeRunPanel gates on persisted chainComplete instead of workflow COMPLETED', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/five-stage/components/ProductionSchemeRunPanel.vue'),
      'utf8'
    )
    expect(content).toContain('usePersistedPlanningResultsStore')
    expect(content).toContain('fiveStageProgress.chainComplete')
    expect(content).not.toMatch(/calcStep\?\.status\s*===\s*'COMPLETED'/)
    expect(content).toContain('生产方案评分')
    expect(content).not.toContain('production-scheme-runs')
    expect(content).toContain('<details')
    expect(content).toContain('结果哈希')
  })

  it('WorkflowGuidancePanel softens SCHEME_MISSING-only guidance after five-stage persistence', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/workflow/components/WorkflowGuidancePanel.vue'),
      'utf8'
    )
    expect(content).toContain('schemeMissingOnly')
    expect(content).toContain('fiveStageProgress.chainComplete')
    expect(content).toContain('还没跑生产方案评分，请到计算结果页运行')
    expect(content).toContain('前往计算结果页运行生产方案评分')
    expect(content).toContain('CALCULATION_REQUIRES_REVIEW')
    expect(content).not.toContain('Complete deterministic calculation')
  })
})
