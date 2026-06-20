export interface ApiError {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}

export interface CalculationResult {
  calculator_name: string
  result: Record<string, unknown>
  formula_references: Array<Record<string, unknown>>
  coefficients: Array<Record<string, unknown>>
  assumptions: string[]
  warnings: Array<Record<string, unknown>>
  requires_review: boolean
}

export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  return (await response.json()) as T
}
