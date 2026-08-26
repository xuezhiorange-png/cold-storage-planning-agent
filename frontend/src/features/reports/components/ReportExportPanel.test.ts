/**
 * @vitest-environment jsdom
 */
import { ref, computed } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import ReportExportPanel from '../components/ReportExportPanel.vue'
import { useReportExport } from '../composables/useReportExport'

vi.mock('../composables/useReportExport', () => ({
  createDefaultExportForm: vi.fn(() => ({
    format: 'pdf',
    mode: 'draft',
    locale: 'zh-CN',
    templateVersion: null,
    idempotencyKey: null
  })),
  useReportExport: vi.fn()
}))

function mockExportContext(overrides: Record<string, unknown> = {}) {
  const defaults = {
    reports: ref([]),
    reportsLoading: ref(false),
    reportsError: ref(''),
    reportDetail: ref(null),
    reportDetailLoading: ref(false),
    reportDetailError: ref(''),
    createLoading: ref(false),
    createError: ref(''),
    generateLoading: ref(false),
    generateError: ref(''),
    actionBlockers: ref([]),
    reviewLoading: ref(false),
    reviewError: ref(''),
    selectedReportId: ref(null),
    selectedRevisionNumber: ref(null),
    selectedReport: computed(() => null),
    revisions: ref([]),
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
    downloadResult: ref(null),
    loadReports: vi.fn(),
    loadReportDetail: vi.fn(),
    createAndGenerateReport: vi.fn(),
    generateRevision: vi.fn(),
    submitReview: vi.fn(),
    markReviewed: vi.fn(),
    approveReport: vi.fn(),
    selectReport: vi.fn(),
    loadRevisions: vi.fn(),
    loadExports: vi.fn(),
    loadRevisionContent: vi.fn(),
    renderReport: vi.fn(),
    downloadArtifact: vi.fn(),
    reset: vi.fn(),
    revisionContent: ref(null),
    revisionContentLoading: ref(false),
    revisionContentError: ref('')
  }

  return { ...defaults, ...overrides }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ReportExportPanel', () => {
  beforeEach(() => {
    vi.mocked(useReportExport).mockReturnValue(mockExportContext() as unknown as ReturnType<typeof useReportExport>)
  })

  /* ── Structural rendering ─────────────────────────────── */

  it('renders the panel header', () => {
    const wrapper = mount(ReportExportPanel)
    expect(wrapper.text()).toContain('报告导出')
  })

  it('renders refresh button in header', () => {
    const wrapper = mount(ReportExportPanel)
    expect(wrapper.find('.report-export-panel__refresh').exists()).toBe(true)
  })

  it('renders with correct aria label', () => {
    const wrapper = mount(ReportExportPanel)
    expect(wrapper.attributes('aria-label')).toBe('报告导出面板')
  })

  it('renders the correct structural sections', () => {
    const wrapper = mount(ReportExportPanel)
    expect(wrapper.find('.report-export-panel__header').exists()).toBe(true)
    const states = [
      '.report-export-panel__list',
      '.report-export-panel__error',
      '.report-export-panel__loading',
      '.report-export-panel__empty'
    ]
    const found = states.some((sel) => wrapper.find(sel).exists())
    expect(found).toBe(true)
  })

  it('accepts projectId and projectVersionId props', () => {
    const wrapper = mount(ReportExportPanel, {
      props: { projectId: 'proj-1', projectVersionId: 'ver-1' }
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows guided create button in empty state when version id is present', () => {
    const wrapper = mount(ReportExportPanel, {
      props: { projectId: 'proj-1', projectVersionId: 'ver-1' }
    })
    expect(wrapper.find('.report-export-panel__create-btn').exists()).toBe(true)
    expect(wrapper.text()).toContain('创建并生成报告')
  })

  it('disables create when project_version_id is missing', () => {
    const wrapper = mount(ReportExportPanel, {
      props: { projectId: 'proj-1' }
    })
    const btn = wrapper.find('.report-export-panel__create-btn')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('缺少项目版本标识')
  })

  it('shows trusted-operator copy for review actions', async () => {
    vi.mocked(useReportExport).mockReturnValue(
      mockExportContext({
        reports: ref([{ id: 'report-1', status: 'draft' }]),
        revisions: ref([{ revision_number: 1, content_hash: 'h1' }])
      }) as unknown as ReturnType<typeof useReportExport>
    )

    const wrapper = mount(ReportExportPanel, {
      props: { projectId: 'proj-1', projectVersionId: 'ver-1' }
    })

    await wrapper.find('.report-export-panel__toggle').trigger('click')

    expect(wrapper.text()).toContain('受信任操作员审核请求')
    expect(wrapper.text()).toContain('请求提交审核')
    expect(wrapper.text()).toContain('请求批准')
  })

  it('shows workflow formal export blocker messages when ineligible', () => {
    const wrapper = mount(ReportExportPanel, {
      props: {
        projectId: 'proj-1',
        projectVersionId: 'ver-1',
        formalExportEligible: false,
        formalExportBlockers: [{ code: 'STAGE_INCOMPLETE', message: 'Cooling load missing' }]
      }
    })

    expect(wrapper.text()).toContain('Cooling load missing')
  })

  it('disables formal mode option when formal export ineligible', async () => {
    vi.mocked(useReportExport).mockReturnValue(
      mockExportContext({
        reports: ref([{ id: 'report-1', status: 'draft' }]),
        revisions: ref([{ revision_number: 1, content_hash: 'h1' }])
      }) as unknown as ReturnType<typeof useReportExport>
    )

    const wrapper = mount(ReportExportPanel, {
      props: {
        projectId: 'proj-1',
        projectVersionId: 'ver-1',
        formalExportEligible: false
      }
    })

    await wrapper.find('.report-export-panel__toggle').trigger('click')
    const formalOption = wrapper.find('option[value="formal"]')
    expect(formalOption.exists()).toBe(true)
    expect(formalOption.attributes('disabled')).toBeDefined()
  })
})
