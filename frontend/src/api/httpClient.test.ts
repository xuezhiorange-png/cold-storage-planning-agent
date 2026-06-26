import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, ApiRequestCancelledError } from './errors'
import { createHttpClient } from './httpClient'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('createHttpClient', () => {
  it('maps JSON request and response contracts', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ result: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const client = createHttpClient('/api')
    const result = await client.requestJson<{ result: string }>('/planning/run', {
      method: 'POST',
      body: { daily_mass_tons: 25 },
      idempotencyKey: 'planning-25'
    })

    expect(result).toEqual({ result: 'ok' })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(init.headers)
    expect(url).toBe('/api/planning/run')
    expect(init.body).toBe(JSON.stringify({ daily_mass_tons: 25 }))
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('Idempotency-Key')).toBe('planning-25')
  })

  it('normalizes backend error payloads', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: 'report_not_approved',
              message: 'Formal export requires an approved revision'
            }
          }),
          { status: 409 }
        )
      )
    )

    const client = createHttpClient()

    await expect(client.requestJson('/api/v1/reports/export')).rejects.toMatchObject({
      name: 'ApiError',
      status: 409,
      code: 'report_not_approved',
      message: 'Formal export requires an approved revision',
      retryable: false
    } satisfies Partial<ApiError>)
  })

  it('maps aborted fetches to a cancellation error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new DOMException('The operation was aborted', 'AbortError'))
    )

    const client = createHttpClient()

    await expect(client.requestJson('/api/v1/projects')).rejects.toBeInstanceOf(
      ApiRequestCancelledError
    )
  })

  it('returns binary artifacts without decoding them as JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('report content', { status: 200 }))
    )

    const client = createHttpClient('/api')
    const result = await client.requestBlob('/v1/reports/artifacts/1')

    // Verify binary roundtrip: content, not exact MIME type (jsdom
    // may not preserve blob Content-Type through fetch mock)
    expect(await result.text()).toBe('report content')
    expect(result.size).toBeGreaterThan(0)
  })
})
