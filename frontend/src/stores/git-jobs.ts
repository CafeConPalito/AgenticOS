import { create } from 'zustand'
import type { JobState } from '@/api/git'

interface GitJobsState {
  /** The jobs this session knows of: running ones and those that just ended. */
  jobs: Record<string, JobState>
  upsert: (job: JobState) => void
  dismiss: (id: string) => void
}

export const useGitJobs = create<GitJobsState>((set) => ({
  jobs: {},
  upsert: (job) => set((state) => ({ jobs: { ...state.jobs, [job.id]: job } })),
  dismiss: (id) =>
    set((state) => ({
      jobs: Object.fromEntries(Object.entries(state.jobs).filter(([key]) => key !== id)),
    })),
}))
