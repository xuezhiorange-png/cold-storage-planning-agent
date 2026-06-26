export type ApiErrorDetails = Record<string, unknown> | unknown[] | string | null

export interface ApiErrorInit {
  status: number
  message: string
  code?: string
  details?: ApiErrorDetails
  retryable?: boolean
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: ApiErrorDetails
  readonly retryable: boolean

  constructor(init: ApiErrorInit) {
    super(init.message)
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code ?? 'api_error'
    this.details = init.details ?? null
    this.retryable = init.retryable ?? init.status >= 500
  }
}

export class ApiRequestCancelledError extends Error {
  constructor() {
    super('Request was cancelled')
    this.name = 'ApiRequestCancelledError'
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export function isRequestCancelled(error: unknown): error is ApiRequestCancelledError {
  return error instanceof ApiRequestCancelledError
}
