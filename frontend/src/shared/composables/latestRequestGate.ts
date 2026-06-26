export interface LatestRequestHandle {
  readonly signal: AbortSignal
  isCurrent(): boolean
  finish(): void
}

export class LatestRequestGate {
  private sequence = 0
  private activeController: AbortController | null = null

  begin(): LatestRequestHandle {
    this.activeController?.abort()

    const requestId = ++this.sequence
    const controller = new AbortController()
    this.activeController = controller

    return {
      signal: controller.signal,
      isCurrent: () => requestId === this.sequence && !controller.signal.aborted,
      finish: () => {
        if (requestId === this.sequence && this.activeController === controller) {
          this.activeController = null
        }
      }
    }
  }

  cancel(): void {
    this.sequence += 1
    this.activeController?.abort()
    this.activeController = null
  }
}
