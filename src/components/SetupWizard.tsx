import { useEffect, useState } from 'react'
import {
  browseWorkspace,
  activateModelProfile,
  createModelProfile,
  createWorkspaceFolder,
  fetchModelProfiles,
  fetchProviderPresets,
  listSessions,
  setWorkspace,
  updateModelProfile,
  updateSessionModel,
  type ProviderPreset,
  type WorkspaceStatus,
} from '../api/agent'
import { useT } from '../i18n'

interface SetupWizardProps {
  onReady: (status: WorkspaceStatus) => void
  onModelSaved?: (modelId: string, profileId: string) => void
}

type Step = 'loading' | 'model' | 'folder'

export function SetupWizard({ onReady, onModelSaved }: SetupWizardProps) {
  const t = useT()
  const [step, setStep] = useState<Step>('loading')
  const [presets, setPresets] = useState<ProviderPreset[]>([])
  const [presetId, setPresetId] = useState('')
  const [label, setLabel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [modelId, setModelId] = useState('')
  const [emptyProfileId, setEmptyProfileId] = useState<string | null>(null)
  const [browsePath, setBrowsePath] = useState('')
  const [parent, setParent] = useState<string | null>(null)
  const [dirs, setDirs] = useState<{ name: string; path: string }[]>([])
  const [folderName, setFolderName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchModelProfiles(), fetchProviderPresets()])
      .then(([profiles, presetList]) => {
        if (cancelled) return
        const usable = presetList.filter((item) => item.base_url && !item.inherit_base_url)
        setPresets(usable)
        const hasKey = profiles.profiles.some((item) => item.api_key_configured)
        if (hasKey) {
          setStep('folder')
          return
        }
        if (profiles.profiles.length === 1) {
          setEmptyProfileId(profiles.profiles[0].id)
        }
        setStep('model')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : t('workspace.loadFailed'))
        setStep('model')
      })
    return () => {
      cancelled = true
    }
  }, [t])

  useEffect(() => {
    if (step !== 'folder') return
    let cancelled = false
    browseWorkspace()
      .then((data) => {
        if (cancelled) return
        setBrowsePath(data.path)
        setParent(data.parent)
        setDirs(data.directories)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : t('workspace.browseFailed'))
      })
    return () => {
      cancelled = true
    }
  }, [step, t])

  const loadBrowse = async (path?: string) => {
    setBusy(true)
    setError(null)
    try {
      const data = await browseWorkspace(path)
      setBrowsePath(data.path)
      setParent(data.parent)
      setDirs(data.directories)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('workspace.browseFailed'))
    } finally {
      setBusy(false)
    }
  }

  const applyPreset = (id: string) => {
    setPresetId(id)
    const preset = presets.find((item) => item.id === id)
    if (!preset) return
    setLabel(preset.label)
    setBaseUrl(preset.base_url)
    setModelId(preset.model_id)
  }

  const saveModel = async () => {
    const url = baseUrl.trim()
    const key = apiKey.trim()
    const model = modelId.trim()
    if (!url || !key || !model) {
      setError(t('setup.needModel'))
      return
    }
    setBusy(true)
    setError(null)
    const body = {
      label: label.trim() || model,
      base_url: url,
      api_key: key,
      model_id: model,
      enabled: true,
    }
    try {
      let profileId = emptyProfileId
      if (profileId) {
        await updateModelProfile(profileId, body)
        await activateModelProfile(profileId)
      } else {
        const created = await createModelProfile({ ...body, activate: true })
        profileId = created.id
      }
      const sessions = await listSessions()
      if (sessions.length === 1) {
        await updateSessionModel(sessions[0].id, { model_id: model, profile_id: profileId })
      }
      onModelSaved?.(model, profileId)
      setStep('folder')
    } catch (err) {
      setError(err instanceof Error ? err.message : t('workspace.setFailed'))
    } finally {
      setBusy(false)
    }
  }

  const createFolder = async () => {
    const name = folderName.trim()
    if (!name || !browsePath) {
      setError(t('setup.needFolderName'))
      return
    }
    setBusy(true)
    setError(null)
    try {
      const created = await createWorkspaceFolder(browsePath, name)
      setFolderName('')
      await loadBrowse(created.path)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('workspace.setFailed'))
      setBusy(false)
    }
  }

  const useFolder = async () => {
    if (!browsePath) return
    setBusy(true)
    setError(null)
    try {
      const status = await setWorkspace(browsePath)
      onReady(status)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('workspace.setFailed'))
      setBusy(false)
    }
  }

  return (
    <div className="flex h-dvh w-full items-center justify-center bg-[var(--bg)] p-4">
      <div className="relative flex max-h-[85vh] w-full max-w-lg flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-xl">
        <div className="border-b border-[var(--border-subtle)] px-5 py-4">
          <h2 className="text-base font-semibold text-[var(--text-h)]">{t('setup.title')}</h2>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            {step === 'folder'
              ? t('setup.folderHint')
              : step === 'model'
                ? t('setup.modelHint')
                : t('setup.preparing')}
          </p>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {step === 'loading' && (
            <p className="text-sm text-[var(--text-muted)]">{t('setup.preparing')}</p>
          )}

          {step === 'model' && (
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs text-[var(--text-muted)]">
                {t('setup.preset')}
                <select
                  value={presetId}
                  onChange={(event) => applyPreset(event.target.value)}
                  className="rounded-lg border border-[var(--input-border)] bg-[var(--input-bg)] px-3 py-2 text-sm text-[var(--text-h)] outline-none focus:border-[var(--input-focus)]"
                >
                  <option value="">{t('setup.presetManual')}</option>
                  {presets.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-[var(--text-muted)]">
                {t('setup.name')}
                <input
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  className="rounded-lg border border-[var(--input-border)] bg-[var(--input-bg)] px-3 py-2 text-sm text-[var(--text-h)] outline-none focus:border-[var(--input-focus)]"
                />
              </label>
              <Field label="Base URL" value={baseUrl} onChange={setBaseUrl} />
              <Field label="API Key" value={apiKey} onChange={setApiKey} secret />
              <Field label="Model ID" value={modelId} onChange={setModelId} />
            </div>
          )}

          {step === 'folder' && (
            <div>
              <div className="mb-2 flex items-center justify-between text-xs text-[var(--text-muted)]">
                <span className="truncate font-mono">{browsePath || '…'}</span>
                <div className="flex gap-2">
                  {parent && (
                    <button
                      type="button"
                      disabled={busy}
                      className="hover:text-[var(--text-h)] disabled:opacity-40"
                      onClick={() => loadBrowse(parent)}
                    >
                      {t('workspace.parent')}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    className="hover:text-[var(--text-h)] disabled:opacity-40"
                    onClick={() => loadBrowse(browsePath)}
                  >
                    {t('workspace.refresh')}
                  </button>
                </div>
              </div>
              <div className="max-h-64 overflow-y-auto rounded-lg border border-[var(--border-subtle)]">
                {dirs.length === 0 ? (
                  <div className="px-3 py-6 text-center text-sm text-[var(--text-muted)]">
                    {t('workspace.noSubdirs')}
                  </div>
                ) : (
                  dirs.map((dir) => (
                    <button
                      key={dir.path}
                      type="button"
                      disabled={busy}
                      className="block w-full truncate border-b border-[var(--border-subtle)] px-3 py-2 text-left text-sm text-[var(--text-h)] last:border-b-0 hover:bg-[var(--surface-hover)] disabled:opacity-40"
                      onClick={() => loadBrowse(dir.path)}
                    >
                      {dir.name}/
                    </button>
                  ))
                )}
              </div>
              <div className="mt-3 flex gap-2">
                <input
                  value={folderName}
                  onChange={(event) => setFolderName(event.target.value)}
                  placeholder={t('setup.folderName')}
                  className="min-w-0 flex-1 rounded-lg border border-[var(--input-border)] bg-[var(--input-bg)] px-3 py-2 text-sm text-[var(--text-h)] outline-none focus:border-[var(--input-focus)]"
                />
                <button
                  type="button"
                  disabled={busy || !folderName.trim()}
                  onClick={createFolder}
                  className="shrink-0 rounded-lg border border-[var(--input-border)] px-3 py-2 text-sm text-[var(--text-h)] disabled:opacity-40"
                >
                  {t('setup.createFolder')}
                </button>
              </div>
            </div>
          )}

          {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
        </div>

        <div className="flex justify-end border-t border-[var(--border-subtle)] px-5 py-3">
          {step === 'model' && (
            <button
              type="button"
              disabled={busy}
              onClick={saveModel}
              className="rounded-lg bg-[var(--text-h)] px-4 py-2 text-sm font-medium text-[var(--bg)] disabled:opacity-40"
            >
              {t('setup.next')}
            </button>
          )}
          {step === 'folder' && (
            <button
              type="button"
              disabled={busy || !browsePath}
              onClick={useFolder}
              className="rounded-lg bg-[var(--text-h)] px-4 py-2 text-sm font-medium text-[var(--bg)] disabled:opacity-40"
            >
              {t('setup.useFolder')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  secret,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  secret?: boolean
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-[var(--text-muted)]">
      {label}
      <input
        type={secret ? 'password' : 'text'}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={secret ? 'off' : undefined}
        className="rounded-lg border border-[var(--input-border)] bg-[var(--input-bg)] px-3 py-2 text-sm text-[var(--text-h)] outline-none focus:border-[var(--input-focus)]"
      />
    </label>
  )
}
