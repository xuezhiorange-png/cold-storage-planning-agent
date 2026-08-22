import type {
  CreateProjectResponse,
  ProjectSummaryResponse,
  ProjectVersionResponse
} from '../../../api/contracts/projects'
import { apiClient, type HttpClient } from '../../../api/httpClient'

export interface ProjectsApi {
  createProject(payload: {
    name: string
    location: string
    product_category: string
  }): Promise<CreateProjectResponse>
  getProject(projectId: string): Promise<ProjectSummaryResponse>
  getVersion(projectId: string, version: number): Promise<ProjectVersionResponse>
  saveInputs(
    projectId: string,
    version: number,
    inputs: Record<string, unknown>
  ): Promise<{ success: boolean }>
}

export function createProjectsApi(client: HttpClient = apiClient): ProjectsApi {
  return {
    async createProject(payload) {
      return client.requestJson<CreateProjectResponse>('/api/v1/projects', {
        method: 'POST',
        body: payload
      })
    },
    async getProject(projectId) {
      return client.requestJson<ProjectSummaryResponse>(`/api/v1/projects/${projectId}`)
    },
    async getVersion(projectId, version) {
      return client.requestJson<ProjectVersionResponse>(
        `/api/v1/projects/${projectId}/versions/${version}`
      )
    },
    async saveInputs(projectId, version, inputs) {
      return client.requestJson<{ success: boolean }>(
        `/api/v1/projects/${projectId}/versions/${version}/inputs`,
        {
          method: 'PUT',
          body: { inputs }
        }
      )
    }
  }
}
