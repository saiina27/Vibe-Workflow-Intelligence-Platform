const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  'http://localhost:8000'

async function authenticatedFetch(
  path: string,
  options: RequestInit = {},
) {
  const token =
    localStorage.getItem('access_token')

  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      ...options,
      headers: {
        ...options.headers,
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    },
  )

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => null)

    throw new Error(
      error?.detail || 'Request failed',
    )
  }

  return response.json()
}

/* =========================
AUTH
========================= */

export async function signup(
  fullName: string,
  email: string,
  password: string,
) {
  const response = await fetch(
    `${API_BASE_URL}/users/`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        full_name: fullName,
        email,
        password,
      }),
    },
  )

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => null)

    throw new Error(
      error?.detail || 'Signup failed',
    )
  }

  return response.json()
}

export async function login(
  email: string,
  password: string,
) {
  const body = new URLSearchParams()

  body.append('username', email)
  body.append('password', password)

  const response = await fetch(
    `${API_BASE_URL}/auth/login`,
    {
      method: 'POST',
      headers: {
        'Content-Type':
          'application/x-www-form-urlencoded',
      },
      body,
    },
  )

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => null)

    throw new Error(
      error?.detail || 'Login failed',
    )
  }

  return response.json()
}

export async function getCurrentUser(
  token: string,
) {
  const response = await fetch(
    `${API_BASE_URL}/users/me`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  )

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => null)

    throw new Error(
      error?.detail ||
        'Failed to fetch current user',
    )
  }

  return response.json()
}

/* =========================
OAUTH / INTEGRATIONS
========================= */

export async function getGitHubStatus() {
  return authenticatedFetch(
    '/oauth/github/status',
  )
}

export async function connectGitHub() {
  return authenticatedFetch(
    '/oauth/github/connect',
  )
}

export async function getSlackStatus() {
  return authenticatedFetch(
    '/oauth/slack/status',
  )
}

export async function connectSlack() {
  return authenticatedFetch(
    '/oauth/slack/connect',
  )
}

/* =========================
WORKSPACES
========================= */

export async function getWorkspaces() {
  return authenticatedFetch(
    '/workspaces/',
  )
}

export async function createWorkspace(
  name: string,
) {
  return authenticatedFetch(
    '/workspaces/',
    {
      method: 'POST',
      body: JSON.stringify({
        name,
      }),
    },
  )
}

/* =========================
CHATS
========================= */

export async function getChats(
  workspaceId: number,
) {
  return authenticatedFetch(
    `/workspaces/${workspaceId}/chats`,
  )
}

export async function createChat(
  workspaceId: number,
  title = 'New Chat',
) {
  return authenticatedFetch(
    `/workspaces/${workspaceId}/chats`,
    {
      method: 'POST',
      body: JSON.stringify({
        title,
      }),
    },
  )
}

export async function renameChat(
  workspaceId: number,
  chatId: number,
  title: string,
) {
  return authenticatedFetch(
    `/workspaces/${workspaceId}/chats/${chatId}`,
    {
      method: 'PATCH',
      body: JSON.stringify({
        title,
      }),
    },
  )
}

export async function deleteChat(
  workspaceId: number,
  chatId: number,
) {
  return authenticatedFetch(
    `/workspaces/${workspaceId}/chats/${chatId}`,
    {
      method: 'DELETE',
    },
  )
}

export async function archiveChat(
  workspaceId: number,
  chatId: number,
) {
  return authenticatedFetch(
    `/workspaces/${workspaceId}/chats/${chatId}/archive`,
    {
      method: 'PATCH',
    },
  )
}

export async function restoreChat(
  workspaceId: number,
  chatId: number,
) {
  return authenticatedFetch(
    `/workspaces/${workspaceId}/chats/${chatId}/restore`,
    {
      method: 'PATCH',
    },
  )
}

/* =========================
MESSAGES
========================= */

export async function getMessages(
  chatId: number,
) {
  return authenticatedFetch(
    `/chats/${chatId}/messages`,
  )
}

export async function sendMessage(
  chatId: number,
  content: string,
) {
  return authenticatedFetch(
    `/chats/${chatId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({
        content,
      }),
    },
  )
}

/* =========================
STREAMING CHAT
========================= */

export type StreamEvent =
  | {
      type: 'content'
      text: string
    }
  | {
      type: 'tool_start'
      tool_call_id: string
      tool_name: string
    }
  | {
      type: 'tool_done'
      tool_call_id: string
      tool_name: string
      duration_ms?: number
    }
  | {
      type: 'tool_error'
      tool_call_id: string
      tool_name: string
      error: string
      duration_ms?: number
    }
  | {
      type: 'done'
    }
  | {
      type: 'error'
      message: string
    }

export async function streamMessage(
  workspaceId: number,
  chatId: number,
  content: string,
  onEvent: (event: StreamEvent) => void,
) {
  const token =
    localStorage.getItem('access_token')

  const response = await fetch(
    `${API_BASE_URL}/workspaces/${workspaceId}/chats/${chatId}/ask/stream`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        content,
      }),
    },
  )

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => null)

    throw new Error(
      error?.detail ||
        'Streaming request failed',
    )
  }

  if (!response.body) {
    throw new Error(
      'Streaming response body is not available',
    )
  }

  const reader =
    response.body.getReader()

  const decoder =
    new TextDecoder()

  let buffer = ''

  try {
    while (true) {
      const { value, done } =
        await reader.read()

      if (done) {
        break
      }

      buffer += decoder.decode(
        value,
        {
          stream: true,
        },
      )

      const events =
        buffer.split('\n\n')

      buffer =
        events.pop() || ''

      for (const event of events) {
        const lines =
          event.split('\n')

        for (const line of lines) {
          if (
            !line.startsWith('data: ')
          ) {
            continue
          }

          const json =
            line.slice(6)

          let parsed: StreamEvent

          try {
            parsed =
              JSON.parse(json)
          } catch {
            continue
          }

          if (parsed.type === 'content') {
            onEvent(parsed)
            continue
          }

          if (
            parsed.type === 'tool_start' ||
            parsed.type === 'tool_done' ||
            parsed.type === 'tool_error'
          ) {
            onEvent(parsed)
            continue
          }

          if (parsed.type === 'error') {
            onEvent(parsed)

            throw new Error(
              parsed.message,
            )
          }

          if (parsed.type === 'done') {
            onEvent(parsed)
            return
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

/* =========================
KNOWLEDGE UPLOAD
========================= */

export async function uploadKnowledgeDocument(
  workspaceId: number,
  file: File,
) {
  const token =
    localStorage.getItem('access_token')

  const formData = new FormData()

  formData.append(
    'title',
    file.name.replace(/\.[^/.]+$/, ''),
  )
  formData.append('file', file)

  // No Content-Type header here: the browser must set
  // the multipart boundary itself.
  const response = await fetch(
    `${API_BASE_URL}/workspaces/${workspaceId}/knowledge/upload`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    },
  )

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => null)

    throw new Error(
      error?.detail || 'Upload failed',
    )
  }

  return response.json()
}

/* =========================
MEMORY
========================= */

export interface Memory {
  id: number
  workspace_id: number
  memory_type: string
  title: string
  content: string
  importance: number
  confidence: number
  source: string
  status: string
  expires_at: string | null
  created_at: string
  updated_at: string
}

export async function getMemories(
  workspaceId: number,
) {
  return authenticatedFetch(
    `/workspaces/${workspaceId}/memories`,
  )
}

export async function updateMemory(
  workspaceId: number,
  memoryId: number,
  updates: {
    title?: string
    content?: string
    importance?: number
  },
) {
  return authenticatedFetch(
    `/workspaces/${workspaceId}/memories/${memoryId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(updates),
    },
  )
}

export async function deleteMemory(
  workspaceId: number,
  memoryId: number,
) {
  const token =
    localStorage.getItem('access_token')

  const response = await fetch(
    `${API_BASE_URL}/workspaces/${workspaceId}/memories/${memoryId}`,
    {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  )

  if (!response.ok && response.status !== 204) {
    const error = await response
      .json()
      .catch(() => null)

    throw new Error(
      error?.detail || 'Failed to delete memory',
    )
  }
}
