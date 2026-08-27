import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_SRC = join(process.cwd(), 'src')
const FIVE_STAGE_DIR = join(FRONTEND_SRC, 'features/five-stage')
const FIVE_STAGE_STORE = join(FRONTEND_SRC, 'stores/fiveStageExecution.ts')
const FORM_COMPONENT = join(FIVE_STAGE_DIR, 'components/EngineeringInputBundleForm.vue')
const FORM_MODEL = join(FIVE_STAGE_DIR, 'model/engineeringInputForm.ts')

const OPERATOR_KEY_FIELD_KEYS = [
  'zonePlanning.dailyInboundMassKg',
  'zonePlanning.finishedStorageDays',
  'zonePlanning.frozenStorageDays',
  'zonePlanning.mainPackagingStorageDays',
  'zonePlanning.auxiliaryPackagingStorageDays'
]

const FORBIDDEN_OPERATOR_FORM_FRAGMENTS = [
  'workingTimeHPerDay',
  'precoolingRequiredRatio',
  'packagingStorageDays',
  'working_time_h_per_day',
  'precooling_required_ratio'
]

const FORBIDDEN_KEYPAD_PATTERNS = [
  /cooling_load_inputs/,
  /equipment_inputs/,
  /installed_power_inputs/,
  /investment_inputs/,
  /coefficient_context/,
  /u_value_wall/,
  /design_cooling_load_kw_r/,
  /compressor_input_power_kw_e/,
  /total_area_m2/,
  /添加冷负荷分区/,
  /添加设备系统/,
  /persisted_upstream_confirmed/
]

const FORBIDDEN_FORMULA_PATTERNS = [
  /\butilization_factor\s*[:=]\s*0\.\d+/,
  /\breserve_factor\s*[:=]\s*0\.\d+/,
  /\b\d+\.?\d*\s*\*\s*\d+\.?\d*\s*\/\s*\d+/
]

function collectTsVueFiles(dir: string): string[] {
  const entries = readdirSync(dir)
  const files: string[] = []
  for (const entry of entries) {
    const fullPath = join(dir, entry)
    const stat = statSync(fullPath)
    if (stat.isDirectory()) {
      files.push(...collectTsVueFiles(fullPath))
      continue
    }
    if (entry.endsWith('.ts') || entry.endsWith('.vue')) {
      files.push(fullPath)
    }
  }
  return files
}

describe('V0.8 P2 operator five-KEY workbench guards', () => {
  it('engineering input form exposes only five operator KEY field-key controls', () => {
    const content = readFileSync(FORM_COMPONENT, 'utf8')
    const fieldKeyMatches = [...content.matchAll(/field-key="([^"]+)"/g)].map((match) => match[1])

    expect(fieldKeyMatches).toEqual(OPERATOR_KEY_FIELD_KEYS)
    for (const fragment of FORBIDDEN_OPERATOR_FORM_FRAGMENTS) {
      expect(content.includes(fragment), `form contained removed KEY ${fragment}`).toBe(false)
    }
    for (const pattern of FORBIDDEN_KEYPAD_PATTERNS) {
      expect(pattern.test(content), `form matched forbidden keypad ${pattern}`).toBe(false)
    }
  })

  it('engineering inputs page titles OperatorProcessInputV1', () => {
    const page = readFileSync(join(FIVE_STAGE_DIR, 'components/EngineeringInputsPage.vue'), 'utf8')
    expect(page).toContain('OperatorProcessInputV1')
    expect(page).toContain('操作员过程输入')
    expect(page).not.toContain('EngineeringInputBundleV1')
  })

  it('five-stage submit path posts operator_process_input not engineering_input_bundle', () => {
    const store = readFileSync(FIVE_STAGE_STORE, 'utf8')
    expect(store).toContain('operator_process_input')
    expect(store).not.toContain('engineering_input_bundle')
    expect(store).not.toContain('buildEngineeringInputBundle')
    expect(store).toContain('buildOperatorProcessInput')
    expect(store).toContain('stableOperatorProcessFieldsJson')
  })

  it('operator process input builder only serializes five zone_planning KEY leaves', () => {
    const content = readFileSync(FORM_MODEL, 'utf8')
    const builderBlock = content.slice(
      content.indexOf('export function buildOperatorProcessInput'),
      content.indexOf('export function stableOperatorProcessFieldsJson')
    )
    expect(builderBlock).toContain('OperatorProcessInputV1')
    expect(builderBlock).toContain('zone_planning_inputs')
    expect(builderBlock).not.toContain('cooling_load_inputs')
    expect(builderBlock).not.toContain('equipment_inputs')
    expect(builderBlock).not.toContain('installed_power_inputs')
    expect(builderBlock).not.toContain('investment_inputs')
  })

  it('default operator form state does not pre-fill KEY user numeric leaves', () => {
    const content = readFileSync(FORM_MODEL, 'utf8')
    const defaultBlock = content.slice(
      content.indexOf('export function createDefaultEngineeringInputFormState'),
      content.indexOf('function buildCoolingZoneLeaves')
    )
    expect(defaultBlock).not.toMatch(/dailyInboundMassKg:\s*\d/)
    expect(defaultBlock).not.toMatch(/finishedStorageDays:\s*\d/)
    expect(defaultBlock).not.toMatch(/frozenStorageDays:\s*\d/)
    expect(defaultBlock).not.toMatch(/mainPackagingStorageDays:\s*\d/)
    expect(defaultBlock).not.toMatch(/auxiliaryPackagingStorageDays:\s*\d/)
    expect(defaultBlock).not.toMatch(/workingTimeHPerDay:\s*\d/)
    expect(defaultBlock).not.toMatch(/packagingStorageDays:\s*\d/)
    expect(defaultBlock).not.toMatch(/precoolingRequiredRatio:\s*0\.\d+/)
    expect(defaultBlock).not.toMatch(/precoolingRequiredRatio:\s*\d/)
  })

  it('five-stage UI package does not embed engineering formula literals', () => {
    const files = collectTsVueFiles(FIVE_STAGE_DIR)
    for (const file of files) {
      const content = readFileSync(file, 'utf8')
      for (const pattern of FORBIDDEN_FORMULA_PATTERNS) {
        expect(pattern.test(content), `${relative(FRONTEND_SRC, file)} matched ${pattern}`).toBe(
          false
        )
      }
    }
  })

  it('legacy project page remains labeled non-authority for V0.8', () => {
    const page = readFileSync(join(FRONTEND_SRC, 'features/project/components/ProjectPage.vue'), 'utf8')
    expect(page).toContain('V0.4 遗留路径 (planning-run)')
    expect(page).toContain('不是 V0.8 五阶段权威输入')
    expect(page).toContain('OperatorProcessInputV1')
  })
})
