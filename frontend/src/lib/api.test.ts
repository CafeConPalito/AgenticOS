import { invoke, isTauri } from '@tauri-apps/api/core'
import { DEFAULT_API_URL, getApiBaseUrl, resetApiBaseUrl } from './api'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn(), isTauri: vi.fn() }))

describe('getApiBaseUrl', () => {
  beforeEach(() => {
    resetApiBaseUrl()
    vi.mocked(invoke).mockReset()
    vi.mocked(isTauri).mockReset()
  })

  it('uses the default URL in the browser', async () => {
    vi.mocked(isTauri).mockReturnValue(false)
    await expect(getApiBaseUrl()).resolves.toBe(DEFAULT_API_URL)
    expect(invoke).not.toHaveBeenCalled()
  })

  it('asks Tauri for the sidecar URL, retrying until it is ready', async () => {
    vi.useFakeTimers()
    vi.mocked(isTauri).mockReturnValue(true)
    vi.mocked(invoke)
      .mockRejectedValueOnce('starting')
      .mockResolvedValueOnce('http://127.0.0.1:51234')
    const url = getApiBaseUrl()
    await vi.advanceTimersByTimeAsync(300)
    await expect(url).resolves.toBe('http://127.0.0.1:51234')
    expect(invoke).toHaveBeenCalledWith('backend_url')
    expect(invoke).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })

  it('fails fast on a permanent backend error', async () => {
    vi.mocked(isTauri).mockReturnValue(true)
    vi.mocked(invoke).mockRejectedValue('backend exited (code Some(1))')
    await expect(getApiBaseUrl()).rejects.toThrow('backend exited')
    expect(invoke).toHaveBeenCalledTimes(1)
  })

  it('caches the resolved URL', async () => {
    vi.mocked(isTauri).mockReturnValue(true)
    vi.mocked(invoke).mockResolvedValue('http://127.0.0.1:51234')
    await getApiBaseUrl()
    await getApiBaseUrl()
    expect(invoke).toHaveBeenCalledTimes(1)
  })
})
