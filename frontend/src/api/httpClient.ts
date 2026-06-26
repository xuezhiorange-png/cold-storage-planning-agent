import { ApiError, ApiRequestCancelledError, type ApiErrorDetails } from './errors'

export interface ApiRequestOptions extends Omit<RequestInit, 'body' | 'headers'> {
  body?: BodyInit | Record<string, unknown> | unknown[] | null
  headers?: HeadersInit
  idempotencyKey?: string
}

export interface HttpClient {
  requestJson<T>(path: string, options?: ApiRequestOptions): Promise<T>
  requestBlob(path: string, options?: ApiRequestOptions): Promise<Blob>
}

interface ErrorPayload {
  message: string
  code: string
  details: ApiErrorDetails
}

function joinUrl(baseUrl: string, path: string): string {
  if (/^https?:\/\//u.test(path)) return path

  const normalizedBase = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${normalizedBase}${normalizedPath}`
}

function isJsonBody(body: ApiRequestOptions['body']): body is Record<string, unknown> | unknown[] {
  if (body === null || body === undefined) return false
  if (Array.isArray(body)) return true
  if (typeof body !== 'object') return false

  return !(
    body instanceof Blob ||
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof ArrayBuffer ||
    ArrayBuffer.isView(body)
  )
}

function toRequestInit(options: ApiRequestOptions): RequestInit {
  const headers = new Headers(options.headers)
  let body: BodyInit | null | undefined = options.body as BodyInit | null | undefined

  if (isJsonBody(options.body)) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(options.body)
  }

  if (options.idempotencyKey) {
    headers.set('Idempotency-Key', options.idempotencyKey)
  }

  const { idempotencyKey: _idempotencyKey, ...requestOptions } = options
  return {
    ...requestOptions,
    headers,
    body
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function readString(record: Record<string, unknown> | null, key: string): string | null {
  const value = record?.[key]
  return typeof value === 'string' && value.trim() ? value : null
}

async function readErrorPayload(response: Response): Promise<ErrorPayload> {
  const raw = await response.text()
  let parsed: unknown = null

  if (raw) {
    try {
      parsed = JSON.parse(raw) as unknown
    } catch {
      parsed = raw
    }
  }

  const record = asRecord(parsed)
  const detail = record?.detail
  const detailRecord = asRecord(detail)
  const message =
    readString(record, 'message') ??
    readString(record, 'error') ??
    readString(detailRecord, 'message') ??
    (typeof detail === 'string' ? detail : null) ??
    (typeof parsed === 'string' ? parsed : null) ??
    `Request failed with status ${response.status}`

  return {
    message,
    code:
      readString(record, 'code') ??
      readString(detailRecord, 'code') ??
      `http_${response.status}`,
    details: (detail ?? parsed) as ApiErrorDetails
  }
}

function normalizeTransportError(error: unknown): never {
  if (error instanceof DOMException && error.name === 'AbortError') {
    throw new ApiRequestCancelledError()
  }
  throw error
}

export function createHttpClient(baseUrl = import.meta.env.VITE_API_BASE_URL ?? ''): HttpClient {
  async function execute(path: string, options: ApiRequestOptions): Promise<Response> {
    try {
      const response = await fetch(joinUrl(baseUrl, path), toRequestInit(options))
      if (!response.ok) {
        const payload = await readErrorPayload(response)
        throw new ApiError({
          status: response.status,
          message: payload.message,
          code: payload.code,
          details: payload.details,
          retryable: response.status >= 500 || response.status === 429
        })
      }
      return response
    } catch (error) {
      return normalizeTransportError(error)
    }
  }

  return {
    async requestJson<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
      const response = await execute(path, options)
      if (response.status === 204) return undefined as T
      return (await response.json()) as T
    },

    async requestBlob(path: string, options: ApiRequestOptions = {}): Promise<Blob> {
      const response = await execute(path, options)
      return response.blob()
    }
  }
}

export const apiClient = createHttpClient()
