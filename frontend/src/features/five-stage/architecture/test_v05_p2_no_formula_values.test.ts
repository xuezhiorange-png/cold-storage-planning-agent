import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_SRC = join(process.cwd(), 'src')
const FIVE_STAGE_DIR = join(FRONTEND_SRC, 'features/five-stage')
const FIVE_STAGE_STORE = join(FRONTEND_SRC, 'stores/fiveStageExecution.ts')

const FORBIDDEN_PATTERNS = [
  /\butilization_factor\s*[:=]\s*0\.\d+/,
  /\breserve_factor\s*[:=]\s*0\.\d+/,
  /\b\d+\.?\d*\s*\*\s*\d+\.?\d*\s*\/\s*\d+/,
  /planning-run/
]

const ALLOWED_PLANNING_RUN_PATHS = new Set([
  'features/project/components/ProjectPage.vue',
  'stores/planningWorkflow.ts',
  'features/calculations/api/planningApi.ts',
  'features/calculations/composables/usePlanningRun.ts',
  'features/calculations/model/mapPersistedCalculations.ts'
])

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

describe('V0.5 P2 architecture guards', () => {
  it('five-stage package does not embed utilization_factor/reserve_factor formula literals', () => {
    const files = collectTsVueFiles(FIVE_STAGE_DIR)
    for (const file of files) {
      const content = readFileSync(file, 'utf8')
      for (const pattern of FORBIDDEN_PATTERNS.slice(0, 3)) {
        expect(pattern.test(content), `${relative(FRONTEND_SRC, file)} matched ${pattern}`).toBe(false)
      }
    }
  })

  it('five-stage submit path does not call planning-run', () => {
    const content = readFileSync(FIVE_STAGE_STORE, 'utf8')
    expect(content.includes('planning-run')).toBe(false)
    expect(content.includes('planningApi')).toBe(false)
    expect(content.includes('planningWorkflow')).toBe(false)

    const engineeringPage = readFileSync(
      join(FIVE_STAGE_DIR, 'components/EngineeringInputsPage.vue'),
      'utf8'
    )
    expect(engineeringPage.includes('planning-run')).toBe(false)
    expect(engineeringPage.includes('five-stage-execution')).toBe(false)
    expect(engineeringPage.includes('fiveStageExecution')).toBe(true)
  })

  it('default engineering form state does not pre-fill KEY user numeric leaves', () => {
    const content = readFileSync(
      join(FIVE_STAGE_DIR, 'model/engineeringInputForm.ts'),
      'utf8'
    )
    const defaultBlock = content.slice(
      content.indexOf('export function createDefaultEngineeringInputFormState'),
      content.indexOf('function buildCoolingZoneLeaves')
    )
    expect(defaultBlock).not.toMatch(/dailyInboundMassKg:\s*\d/)
    expect(defaultBlock).not.toMatch(/condensingTemperatureC:\s*\d/)
    expect(defaultBlock).not.toMatch(/compressorInputPowerKwE:\s*\d/)
    expect(defaultBlock).not.toMatch(/designCoolingLoadKwR:\s*\d/)
    expect(defaultBlock).not.toMatch(/zoneArea:\s*\d/)
  })

  it('planning-run references remain only on legacy paths', () => {
    const files = collectTsVueFiles(FRONTEND_SRC)
    for (const file of files) {
      const rel = relative(FRONTEND_SRC, file)
      const content = readFileSync(file, 'utf8')
      if (!content.includes('planning-run')) continue
      if (rel.includes('.test.')) continue
      expect(
        ALLOWED_PLANNING_RUN_PATHS.has(rel) || rel === 'features/project/components/ProjectPage.vue',
        `unexpected planning-run reference in ${rel}`
      ).toBe(true)
    }
  })
})
