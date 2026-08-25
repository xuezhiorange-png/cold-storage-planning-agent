import type {
  BundleLeaf,
  BundleLeafState,
  BundleSourceType,
  BundleValidityStatus
} from '../../../api/contracts/fiveStage'

export interface BundleLeafOptions {
  unit?: string | null
  state?: BundleLeafState
  source_type?: BundleSourceType
  validity_status?: BundleValidityStatus
  requires_review?: boolean
}

export function bundleLeaf<T>(
  value: T,
  options: BundleLeafOptions = {}
): BundleLeaf<T> {
  return {
    value,
    unit: options.unit ?? null,
    state: options.state ?? 'provided',
    source_type: options.source_type ?? 'user',
    validity_status: options.validity_status ?? 'unverified',
    requires_review: options.requires_review ?? true
  }
}

export function bundleLeafFromInput(
  value: string | number | boolean | null | undefined,
  options: BundleLeafOptions = {}
): BundleLeaf {
  const hasValue = value !== null && value !== undefined && value !== ''
  return bundleLeaf(hasValue ? value : null, {
    ...options,
    state: hasValue ? (options.state ?? 'provided') : 'missing'
  })
}

export function bundleNumericLeaf(
  value: number | null | undefined,
  options: BundleLeafOptions = {}
): BundleLeaf {
  const hasValue = value !== null && value !== undefined && Number.isFinite(value)
  return bundleLeaf(hasValue ? String(value) : null, {
    ...options,
    state: hasValue ? (options.state ?? 'provided') : 'missing'
  })
}
