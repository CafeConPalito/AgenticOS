/**
 * Photos for agent avatars (phase 20, spike S6). The size is read from the file's header so a
 * photo over the limit is refused before it is decoded; the crop is drawn on a canvas and only
 * that small picture leaves the browser. Nothing here writes the original anywhere.
 */

export const MAX_PHOTO_SIDE = 2048
export const CROP_SIDE = 256
export const PHOTO_TYPES = ['image/png', 'image/jpeg', 'image/webp']

export interface ImageSize {
  width: number
  height: number
}

/** Width and height from the header of a PNG, JPEG or WebP, or null if it is none of them. */
export function headerSize(buffer: ArrayBuffer): ImageSize | null {
  const v = new DataView(buffer)
  if (v.byteLength < 30) return null
  if (v.getUint32(0) === 0x89504e47) return { width: v.getUint32(16), height: v.getUint32(20) }
  if (v.getUint16(0) === 0xffd8) {
    let offset = 2
    while (offset + 9 < v.byteLength) {
      const marker = v.getUint16(offset)
      const length = v.getUint16(offset + 2)
      // Start of frame (baseline, progressive…), not the Huffman/arithmetic tables.
      if (marker >= 0xffc0 && marker <= 0xffcf && ![0xffc4, 0xffc8, 0xffcc].includes(marker))
        return { width: v.getUint16(offset + 7), height: v.getUint16(offset + 5) }
      offset += 2 + length
    }
    return null
  }
  if (v.getUint32(0) === 0x52494646 && v.getUint32(8) === 0x57454250) {
    const chunk = String.fromCharCode(...new Uint8Array(buffer, 12, 4))
    if (chunk === 'VP8X')
      return {
        width: 1 + (v.getUint32(24, true) & 0xffffff),
        height: 1 + (v.getUint32(27, true) & 0xffffff),
      }
    if (chunk === 'VP8L') {
      const bits = v.getUint32(21, true)
      return { width: 1 + (bits & 0x3fff), height: 1 + ((bits >> 14) & 0x3fff) }
    }
    if (chunk === 'VP8 ')
      return { width: v.getUint16(26, true) & 0x3fff, height: v.getUint16(28, true) & 0x3fff }
  }
  return null
}

export type PhotoCheck = { ok: true; size: ImageSize } | { ok: false; reason: 'format' | 'size' }

/** Whether a file may be cropped: a PNG, JPEG or WebP of MAX_PHOTO_SIDE px or less per side. */
export async function checkPhoto(file: File): Promise<PhotoCheck> {
  if (!PHOTO_TYPES.includes(file.type)) return { ok: false, reason: 'format' }
  const size = headerSize(await file.slice(0, 65536).arrayBuffer())
  if (!size) return { ok: false, reason: 'format' }
  if (size.width > MAX_PHOTO_SIDE || size.height > MAX_PHOTO_SIDE)
    return { ok: false, reason: 'size' }
  return { ok: true, size }
}

export interface CropArea {
  x: number
  y: number
  width: number
  height: number
}

/** The chosen square of `file`, as a CROP_SIDE px WebP (PNG where WebP cannot be encoded). */
export async function cropToBlob(file: File, area: CropArea): Promise<Blob> {
  const bitmap = await createImageBitmap(file)
  try {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = CROP_SIDE
    const context = canvas.getContext('2d')
    if (!context) throw new Error('canvas unavailable')
    context.imageSmoothingQuality = 'high'
    context.drawImage(bitmap, area.x, area.y, area.width, area.height, 0, 0, CROP_SIDE, CROP_SIDE)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/webp', 0.85),
    )
    if (!blob) throw new Error('could not encode the crop')
    return blob
  } finally {
    // The decoded original is let go at once.
    bitmap.close()
  }
}
