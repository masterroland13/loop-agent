export type FilesAutoSaveMode = 'off' | 'blur' | 'interval'

const STORAGE_KEY = 'loop:files-auto-save'
const LEGACY_STORAGE_KEY = 'hal:files-auto-save'

export function loadFilesAutoSaveMode(): FilesAutoSaveMode {
  try {
    let raw = localStorage.getItem(STORAGE_KEY)
    if (raw == null) {
      raw = localStorage.getItem(LEGACY_STORAGE_KEY)
      if (raw != null) localStorage.setItem(STORAGE_KEY, raw)
    }
    if (raw === 'off' || raw === 'blur' || raw === 'interval') return raw
  } catch {
    // ignore
  }
  return 'blur'
}

export function saveFilesAutoSaveMode(mode: FilesAutoSaveMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    // ignore
  }
}

export function fileNameFromPath(path: string): string {
  const norm = path.replace(/\\/g, '/')
  const i = norm.lastIndexOf('/')
  return i >= 0 ? norm.slice(i + 1) : norm
}

export function isMarkdownFilePath(path: string): boolean {
  return /\.(md|mdx|markdown)$/i.test(fileNameFromPath(path))
}

export function isDocxFilePath(path: string): boolean {
  return /\.docx$/i.test(fileNameFromPath(path))
}
