import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_SRC = join(process.cwd(), 'src')
const MAPPER_PATH = join(FRONTEND_SRC, 'features/calculations/model/mapFactoryPowerPresentation.ts')
const COMPONENT_PATH = join(
  FRONTEND_SRC,
  'features/calculations/components/FactoryPowerEstimationResults.vue'
)
const PAGE_PATH = join(FRONTEND_SRC, 'features/calculations/components/CalculationsPage.vue')
const LEGACY_POWER_PATH = join(
  FRONTEND_SRC,
  'features/calculations/components/InstalledPowerResultsTable.vue'
)

describe('V2.0 P2 factory-power read-only presentation boundary', () => {
  it('keeps V2 identity and consumer source selection exact', () => {
    const mapper = readFileSync(MAPPER_PATH, 'utf8')
    expect(mapper).toContain("FACTORY_POWER_CALCULATOR_ID = 'factory_power_estimation'")
    expect(mapper).toContain("FACTORY_POWER_CALCULATOR_VERSION = '2.0.0-p2'")
    expect(mapper).toContain("FACTORY_POWER_RESULT_SCHEMA_VERSION = '2.0.0-p1'")
    expect(mapper).toContain('record.factory_power_presentation')
    expect(mapper).toContain('if (!isValidPresentation(attached)) return null')
    expect(mapper).toContain('/^sha256:[0-9a-f]{64}$/u')
    expect(mapper).not.toContain('readCanonicalResult')
    expect(mapper).not.toContain('isValidCanonicalResult')
    expect(mapper).not.toContain('readCanonicalHash')
    expect(mapper).not.toContain('result_snapshot')
    expect(mapper).not.toMatch(/\brecord\.result_hash\b/u)
    expect(mapper).not.toContain('installed_power@1.0.0')
    expect(mapper).not.toContain('power_configuration')
  })

  it('contains no engineering recalculation and keeps the card separate from legacy power', () => {
    const mapper = readFileSync(MAPPER_PATH, 'utf8')
    const component = readFileSync(COMPONENT_PATH, 'utf8')
    const page = readFileSync(PAGE_PATH, 'utf8')
    const legacy = readFileSync(LEGACY_POWER_PATH, 'utf8')

    for (const source of [mapper, component]) {
      expect(source).not.toMatch(/Math\.(ceil|floor|round)/u)
      expect(source).not.toMatch(/\b(?:sum|reduce)\s*\(/u)
      expect(source).not.toContain('simultaneity_factor *')
      expect(source).not.toContain('configured_quantity *')
    }
    expect(page).toContain('FactoryPowerEstimationResults')
    expect(page).toContain('mapFactoryPowerPresentation')
    expect(legacy).not.toContain('factory_power_estimation')
  })

  it('has an explicit no-result state with no legacy fallback wording', () => {
    const component = readFileSync(COMPONENT_PATH, 'utf8')
    expect(component).toContain('暂无可用的 V2.0 估算工厂电功率结果')
    expect(component).toContain('不会回退到旧装机功率或补充用电配置')
  })
})
