import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_SRC = join(process.cwd(), 'src')

const P3_FORMULA_SCAN_FILES = [
  'features/calculations/components/CalculationsPage.vue',
  'features/calculations/components/ZoneResultsTable.vue',
  'features/calculations/model/mapPersistedCalculations.ts',
  'api/contracts/planning.ts'
]

const P3_FACTOR_ASSIGNMENT_SCAN_FILES = [
  'features/calculations/components/CalculationsPage.vue',
  'features/calculations/components/ZoneResultsTable.vue',
  'features/calculations/model/mapPersistedCalculations.ts'
]

const FORBIDDEN_FORMULA_PATTERNS = [
  /Math\.ceil/,
  /\*\s*1\.56/,
  /\*\s*2\.5/,
  /\*\s*55/,
  /\/\s*400/,
  /\/\s*16/
]

const FORBIDDEN_FACTOR_ASSIGNMENT_PATTERNS = [
  /\butilization_factor\s*[:=]/,
  /\breserve_factor\s*[:=]/
]

describe('V0.9 P3 zone result display guards', () => {
  it('P3 Vue/TS files do not embed zone area or dock arithmetic', () => {
    for (const relativePath of P3_FORMULA_SCAN_FILES) {
      const content = readFileSync(join(FRONTEND_SRC, relativePath), 'utf8')
      for (const pattern of FORBIDDEN_FORMULA_PATTERNS) {
        expect(pattern.test(content), `${relativePath} matched ${pattern}`).toBe(false)
      }
    }
    for (const relativePath of P3_FACTOR_ASSIGNMENT_SCAN_FILES) {
      const content = readFileSync(join(FRONTEND_SRC, relativePath), 'utf8')
      for (const pattern of FORBIDDEN_FACTOR_ASSIGNMENT_PATTERNS) {
        expect(pattern.test(content), `${relativePath} matched ${pattern}`).toBe(false)
      }
    }
  })

  it('zone results table labels reporting scalars as 6-position scheme', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/calculations/components/ZoneResultsTable.vue'),
      'utf8'
    )
    expect(content).toContain('6位汇报')
    expect(content).not.toMatch(/\bMath\.min\s*\(/)
  })

  it('calculations page uses operator process input empty-state copy', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/calculations/components/CalculationsPage.vue'),
      'utf8'
    )
    expect(content).toContain('暂无完整五阶段计算结果。')
    expect(content).toContain('OperatorProcessInputV1')
    expect(content).not.toContain('EngineeringInputBundleV1')
    expect(content).toContain('max-width: 1400px')
    expect(content).toContain('total_area_m2_8_position_scheme')
  })
})
