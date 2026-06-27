import { describe, expect, it, vi } from 'vitest'

import type { HttpClient } from '../../../api/httpClient'
import { createReportsApi } from './reportsApi'

function createClient(): HttpClient {
  return {
    requestJson: vi.fn(),
    requestBlob: vi.fn(),
    requestBinary: vi.fn()
  }
}

describe('reportsApi', () => {
  it('maps locale, format, mode, and idempotency into the render request', async () => {
    const client = createClient()
    vi.mocked(client.requestJson).mockResolvedValue({
      artifact_id: 'artifact-1',
      status: 'completed',
      format: 'pdf',
      file_name: 'report.pdf',
      file_size_bytes: 100,
      file_sha256: 'sha',
      locale: 'en-US',
      template_locale: 'en-US',
      translation_catalog_version: '1.0.0',
      translation_catalog_content_hash: 'catalog-hash',
      localized_template_content_hash: 'template-hash'
    })

    const api = createReportsApi(client)
    await api.render('report/1', 3, {
      format: 'pdf',
      mode: 'formal',
      locale: 'en-US',
      template_version: '2.0.0',
      idempotency_key: 'export-1'
    })

    expect(client.requestJson).toHaveBeenCalledWith(
      '/api/v1/reports/report%2F1/revisions/3/render',
      {
        method: 'POST',
        body: {
          format: 'pdf',
          mode: 'formal',
          locale: 'en-US',
          template_version: '2.0.0',
          idempotency_key: 'export-1'
        },
        signal: undefined
      }
    )
  })

  it('preserves artifact integrity metadata from download response headers', async () => {
    const client = createClient()
    vi.mocked(client.requestBinary).mockResolvedValue({
      blob: new Blob(['pdf'], { type: 'application/pdf' }),
      status: 200,
      headers: new Headers({
        'Content-Disposition': "attachment; filename*=UTF-8''design%20report.pdf",
        'X-Artifact-Id': 'artifact-1',
        'X-Content-SHA256': 'artifact-sha',
        'X-Source-Content-Hash': 'source-hash',
        'X-Template-Version': '2.0.0',
        'X-Report-Locale': 'zh-CN',
        'X-Template-Locale': 'zh-CN',
        'X-Translation-Catalog-Version': '1.0.0',
        'X-Translation-Catalog-Content-Hash': 'catalog-hash',
        'X-Localized-Template-Content-Hash': 'localized-template-hash'
      })
    })

    const api = createReportsApi(client)
    const result = await api.download('report-1', 'artifact-1')

    expect(result).toMatchObject({
      artifactId: 'artifact-1',
      fileName: 'design report.pdf',
      contentSha256: 'artifact-sha',
      sourceContentHash: 'source-hash',
      templateVersion: '2.0.0',
      locale: 'zh-CN',
      templateLocale: 'zh-CN',
      translationCatalogVersion: '1.0.0',
      translationCatalogContentHash: 'catalog-hash',
      localizedTemplateContentHash: 'localized-template-hash'
    })
  })

  it('fails closed when an integrity header is missing', async () => {
    const client = createClient()
    vi.mocked(client.requestBinary).mockResolvedValue({
      blob: new Blob(['pdf']),
      status: 200,
      headers: new Headers()
    })

    const api = createReportsApi(client)

    await expect(api.download('report-1', 'artifact-1')).rejects.toThrow(
      'Artifact download response is missing required header: X-Artifact-Id'
    )
  })
})
