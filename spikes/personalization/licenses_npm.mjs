// S5: production dependency tree of the frontend with each package's license.
import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

const roots = process.argv.slice(2)
const seen = new Map()
function visit(name, from) {
  if (seen.has(name)) return
  let dir = join(from, 'node_modules', name)
  if (!existsSync(dir)) dir = join('node_modules', name)
  if (!existsSync(join(dir, 'package.json'))) return
  const pkg = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'))
  const lic = typeof pkg.license === 'string' ? pkg.license : (pkg.license?.type ?? ((pkg.licenses ?? []).map((l) => l.type).join(' OR ') || 'UNKNOWN'))
  seen.set(name, { version: pkg.version, license: lic })
  for (const dep of Object.keys(pkg.dependencies ?? {})) visit(dep, dir)
}
for (const root of roots) {
  const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
  for (const dep of Object.keys(pkg.dependencies ?? {})) visit(dep, root)
}
const byLicense = {}
for (const [name, info] of seen) (byLicense[info.license] ??= []).push(name)
for (const [lic, names] of Object.entries(byLicense).sort((a, b) => b[1].length - a[1].length))
  console.log(`${lic}\t${names.length}\t${names.length <= 6 ? names.join(', ') : ''}`)
console.log(`TOTAL\t${seen.size}`)
