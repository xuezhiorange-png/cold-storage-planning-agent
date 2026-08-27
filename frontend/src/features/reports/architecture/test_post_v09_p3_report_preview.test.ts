import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import ReportExportPanel from '../components/ReportExportPanel.vue'

vi.mock('../composables/useReportExport', () => {
  const revisionContent = ref({
    project_summary: {
      project_name: 'V0.9 sample'
    },
    input_conditions: {
      daily_inbound_mass_kg: 20000,
      finished_storage_days: 7,
      frozen_storage_days: 10,
      main_packaging_storage_days: 4,
      auxiliary_packaging_storage_days: 12
    },
    calculation_logic: {
      stages: [
        {
          stage: 'zone',
          calculation_id: 'zone-1',
          formulas: [{ formula_id: 'ZP-001', expression: 'daily_mass' }]
        }
      ]
    }
  })

  return {
    createDefaultExportForm: () => ({
      format: 'pdf',
      locale: 'zh-CN',
      mode: 'draft'
    }),
    DRAFT_EXPORT_POLICY_COPY: '草稿导出不校验正式门槛',
    FORMAL_EXPORT_POLICY_COPY: '正式导出需后端再次校验',
    selectDisplayedExportBlockers: () => [],
    useReportExport: () => ({
      reports: ref([{ id: 'report-1', status: 'draft' }]),
      reportsLoading: ref(false),
      reportsError: ref(''),
      reportDetail: ref({ id: 'report-1', status: 'draft', revision_number: 1 }),
      reportDetailLoading: ref(false),
      reportDetailError: ref(''),
      createLoading: ref(false),
      createError: ref(''),
      generateLoading: ref(false),
      generateError: ref(''),
      actionBlockers: ref([]),
      reviewLoading: ref(false),
      reviewError: ref(''),
      selectedReportId: ref('report-1'),
      selectedRevisionNumber: ref(1),
      revisions: ref([{ revision_number: 1 }]),
      revisionsLoading: ref(false),
      revisionsError: ref(''),
      exports: ref([]),
      exportsLoading: ref(false),
      exportsError: ref(''),
      renderLoading: ref(false),
      renderError: ref(''),
      renderResult: ref(null),
      downloadLoading: ref(false),
      downloadError: ref(''),
      loadReports: vi.fn(),
      createAndGenerateReport: vi.fn(),
      generateRevision: vi.fn(),
      submitReview: vi.fn(),
      markReviewed: vi.fn(),
      approveReport: vi.fn(),
      selectReport: vi.fn(),
      renderReport: vi.fn(),
      downloadArtifact: vi.fn(),
      reset: vi.fn(),
      revisionContent,
      revisionContentLoading: ref(false),
      revisionContentError: ref('')
    })
  }
})

describe('POST-V0.9 P3 report preview', () => {
  it('shows persisted five KEY and formula list without computing values', async () => {
    const wrapper = mount(ReportExportPanel, {
      props: {
        projectId: 'project-1',
        projectVersionId: 'version-1',
        formalExportEligible: false,
        formalExportBlockers: []
      }
    })

    await wrapper.get('[aria-controls="report-detail-report-1"]').trigger('click')

    const text = wrapper.text()
    expect(text).toContain('daily_inbound_mass_kg')
    expect(text).toContain('20000')
    expect(text).toContain('calculation_logic')
    expect(text).toContain('ZP-001')
    expect(text).toContain('daily_mass')
  })
})
