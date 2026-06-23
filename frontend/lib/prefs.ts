const PREF_KEY = "quantdesk-ui-prefs"

interface UiPrefs {
  refreshInterval: number
  defaultPage: string
  ordersPageSize: number
  compactMode: boolean
  showTooltips: boolean
}

const DEFAULT_PREFS: UiPrefs = {
  refreshInterval: 30,
  defaultPage: "/",
  ordersPageSize: 20,
  compactMode: false,
  showTooltips: true,
}

function loadPrefs(): UiPrefs {
  if (typeof window === "undefined") return DEFAULT_PREFS
  try {
    const raw = localStorage.getItem(PREF_KEY)
    if (!raw) return DEFAULT_PREFS
    return { ...DEFAULT_PREFS, ...JSON.parse(raw) }
  } catch {
    return DEFAULT_PREFS
  }
}

function getPref<K extends keyof UiPrefs>(key: K): UiPrefs[K] {
  return loadPrefs()[key]
}

export { loadPrefs, getPref }
export type { UiPrefs }
