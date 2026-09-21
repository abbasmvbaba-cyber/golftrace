import { create } from 'zustand'

type Lang = 'en' | 'fa'

interface UIState {
  lang: Lang
  dir: 'ltr' | 'rtl'
  setLang: (lang: Lang) => void
}

export const useUIStore = create<UIState>((set) => ({
  lang: 'en',
  dir: 'ltr',
  setLang: (lang) => set({ lang, dir: lang === 'fa' ? 'rtl' : 'ltr' })
}))
