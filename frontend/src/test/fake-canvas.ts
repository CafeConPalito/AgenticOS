import { resetMeasurer } from '@/lib/system-fonts'

/** A canvas where only `installed` fonts change the width of the text. */
export function fakeCanvas(installed: string[]) {
  let font = ''
  const context = {
    set font(value: string) {
      font = value
    },
    get font() {
      return font
    },
    measureText: () => ({
      width:
        installed.find((name) => font.includes(`"${name}"`))?.length ??
        (font.includes('monospace') ? 100 : 80),
    }),
  }
  resetMeasurer()
  return vi
    .spyOn(HTMLCanvasElement.prototype, 'getContext')
    .mockReturnValue(context as unknown as CanvasRenderingContext2D)
}
