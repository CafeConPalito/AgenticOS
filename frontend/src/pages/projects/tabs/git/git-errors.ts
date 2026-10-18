import type { TFunction } from 'i18next'
import { ApiError } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'

/** What to tell the person when a git operation fails: by its code, else git's own message. */
export function gitErrorText(error: unknown, t: TFunction): string {
  if (error instanceof ApiError)
    return t(`git.errors.${error.code}`, { defaultValue: errorMessage(error) })
  return errorMessage(error)
}
