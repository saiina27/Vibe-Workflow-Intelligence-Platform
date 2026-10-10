import { useCallback, useEffect, useState } from 'react'

import {
  addTrackedRepo,
  getDevEvents,
  getGithubRepos,
  getTrackedRepos,
  removeTrackedRepo,
  syncDevEvents,
  type DevEvent,
  type TrackedRepo,
} from '../api/client'

import './ActivityPanel.css'

type Props = {
  workspaceId: number
  onClose: () => void
}

const REPO_PATTERN = /^[A-Za-z0-9_-][A-Za-z0-9_.-]*\/[A-Za-z0-9_-][A-Za-z0-9_.-]*$/

// The backend stores UTC times without a "Z"; add it so the
// browser converts them to the user's local time.
function parseUtc(value: string): Date {
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value)
  return new Date(hasZone ? value : `${value}Z`)
}

function formatDay(value: string): string {
  return parseUtc(value).toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function formatTime(value: string): string {
  return parseUtc(value).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function ActivityPanel({ workspaceId, onClose }: Props) {
  const [repos, setRepos] = useState<TrackedRepo[]>([])
  const [events, setEvents] = useState<DevEvent[]>([])
  const [githubRepos, setGithubRepos] = useState<string[]>([])

  const [manualRepo, setManualRepo] = useState('')
  const [repoFilter, setRepoFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [days, setDays] = useState(30)

  const [loadingEvents, setLoadingEvents] = useState(false)
  const [loadingGithub, setLoadingGithub] = useState(false)
  const [syncing, setSyncing] = useState(false)

  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const loadRepos = useCallback(async () => {
    try {
      setRepos(await getTrackedRepos(workspaceId))
    } catch (e) {
      setError(errorText(e, 'Failed to load repositories'))
    }
  }, [workspaceId])

  const loadEvents = useCallback(async () => {
    try {
      setLoadingEvents(true)
      setEvents(
        await getDevEvents(workspaceId, {
          repo: repoFilter,
          eventType: typeFilter,
          days,
        }),
      )
    } catch (e) {
      setError(errorText(e, 'Failed to load activity'))
    } finally {
      setLoadingEvents(false)
    }
  }, [workspaceId, repoFilter, typeFilter, days])

  useEffect(() => {
    loadRepos()
  }, [loadRepos])

  useEffect(() => {
    loadEvents()
  }, [loadEvents])

  async function handleAdd(name: string) {
    const fullName = name.trim()

    setError('')
    setMessage('')

    if (!REPO_PATTERN.test(fullName)) {
      setError('Repository must look like owner/repo.')
      return
    }

    try {
      await addTrackedRepo(workspaceId, fullName)
      setManualRepo('')
      await loadRepos()
      setMessage(`Added ${fullName}. Press Sync to import its activity.`)
    } catch (e) {
      setError(errorText(e, 'Failed to add repository'))
    }
  }

  async function handleRemove(repo: TrackedRepo) {
    const ok = window.confirm(
      `Stop tracking ${repo.full_name}? Its saved activity will be removed from Vibe (nothing changes on GitHub).`,
    )

    if (!ok) return

    try {
      setError('')
      await removeTrackedRepo(workspaceId, repo.id)
      if (repoFilter === repo.full_name) setRepoFilter('')
      await loadRepos()
      await loadEvents()
    } catch (e) {
      setError(errorText(e, 'Failed to remove repository'))
    }
  }

  async function handleLoadGithub() {
    try {
      setLoadingGithub(true)
      setError('')
      const data = await getGithubRepos(workspaceId)
      setGithubRepos(data.repos)

      if (!data.repos.length) {
        setMessage('No repositories found. Type owner/repo below.')
      }
    } catch (e) {
      setError(errorText(e, 'Failed to load GitHub repositories'))
    } finally {
      setLoadingGithub(false)
    }
  }

  async function handleSync() {
    if (syncing) return

    try {
      setSyncing(true)
      setError('')
      setMessage('')

      const { results } = await syncDevEvents(workspaceId)

      const lines = results.map((r) =>
        r.error
          ? `${r.repo}: ${r.error}`
          : `${r.repo}: ${r.events ?? 0} events (${r.new ?? 0} new, ${r.updated ?? 0} updated)`,
      )

      setMessage(lines.join(' | '))
      await loadRepos()
      await loadEvents()
    } catch (e) {
      setError(errorText(e, 'Sync failed'))
    } finally {
      setSyncing(false)
    }
  }

  const groups: { day: string; items: DevEvent[] }[] = []

  for (const item of events) {
    const day = formatDay(item.occurred_at)
    const last = groups[groups.length - 1]

    if (last && last.day === day) {
      last.items.push(item)
    } else {
      groups.push({ day, items: [item] })
    }
  }

  const lastSynced = repos
    .map((r) => r.last_synced_at)
    .filter((v): v is string => Boolean(v))
    .sort()
    .pop()

  const trackedNames = new Set(repos.map((r) => r.full_name))

  return (
    <div className="activity-overlay" onClick={onClose}>
      <div
        className="activity-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="activity-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="activity-header">
          <h3 id="activity-title">Developer Activity</h3>
          <button
            type="button"
            className="activity-close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <p className="activity-help">
          Saved history of your tracked GitHub repositories. Vibe
          can answer questions like "what changed on 5 Oct?" from
          this. It is read-only: nothing is changed on GitHub.
        </p>

        <section className="activity-section">
          <h4>Repositories</h4>

          {repos.length === 0 && (
            <p className="activity-muted">
              No repository tracked yet.
            </p>
          )}

          <ul className="activity-repos">
            {repos.map((repo) => (
              <li key={repo.id}>
                <span>{repo.full_name}</span>
                <button
                  type="button"
                  className="activity-link-button"
                  onClick={() => handleRemove(repo)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>

          <div className="activity-row">
            <select
              className="activity-input"
              value=""
              onChange={(e) => {
                if (e.target.value) handleAdd(e.target.value)
              }}
              disabled={githubRepos.length === 0}
            >
              <option value="">
                {githubRepos.length
                  ? 'Add from your GitHub repositories…'
                  : 'Load your repositories first'}
              </option>
              {githubRepos
                .filter((name) => !trackedNames.has(name))
                .map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
            </select>

            <button
              type="button"
              className="activity-button secondary"
              onClick={handleLoadGithub}
              disabled={loadingGithub}
            >
              {loadingGithub ? 'Loading…' : 'Load my repos'}
            </button>
          </div>

          <div className="activity-row">
            <input
              className="activity-input"
              value={manualRepo}
              placeholder="or type owner/repo"
              onChange={(e) => setManualRepo(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAdd(manualRepo)
              }}
            />
            <button
              type="button"
              className="activity-button secondary"
              onClick={() => handleAdd(manualRepo)}
              disabled={!manualRepo.trim()}
            >
              Add
            </button>
          </div>
        </section>

        <section className="activity-section">
          <div className="activity-row activity-sync-row">
            <button
              type="button"
              className="activity-button"
              onClick={handleSync}
              disabled={syncing || repos.length === 0}
            >
              {syncing ? 'Syncing…' : 'Sync now'}
            </button>
            <span className="activity-muted">
              {lastSynced
                ? `Last synced ${formatDay(lastSynced)} ${formatTime(lastSynced)}`
                : 'Not synced yet'}
            </span>
          </div>
          <p className="activity-muted">
            Tip: avoid syncing while a chat answer is still being
            generated.
          </p>
        </section>

        {message && <p className="activity-message">{message}</p>}
        {error && <p className="activity-error">{error}</p>}

        <section className="activity-section">
          <div className="activity-row activity-filters">
            <select
              className="activity-input"
              value={repoFilter}
              onChange={(e) => setRepoFilter(e.target.value)}
            >
              <option value="">All repositories</option>
              {repos.map((r) => (
                <option key={r.id} value={r.full_name}>
                  {r.full_name}
                </option>
              ))}
            </select>

            <select
              className="activity-input"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="">Commits and PRs</option>
              <option value="commit">Commits</option>
              <option value="pull_request">Pull requests</option>
            </select>

            <select
              className="activity-input"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last year</option>
            </select>
          </div>

          {loadingEvents && (
            <p className="activity-muted">Loading…</p>
          )}

          {!loadingEvents && events.length === 0 && (
            <p className="activity-muted">
              No activity in this period. Add a repository and
              press Sync.
            </p>
          )}

          <div className="activity-events">
            {groups.map((group) => (
              <div key={group.day} className="activity-day">
                <h5>{group.day}</h5>

                <ul>
                  {group.items.map((item) => (
                    <li key={item.id}>
                      <span
                        className={`activity-badge ${item.event_type}`}
                      >
                        {item.event_type === 'commit'
                          ? 'Commit'
                          : `PR${item.detail ? ` · ${item.detail}` : ''}`}
                      </span>

                      <div className="activity-event-body">
                        {item.url ? (
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {item.title}
                          </a>
                        ) : (
                          <span>{item.title}</span>
                        )}
                        <small>
                          {item.author ?? 'unknown'} ·{' '}
                          {formatTime(item.occurred_at)} ·{' '}
                          {item.repo}
                        </small>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

export default ActivityPanel
