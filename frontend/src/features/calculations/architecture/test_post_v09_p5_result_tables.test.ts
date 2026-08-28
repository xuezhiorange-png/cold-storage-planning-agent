import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_SRC = join(process.cwd(), 'src')

const P5_RESULT_TABLE_FILES = [
  'features/calculations/components/CalculationsPage.vue',
  'features/calculations/components/ZoneResultsTable.vue',
  'features/calculations/components/CoolingLoadResultsTable.vue',
  'features/calculations/components/EquipmentResultsTable.vue',
  'features/calculations/components/InstalledPowerResultsTable.vue',
  'features/calculations/components/InvestmentResultsTable.vue',
  'features/calculations/components/PersistedScalarResultsTable.vue',
  'features/calculations/components/PersistedArrayResultsTable.vue',
  'features/calculations/components/CalculationBasisDetails.vue',
  'features/five-stage/components/FiveStageProgressPanel.vue'
]

const P5_FORMULA_SCAN_FILES = [
  ...P5_RESULT_TABLE_FILES,
  'features/calculations/components/persistedResultLabels.ts'
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

describe('POST-V0.9 P5 operator result tables guards', () => {
  it('P5 Vue files do not embed engineering arithmetic', () => {
    for (const relativePath of P5_FORMULA_SCAN_FILES) {
      const content = readFileSync(join(FRONTEND_SRC, relativePath), 'utf8')
      for (const pattern of FORBIDDEN_FORMULA_PATTERNS) {
        expect(pattern.test(content), `${relativePath} matched ${pattern}`).toBe(false)
      }
    }
  })

  it('scalar result tables use Chinese 项目/数值/单位 columns', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/calculations/components/PersistedScalarResultsTable.vue'),
      'utf8'
    )
    expect(content).toContain('项目')
    expect(content).toContain('数值')
    expect(content).toContain('单位')
  })

  it('array result tables do not use Object.keys for column headers', () => {
    for (const relativePath of [
      'features/calculations/components/CoolingLoadResultsTable.vue',
      'features/calculations/components/EquipmentResultsTable.vue',
      'features/calculations/components/InstalledPowerResultsTable.vue',
      'features/calculations/components/PersistedArrayResultsTable.vue'
    ]) {
      const content = readFileSync(join(FRONTEND_SRC, relativePath), 'utf8')
      expect(content).not.toMatch(/Object\.keys/)
      expect(content).not.toMatch(/v-for="key in \w+Keys"/)
    }
  })

  it('stage result tables collapse formulas and warnings under 计算依据', () => {
    for (const relativePath of [
      'features/calculations/components/CoolingLoadResultsTable.vue',
      'features/calculations/components/EquipmentResultsTable.vue',
      'features/calculations/components/InstalledPowerResultsTable.vue',
      'features/calculations/components/InvestmentResultsTable.vue'
    ]) {
      const content = readFileSync(join(FRONTEND_SRC, relativePath), 'utf8')
      expect(content).toContain('CalculationBasisDetails')
      expect(content).not.toMatch(/<h4>公式/)
    }
  })

  it('calculations page drops English stage titles from card headers', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/calculations/components/CalculationsPage.vue'),
      'utf8'
    )
    expect(content).toContain('装机功率结果')
    expect(content).not.toContain('(installed_power)')
    expect(content).not.toContain('(equipment_rows)')
  })

  it('five-stage progress panel hides hash and id from primary body', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/five-stage/components/FiveStageProgressPanel.vue'),
      'utf8'
    )
    expect(content).toContain('待复核')
    expect(content).not.toContain('calculation_id')
    expect(content).not.toContain('result_hash')
    expect(content).not.toContain('requires_review')
    expect(content).toContain('CalculationBasisDetails')
  })

  it('zone table keeps 6位汇报 substring and translates aisle/scheme labels', () => {
    const content = readFileSync(
      join(FRONTEND_SRC, 'features/calculations/components/ZoneResultsTable.vue'),
      'utf8'
    )
    expect(content).toContain('6位汇报')
    expect(content).toContain('formatAisleLayout')
    expect(content).toContain('formatSchemeId')
  })
})
