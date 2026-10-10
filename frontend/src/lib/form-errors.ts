import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import { toast } from 'sonner'
import i18n from '@/i18n'
import { ApiError } from '@/lib/api'

/** Human message for an API error code (falls back to a generic message). */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const key = `errors.${error.code}`
    // Dynamic key coming from the backend: checked with exists() before use.
    return i18n.exists(key)
      ? i18n.t(key as never)
      : i18n.t('errors.generic', { message: error.message })
  }
  return i18n.t('errors.network')
}

/**
 * Shows an API error on the form field it refers to (when the field is part of the form),
 * otherwise as a toast.
 */
export function applyApiError<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): void {
  const message = errorMessage(error)
  if (error instanceof ApiError && error.field && fields.includes(error.field)) {
    setError(error.field as Path<T>, { type: 'server', message })
  } else {
    toast.error(message)
  }
}
