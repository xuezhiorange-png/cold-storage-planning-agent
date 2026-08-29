/// <reference types="vite/client" />

declare module '@v09-operator-demo' {
  const manifest: {
    operator_process_input: {
      schema_id: string
      schema_version: string
      zone_planning_inputs: Record<
        string,
        {
          value: string
          unit: string
          state: string
        }
      >
    }
  }
  export default manifest
}
