import type {
  ArtifactDetailResponse,
  ArtifactDownload,
  ArtifactResponse,
  ListExportsResponse,
  ListReportsResponse,
  ListRevisionsResponse,
  RenderReportRequest,
  ReportDetailResponse,
  ReportLocale
} from '../../../api/contracts/reports'
import { apiClient, type HttpClient } from '../../../api/httpClient'

export interface ReportsApi {
  list(projectId?: string, signal?: AbortSignal): Promise<ListReportsResponse>
  get(reportId: string, signal?: AbortSignal): Promise<ReportDetailResponse>
  listRevisions(reportId: string, signal?: AbortSignal): Promise<ListRevisionsResponse>
  render(
    reportId: string,
    revisionNumber: number,
    request: RenderReportRequest,
    signal?: AbortSignal
  ): Promise<ArtifactResponse>
  listExports(
    reportId: string,
    locale?: ReportLocale,
    signal?: AbortSignal
  ): Promise<ListExportsResponse>
  getArtifact(
    reportId: string,
    artifactId: string,
    signal?: AbortSignal
  ): Promise<ArtifactDetailResponse>
  download(
    reportId: string,
    artifactId: string,
    signal?: AbortSignal
  ): Promise<ArtifactDownload>
}

function segment(value: string): string {
  return encodeURIComponent(value)
}

function parseFileName(contentDisposition: string | null, fallback: string): string {
  if (!contentDisposition) return fallback

  const encodedMatch = /filename\*=UTF-8''([^;]+)/iu.exec(contentDisposition)
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1])
    } catch {
      return encodedMatch[1]
    }
  }

  const quotedMatch = /filename="([^"]+)"/iu.exec(contentDisposition)
  if (quotedMatch?.[1]) return quotedMatch[1]

  const plainMatch = /filename=([^;]+)/iu.exec(contentDisposition)
  return plainMatch?.[1]?.trim() || fallback
}

function requiredHeader(headers: Headers, name: string): string {
  const value = headers.get(name)
  if (!value) {
    throw new Error(`Artifact download response is missing required header: ${name}`)
  }
  return value
}

function reportPath(reportId: string): string {
  return `/api/v1/reports/${segment(reportId)}`
}

export function createReportsApi(client: HttpClient = apiClient): ReportsApi {
  return {
    list(projectId?: string, signal?: AbortSignal): Promise<ListReportsResponse> {
      const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
      return client.requestJson<ListReportsResponse>(`/api/v1/reports${query}`, { signal })
    },

    get(reportId: string, signal?: AbortSignal): Promise<ReportDetailResponse> {
      return client.requestJson<ReportDetailResponse>(reportPath(reportId), { signal })
    },

    listRevisions(reportId: string, signal?: AbortSignal): Promise<ListRevisionsResponse> {
      return client.requestJson<ListRevisionsResponse>(`${reportPath(reportId)}/revisions`, {
        signal
      })
    },

    render(
      reportId: string,
      revisionNumber: number,
      request: RenderReportRequest,
      signal?: AbortSignal
    ): Promise<ArtifactResponse> {
      return client.requestJson<ArtifactResponse>(
        `${reportPath(reportId)}/revisions/${revisionNumber}/render`,
        {
          method: 'POST',
          body: request,
          signal
        }
      )
    },

    listExports(
      reportId: string,
      locale?: ReportLocale,
      signal?: AbortSignal
    ): Promise<ListExportsResponse> {
      const query = locale ? `?locale=${encodeURIComponent(locale)}` : ''
      return client.requestJson<ListExportsResponse>(`${reportPath(reportId)}/exports${query}`, {
        signal
      })
    },

    getArtifact(
      reportId: string,
      artifactId: string,
      signal?: AbortSignal
    ): Promise<ArtifactDetailResponse> {
      return client.requestJson<ArtifactDetailResponse>(
        `${reportPath(reportId)}/exports/${segment(artifactId)}`,
        { signal }
      )
    },

    async download(
      reportId: string,
      artifactId: string,
      signal?: AbortSignal
    ): Promise<ArtifactDownload> {
      const response = await client.requestBinary(
        `${reportPath(reportId)}/exports/${segment(artifactId)}/download`,
        { signal }
      )
      const fallbackFileName = `report-${artifactId}`

      return {
        blob: response.blob,
        artifactId: requiredHeader(response.headers, 'X-Artifact-Id'),
        fileName: parseFileName(response.headers.get('Content-Disposition'), fallbackFileName),
        contentSha256: requiredHeader(response.headers, 'X-Content-SHA256'),
        sourceContentHash: requiredHeader(response.headers, 'X-Source-Content-Hash'),
        templateVersion: requiredHeader(response.headers, 'X-Template-Version'),
        locale: requiredHeader(response.headers, 'X-Report-Locale') as ReportLocale,
        templateLocale: requiredHeader(response.headers, 'X-Template-Locale') as ReportLocale,
        translationCatalogVersion: requiredHeader(
          response.headers,
          'X-Translation-Catalog-Version'
        ),
        translationCatalogContentHash: requiredHeader(
          response.headers,
          'X-Translation-Catalog-Content-Hash'
        ),
        localizedTemplateContentHash: requiredHeader(
          response.headers,
          'X-Localized-Template-Content-Hash'
        )
      }
    }
  }
}

export const reportsApi = createReportsApi()
