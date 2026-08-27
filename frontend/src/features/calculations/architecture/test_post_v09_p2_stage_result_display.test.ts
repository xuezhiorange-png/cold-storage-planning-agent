import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_SRC = join(process.cwd(), 'src')

const P2_FORMULA_SCAN_FILES = [
  'features/calculations/components/CalculationsPage.vue',
  'features/calculations/components/CalculationSummary.vue',
  'features/calculations/components/CoolingLoadResultsTable.vue',
  'features/calculations/components/EquipmentResultsTable.vue',
  'features/calculations/components/InstalledPowerResultsTable.vue',
  'features/calculations/components/InvestmentResultsTable.vue',
  'features/five-stage/components/FiveStageProgressPanel.vue',
  'api/contracts/calculations.ts',
  'features/calculations/model/mapPersistedCalculations.ts',
  'features/five-stage/model/mapFiveStageCalculations.ts'
]

const FORBIDDEN_FORMULA_PATTERNS = [
  /Math\.ceil/,
  /Math\.floor/,
  /\*\s*1\.56/,
  /\*\s*2\.5/,
  /\*\s*55/,
  /\/\s*400/,
  /\/\s*16/
]

describe('POST-V0.9 P2 stage result display guards', () => {
  it('P2 Vue/TS files do not embed engineering arithmetic', () => {
    for (const relativePath of P2_FORMULA_SCAN_FILES) {
      const content = readFileSync(join(FRONTEND_SRC, relativePath), 'utf8')
      for (const pattern of FORBIDDEN_FORMULA_PATTERNS) {
        expect(pattern.test(content), `${relativePath} matched ${pattern}`).toBe(false)
      }
    }
  })

  it('calculations page shows five stage result blocks and empty copy', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/calculations/components/CalculationsPage.vue'),
      'utf8'
    )
    expect(content).toContain('CoolingLoadResultsTable')
    expect(content).toContain('EquipmentResultsTable')
    expect(content).toContain('InstalledPowerResultsTable')
    expect(content).toContain('InvestmentResultsTable')
    expect(content).toContain('EMPTY_STAGE_COPY')
    expect(content).toContain('暂无完整五阶段计算结果。')
    expect(content).toContain('OperatorProcessInputV1')
    expect(content).not.toContain('power_configuration')
  })
})
