import { lstatSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const lifecycleNames = ['preinstall', 'install', 'postinstall']
const expectedLockEntries = new Map([
  ['node_modules/fsevents', { version: '2.3.3', optional: true }],
])

function fail(message) {
  console.error(`install-script-check: ${message}`)
  process.exitCode = 1
}

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'))
}

const lock = readJson(join(root, 'package-lock.json'))
const lockPackages = lock.packages ?? {}

function hasApprovedArtifact(pkg) {
  return (
    typeof pkg?.resolved === 'string' &&
    pkg.resolved.startsWith('https://registry.npmjs.org/') &&
    typeof pkg.integrity === 'string' &&
    /^sha512-[A-Za-z0-9+/]+={0,2}$/.test(pkg.integrity)
  )
}

function bundledParentHasApprovedArtifact(path) {
  let parentPath = path
  while (parentPath.includes('/node_modules/')) {
    parentPath = parentPath.slice(0, parentPath.lastIndexOf('/node_modules/'))
    const parent = lockPackages[parentPath]
    if (parent && !parent.inBundle) return hasApprovedArtifact(parent)
  }
  return false
}

for (const [path, pkg] of Object.entries(lockPackages)) {
  if (path === '') continue
  if (pkg.inBundle && bundledParentHasApprovedArtifact(path)) continue
  if (!hasApprovedArtifact(pkg)) {
    fail(`dependency lacks an approved registry artifact: ${path}`)
  }
}

const actualLockEntries = new Map(
  Object.entries(lockPackages).filter(([, pkg]) => pkg.hasInstallScript)
)

for (const [path, expected] of expectedLockEntries) {
  const actual = actualLockEntries.get(path)
  if (!actual) {
    fail(`approved lock entry is missing: ${path}`)
    continue
  }
  if (actual.version !== expected.version) {
    fail(`${path} changed from ${expected.version} to ${actual.version ?? 'unknown'}`)
  }
  if (Boolean(actual.optional) !== expected.optional) {
    fail(`${path} changed its optional-package status`)
  }
}

for (const path of actualLockEntries.keys()) {
  if (!expectedLockEntries.has(path)) {
    fail(`unreviewed lock entry has an install script: ${path}`)
  }
}

const installedScripts = new Map()

function inspectPackage(packagePath) {
  const metadataPath = join(packagePath, 'package.json')
  const metadata = readJson(metadataPath)
  const scripts = Object.fromEntries(
    lifecycleNames
      .filter((name) => typeof metadata.scripts?.[name] === 'string')
      .map((name) => [name, metadata.scripts[name]])
  )

  if (Object.keys(scripts).length > 0) {
    installedScripts.set(relative(root, packagePath), {
      name: metadata.name,
      version: metadata.version,
      scripts,
    })
  }

  const nested = join(packagePath, 'node_modules')
  try {
    if (lstatSync(nested).isDirectory()) {
      inspectNodeModules(nested)
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
}

function inspectNodeModules(nodeModulesPath) {
  for (const entry of readdirSync(nodeModulesPath, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue
    const entryPath = join(nodeModulesPath, entry.name)
    if (entry.isSymbolicLink()) {
      fail(`unexpected package symlink: ${relative(root, entryPath)}`)
      continue
    }
    if (!entry.isDirectory()) continue

    if (entry.name.startsWith('@')) {
      for (const scoped of readdirSync(entryPath, { withFileTypes: true })) {
        const scopedPath = join(entryPath, scoped.name)
        if (scoped.isSymbolicLink()) {
          fail(`unexpected package symlink: ${relative(root, scopedPath)}`)
        } else if (scoped.isDirectory()) {
          inspectPackage(scopedPath)
        }
      }
    } else {
      inspectPackage(entryPath)
    }
  }
}

inspectNodeModules(join(root, 'node_modules'))

for (const [path, installed] of installedScripts) {
  const expected = expectedLockEntries.get(path)
  if (!expected) {
    fail(
      `unreviewed installed package has lifecycle scripts: ${installed.name}@${installed.version} (${path})`
    )
    continue
  }
  if (installed.version !== expected.version) {
    fail(`${path} installed version does not match the reviewed lock entry`)
  }
}

if (process.exitCode) process.exit(process.exitCode)
console.log(
  'Install-script inventory verified: fsevents@2.3.3 is optional and blocked; no lifecycle scripts were executed.'
)
