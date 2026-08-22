export interface CreateProjectResponse {
  id: string
  code: string
  current_version_number: number
}

export interface ProjectVersionResponse {
  id: string
  version_number: number
  status: string
  input_snapshot: Record<string, unknown>
  change_summary?: string
}

export interface ProjectSummaryResponse {
  id: string
  code: string
  name: string
  location: string
  product_category: string
  status: string
  current_version_number: number
}
