import { describe, expect, it, vi } from 'vitest'

import {
  PRODUCTION_PROFILE_CODES,
  PRODUCTION_WEIGHT_SET_REVISION_ID,
  createProductionSchemeRunApi
} from '../../../src/features/five-stage/components/productionSchemeRunApi'

describe('productionSchemeRunApi', () => {
  it('posts to production-scheme-runs with frozen revision and balanced profile', async () => {
    const requestJson = vi.fn().mockResolvedValue({ run_id: 'run-1', source_mode: 'production' })
    const api = createProductionSchemeRunApi({ requestJson, requestBlob: vi.fn(), requestBinary: vi.fn() })

    await api.createRun('proj-1', 1)

    expect(requestJson).toHaveBeenCalledWith(
      '/api/v1/projects/proj-1/versions/1/production-scheme-runs',
      expect.objectContaining({
        method: 'POST',
        body: {
          profile_codes: [...PRODUCTION_PROFILE_CODES],
          weight_set_revision_id: PRODUCTION_WEIGHT_SET_REVISION_ID,
          profile_parameters: {}
        }
      })
    )
  })
})
