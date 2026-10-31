import type { PaletteId } from './builtin-palettes'

/**
 * The built-in themes that come from other projects (phase 22, ADR 0028): their colors,
 * adapted to the app's tokens and contrast, with their authors and license, shown in
 * Acerca de. Every license was checked in the project's repository (2026-10-31).
 */
export interface ThemeCredit {
  name: string
  themes: PaletteId[]
  author: string
  license: string
  url: string
}

export const THEME_CREDITS: ThemeCredit[] = [
  {
    name: 'Ayu',
    themes: ['ayu-dark', 'ayu-light'],
    author: 'Ike Ku y colaboradores',
    license: 'MIT',
    url: 'https://github.com/ayu-theme/vscode-ayu',
  },
  {
    name: 'Catppuccin',
    themes: ['catppuccin-latte', 'catppuccin-mocha'],
    author: 'Catppuccin',
    license: 'MIT',
    url: 'https://github.com/catppuccin/vscode',
  },
  {
    name: 'Dracula',
    themes: ['dracula'],
    author: 'Dracula Theme (Zeno Rocha y colaboradores)',
    license: 'MIT',
    url: 'https://github.com/dracula/visual-studio-code',
  },
  {
    name: 'GitHub Theme',
    themes: ['github-dark', 'github-light'],
    author: 'GitHub (Primer)',
    license: 'MIT',
    url: 'https://github.com/primer/github-vscode-theme',
  },
  {
    name: 'Gruvbox',
    themes: ['gruvbox-dark', 'gruvbox-light'],
    author: 'Pavel Pertsev (morhetz); para VS Code, jdinhify',
    license: 'MIT',
    url: 'https://github.com/morhetz/gruvbox',
  },
  {
    name: 'Night Owl',
    themes: ['night-owl', 'light-owl'],
    author: 'Sarah Drasner',
    license: 'MIT',
    url: 'https://github.com/sdras/night-owl-vscode-theme',
  },
  {
    name: 'Nord',
    themes: ['nord'],
    author: 'Sven Greb (Nord)',
    license: 'MIT',
    url: 'https://github.com/nordtheme/visual-studio-code',
  },
  {
    name: 'One Dark',
    themes: ['one-dark'],
    author: 'GitHub (Atom One Dark); para VS Code, Binaryify',
    license: 'MIT',
    url: 'https://github.com/Binaryify/OneDark-Pro',
  },
  {
    name: 'Solarized',
    themes: ['solarized-dark', 'solarized-light'],
    author: 'Ethan Schoonover',
    license: 'MIT',
    url: 'https://github.com/altercation/solarized',
  },
  {
    name: 'Tokyo Night',
    themes: ['tokyo-night', 'tokyo-night-day'],
    author: 'enkia y colaboradores',
    license: 'MIT',
    url: 'https://github.com/tokyo-night/tokyo-night-vscode-theme',
  },
]

/** The app's own themes made from a palette: no credit needed. */
export const OWN_PALETTES: PaletteId[] = ['forest', 'ocean', 'wine', 'sand', 'lavender', 'mint']
