import type { WorkflowAggregateV1 } from '../../../api/contracts/workflow'
import { apiClient, type HttpClient } from '../../../api/httpClient'

export interface WorkflowApi {
  getAggregate(
    projectId: string,
    version: number,
    workflowGoal?: string,
    signal?: AbortSignal
  ): Promise<WorkflowAggregateV1>
}

export function createWorkflowApi(client: HttpClient = apiClient): WorkflowApi {
  return {
    async getAggregate(projectId, version, workflowGoal = 'formal_report', signal) {
      const query =
        workflowGoal === 'formal_report' ? '' : `?workflow_goal=${encodeURIComponent(workflowGoal)}`
      return client.requestJson<WorkflowAggregateV1>(
        `/api/v1/projects/${projectId}/versions/${version}/workflow${query}`,
        { signal }
      )
    }
  }
}
