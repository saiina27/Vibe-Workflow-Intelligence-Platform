import { useEffect, useState } from 'react'
import './App.css'

import Login from './components/Login'
import Signup from './components/Signup'

import {
  archiveChat,
  createChat,
  deleteChat,
  getChats,
  getCurrentUser,
  getMessages,
  getWorkspaces,
  renameChat,
  restoreChat,
  streamMessage,
} from './api/client'

import type {
  StreamEvent,
} from './api/client'

import type {
  Chat,
  Message,
  Workspace,
} from './types/chat'

type ToolStatus =
  | 'running'
  | 'done'
  | 'error'

type ToolActivity = {
  tool_call_id: string
  tool_name: string
  status: ToolStatus
  duration_ms?: number
  error?: string
}

function App() {
  const [token, setToken] = useState(
    localStorage.getItem('access_token'),
  )

  const [showSignup, setShowSignup] =
    useState(false)

  const [workspace, setWorkspace] =
    useState<Workspace | null>(null)

  const [chats, setChats] =
    useState<Chat[]>([])

  const [activeChat, setActiveChat] =
    useState<Chat | null>(null)

  const [messages, setMessages] =
    useState<Message[]>([])

  const [input, setInput] =
    useState('')

  const [loading, setLoading] =
    useState(false)

  const [toolActivities, setToolActivities] =
    useState<ToolActivity[]>([])

  const [deletingChatId, setDeletingChatId] =
    useState<number | null>(null)

  const [archivingChatId, setArchivingChatId] =
    useState<number | null>(null)

  const [restoringChatId, setRestoringChatId] =
    useState<number | null>(null)

  const [openMenuChatId, setOpenMenuChatId] =
    useState<number | null>(null)

  const [renamingChatId, setRenamingChatId] =
    useState<number | null>(null)

  const [renameTitle, setRenameTitle] =
    useState('')

  const [error, setError] =
    useState('')

  /* =========================
  LOAD WORKSPACE + CHATS
  ========================= */

  useEffect(() => {
    if (!token) {
      return
    }

    const currentToken = token

    async function loadWorkspace() {
      try {
        setError('')

        await getCurrentUser(currentToken)

        const workspaces =
          await getWorkspaces()

        if (!workspaces.length) {
          setError('No workspace found.')
          return
        }

        const currentWorkspace =
          workspaces[0]

        setWorkspace(currentWorkspace)

        const workspaceChats =
          await getChats(
            currentWorkspace.id,
          )

        setChats(workspaceChats)

        if (workspaceChats.length > 0) {
          const firstChat =
            workspaceChats[0]

          setActiveChat(firstChat)

          const chatMessages =
            await getMessages(
              firstChat.id,
            )

          setMessages(chatMessages)
        } else {
          setActiveChat(null)
          setMessages([])
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to load Vibe',
        )
      }
    }

    loadWorkspace()
  }, [token])

  /* =========================
  AUTHENTICATION
  ========================= */

  if (!token) {
    if (showSignup) {
      return (
        <Signup
          onSignup={() =>
            setShowSignup(false)
          }
        />
      )
    }

    return (
      <Login
        onLogin={setToken}
        onSignup={() =>
          setShowSignup(true)
        }
      />
    )
  }

  /* =========================
  CREATE CHAT
  ========================= */

  async function handleNewChat() {
    if (!workspace) {
      return
    }

    try {
      setError('')
      setToolActivities([])

      const chat = await createChat(
        workspace.id,
        'New Chat',
      )

      setChats((current) => [
        chat,
        ...current,
      ])

      setActiveChat(chat)
      setMessages([])

      setOpenMenuChatId(null)
      setRenamingChatId(null)
      setRenameTitle('')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to create chat',
      )
    }
  }

  /* =========================
  SELECT CHAT
  ========================= */

  async function handleSelectChat(
    chat: Chat,
  ) {
    try {
      setError('')
      setToolActivities([])

      setActiveChat(chat)

      setOpenMenuChatId(null)

      setRenamingChatId(null)
      setRenameTitle('')

      const chatMessages =
        await getMessages(chat.id)

      setMessages(chatMessages)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to load messages',
      )
    }
  }

  /* =========================
  START RENAME
  ========================= */

  function handleStartRename(
    chat: Chat,
  ) {
    setRenameTitle(chat.title)
    setRenamingChatId(chat.id)
    setOpenMenuChatId(null)
    setError('')
  }

  /* =========================
  CANCEL RENAME
  ========================= */

  function handleCancelRename() {
    setRenamingChatId(null)
    setRenameTitle('')
  }

  /* =========================
  RENAME CHAT
  ========================= */

  async function handleRenameChat(
    chat: Chat,
  ) {
    if (!workspace) {
      return
    }

    const cleanedTitle =
      renameTitle.trim()

    if (!cleanedTitle) {
      setError(
        'Chat name cannot be empty.',
      )
      return
    }

    if (cleanedTitle.length > 200) {
      setError(
        'Chat name cannot exceed 200 characters.',
      )
      return
    }

    try {
      setError('')

      const updatedChat =
        await renameChat(
          workspace.id,
          chat.id,
          cleanedTitle,
        )

      setChats((currentChats) =>
        currentChats.map(
          (currentChat) =>
            currentChat.id === chat.id
              ? updatedChat
              : currentChat,
        ),
      )

      if (
        activeChat?.id === chat.id
      ) {
        setActiveChat(updatedChat)
      }

      setRenamingChatId(null)
      setRenameTitle('')
      setOpenMenuChatId(null)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to rename chat',
      )
    }
  }

  /* =========================
  ARCHIVE CHAT
  ========================= */

  async function handleArchiveChat(
    chat: Chat,
  ) {
    if (!workspace) {
      return
    }

    setOpenMenuChatId(null)

    try {
      setError('')
      setArchivingChatId(chat.id)

      const archivedChat =
        await archiveChat(
          workspace.id,
          chat.id,
        )

      setChats((currentChats) =>
        currentChats.map(
          (currentChat) =>
            currentChat.id === chat.id
              ? archivedChat
              : currentChat,
        ),
      )

      if (
        activeChat?.id === chat.id
      ) {
        const remainingActiveChats =
          chats.filter(
            (currentChat) =>
              currentChat.id !== chat.id &&
              currentChat.status !== 'archived',
          )

        if (
          remainingActiveChats.length > 0
        ) {
          const nextChat =
            remainingActiveChats[0]

          setActiveChat(nextChat)

          const nextMessages =
            await getMessages(
              nextChat.id,
            )

          setMessages(nextMessages)
        } else {
          setActiveChat(null)
          setMessages([])
        }
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to archive chat',
      )
    } finally {
      setArchivingChatId(null)
    }
  }

  /* =========================
  RESTORE CHAT
  ========================= */

  async function handleRestoreChat(
    chat: Chat,
  ) {
    if (!workspace) {
      return
    }

    setOpenMenuChatId(null)

    try {
      setError('')
      setRestoringChatId(chat.id)

      const restoredChat =
        await restoreChat(
          workspace.id,
          chat.id,
        )

      setChats((currentChats) =>
        currentChats.map(
          (currentChat) =>
            currentChat.id === chat.id
              ? restoredChat
              : currentChat,
        ),
      )
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to restore chat',
      )
    } finally {
      setRestoringChatId(null)
    }
  }

  /* =========================
  DELETE CHAT
  ========================= */

  async function handleDeleteChat(
    chat: Chat,
  ) {
    if (!workspace) {
      return
    }

    setOpenMenuChatId(null)

    const confirmed =
      window.confirm(
        `Delete "${chat.title}"? This cannot be undone.`,
      )

    if (!confirmed) {
      return
    }

    try {
      setError('')
      setDeletingChatId(chat.id)

      await deleteChat(
        workspace.id,
        chat.id,
      )

      const remainingChats =
        chats.filter(
          (currentChat) =>
            currentChat.id !== chat.id,
        )

      setChats(remainingChats)

      if (
        activeChat?.id === chat.id
      ) {
        const remainingActiveChats =
          remainingChats.filter(
            (currentChat) =>
              currentChat.status !== 'archived',
          )

        if (
          remainingActiveChats.length > 0
        ) {
          const nextChat =
            remainingActiveChats[0]

          setActiveChat(nextChat)

          const nextMessages =
            await getMessages(
              nextChat.id,
            )

          setMessages(nextMessages)
        } else {
          setActiveChat(null)
          setMessages([])
        }
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to delete chat',
      )
    } finally {
      setDeletingChatId(null)
    }
  }

  /* =========================
  HANDLE TOOL EVENTS
  ========================= */

  function handleToolEvent(
    event: StreamEvent,
  ) {
    if (
      event.type ===
      'tool_start'
    ) {
      setToolActivities(
        (currentActivities) => [
          ...currentActivities,
          {
            tool_call_id:
              event.tool_call_id,
            tool_name:
              event.tool_name,
            status: 'running',
          },
        ],
      )

      return
    }

    if (
      event.type ===
      'tool_done'
    ) {
      setToolActivities(
        (currentActivities) =>
          currentActivities.map(
            (activity) =>
              activity.tool_call_id ===
              event.tool_call_id
                ? {
                    ...activity,
                    status: 'done',
                    duration_ms:
                      event.duration_ms,
                  }
                : activity,
          ),
      )

      return
    }

    if (
      event.type ===
      'tool_error'
    ) {
      setToolActivities(
        (currentActivities) =>
          currentActivities.map(
            (activity) =>
              activity.tool_call_id ===
              event.tool_call_id
                ? {
                    ...activity,
                    status: 'error',
                    duration_ms:
                      event.duration_ms,
                    error: event.error,
                  }
                : activity,
          ),
      )
    }
  }

  /* =========================
  SEND MESSAGE — STREAMING
  ========================= */

  async function handleSendMessage() {
    if (
      !workspace ||
      !activeChat ||
      !input.trim() ||
      loading
    ) {
      return
    }

    const content =
      input.trim()

    const chatId =
      activeChat.id

    setInput('')
    setLoading(true)
    setError('')
    setToolActivities([])

    /*
     * Temporary IDs are used only for
     * optimistic UI while the stream
     * is running.
     */
    const temporaryUserId =
      Date.now()

    const temporaryAssistantId =
      temporaryUserId + 1

    const userMessage =
      {
        id: temporaryUserId,
        role: 'user',
        content,
      } as Message

    const assistantMessage =
      {
        id: temporaryAssistantId,
        role: 'assistant',
        content: '',
      } as Message

    /*
     * Show both messages immediately.
     */
    setMessages((currentMessages) => [
      ...currentMessages,
      userMessage,
      assistantMessage,
    ])

    try {
      await streamMessage(
        workspace.id,
        chatId,
        content,
        (event) => {
          if (
            event.type ===
            'content'
          ) {
            setMessages(
              (currentMessages) =>
                currentMessages.map(
                  (message) =>
                    message.id ===
                    temporaryAssistantId
                      ? {
                          ...message,
                          content:
                            message.content +
                            event.text,
                        }
                      : message,
                ),
            )

            return
          }

          if (
            event.type ===
              'tool_start' ||
            event.type ===
              'tool_done' ||
            event.type ===
              'tool_error'
          ) {
            handleToolEvent(event)

            return
          }
        },
      )

      /*
       * The backend has now finished
       * saving the assistant response.
       *
       * Reload messages so the temporary
       * IDs are replaced by real DB IDs.
       */
      const updatedMessages =
        await getMessages(chatId)

      setMessages(updatedMessages)
    } catch (err) {
      setMessages(
        (currentMessages) =>
          currentMessages.filter(
            (message) =>
              message.id !==
              temporaryAssistantId,
          ),
      )

      setError(
        err instanceof Error
          ? err.message
          : 'Failed to stream response',
      )
    } finally {
      setLoading(false)
    }
  }

  /* =========================
  LOGOUT
  ========================= */

  function handleLogout() {
    localStorage.removeItem(
      'access_token',
    )

    setToken(null)
    setShowSignup(false)
    setWorkspace(null)
    setChats([])
    setActiveChat(null)
    setMessages([])
    setInput('')
    setError('')
    setToolActivities([])

    setOpenMenuChatId(null)
    setRenamingChatId(null)
    setRenameTitle('')
  }

  /* =========================
  DERIVED CHAT LISTS
  ========================= */

  const activeChats =
    chats.filter(
      (chat) =>
        chat.status !== 'archived',
    )

  const archivedChats =
    chats.filter(
      (chat) =>
        chat.status === 'archived',
    )

  /* =========================
  CHAT MENU
  ========================= */

  function renderChatItem(
    chat: Chat,
  ) {
    const isDeleting =
      deletingChatId === chat.id

    const isArchiving =
      archivingChatId === chat.id

    const isRestoring =
      restoringChatId === chat.id

    const isBusy =
      isDeleting ||
      isArchiving ||
      isRestoring

    return (
      <div
        key={chat.id}
        className="chat-item-wrapper"
      >
        {renamingChatId ===
        chat.id ? (
          <div
            className="chat-rename-form"
            onClick={(event) =>
              event.stopPropagation()
            }
          >
            <input
              className="chat-rename-input"
              value={renameTitle}
              onChange={(event) =>
                setRenameTitle(
                  event.target.value,
                )
              }
              autoFocus
              maxLength={200}
              onKeyDown={(event) => {
                if (
                  event.key ===
                  'Enter'
                ) {
                  event.preventDefault()

                  handleRenameChat(
                    chat,
                  )
                }

                if (
                  event.key ===
                  'Escape'
                ) {
                  event.preventDefault()

                  handleCancelRename()
                }
              }}
            />

            <div className="chat-rename-actions">
              <button
                type="button"
                onClick={
                  handleCancelRename
                }
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={() =>
                  handleRenameChat(
                    chat,
                  )
                }
                disabled={
                  !renameTitle.trim()
                }
              >
                Save
              </button>
            </div>
          </div>
        ) : (
          <button
            className={`chat-item ${
              activeChat?.id ===
              chat.id
                ? 'active'
                : ''
            }`}
            onClick={() =>
              handleSelectChat(chat)
            }
            disabled={isBusy}
          >
            <span className="chat-title">
              {chat.title}
            </span>
          </button>
        )}

        {renamingChatId !==
          chat.id && (
          <div className="chat-menu">
            <button
              className="chat-menu-button"
              onClick={(event) => {
                event.stopPropagation()

                if (isBusy) {
                  return
                }

                setOpenMenuChatId(
                  (current) =>
                    current ===
                    chat.id
                      ? null
                      : chat.id,
                )
              }}
              disabled={isBusy}
              title="Chat options"
              aria-label="Chat options"
            >
              ⋯
            </button>

            {openMenuChatId ===
              chat.id && (
              <div
                className="chat-menu-dropdown"
                onClick={(event) =>
                  event.stopPropagation()
                }
              >
                <button
                  className="rename-menu-item"
                  onClick={() =>
                    handleStartRename(
                      chat,
                    )
                  }
                >
                  Rename
                </button>

                {chat.status ===
                'archived' ? (
                  <button
                    className="restore-menu-item"
                    onClick={() =>
                      handleRestoreChat(
                        chat,
                      )
                    }
                  >
                    {isRestoring
                      ? 'Restoring...'
                      : 'Restore'}
                  </button>
                ) : (
                  <button
                    className="archive-menu-item"
                    onClick={() =>
                      handleArchiveChat(
                        chat,
                      )
                    }
                  >
                    {isArchiving
                      ? 'Archiving...'
                      : 'Archive'}
                  </button>
                )}

                <button
                  className="delete-menu-item"
                  onClick={() =>
                    handleDeleteChat(
                      chat,
                    )
                  }
                >
                  {isDeleting
                    ? 'Deleting...'
                    : 'Delete'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  /* =========================
  TOOL ACTIVITY PANEL
  ========================= */

  function renderToolActivityPanel() {
    if (
      !loading &&
      toolActivities.length === 0
    ) {
      return null
    }

    return (
      <div className="tool-activity-panel">
        <div className="tool-activity-header">
          <strong>
            {loading
              ? 'Vibe is working...'
              : 'Tool Activity'}
          </strong>
        </div>

        <div className="tool-activity-list">
          {toolActivities.map(
            (activity) => (
              <div
                key={
                  activity.tool_call_id
                }
                className="tool-activity-item"
              >
                <div className="tool-activity-name">
                  <span>
                    {getToolIcon(
                      activity.tool_name,
                    )}
                  </span>

                  <span>
                    {formatToolName(
                      activity.tool_name,
                    )}
                  </span>
                </div>

                <div
                  className={`tool-activity-status ${activity.status}`}
                >
                  {activity.status ===
                    'running' &&
                    'Running'}

                  {activity.status ===
                    'done' &&
                    `✓ Done${
                      activity.duration_ms
                        ? ` · ${Math.round(
                            activity.duration_ms,
                          )}ms`
                        : ''
                    }`}

                  {activity.status ===
                    'error' &&
                    '✕ Error'}
                </div>
              </div>
            ),
          )}
        </div>
      </div>
    )
  }

  function formatToolName(
    toolName: string,
  ) {
    const normalized =
      toolName.toLowerCase()

    if (
      normalized.includes('github')
    ) {
      return 'GitHub'
    }

    if (
      normalized.includes('slack')
    ) {
      return 'Slack'
    }

    if (
      normalized.includes('web')
    ) {
      return 'Web Search'
    }

    if (
      normalized.includes('knowledge')
    ) {
      return 'Knowledge'
    }

    if (
      normalized.includes('memory')
    ) {
      return 'Memory'
    }

    return toolName
  }

  function getToolIcon(
    toolName: string,
  ) {
    const normalized =
      toolName.toLowerCase()

    if (
      normalized.includes('github')
    ) {
      return '🐙'
    }

    if (
      normalized.includes('slack')
    ) {
      return '💬'
    }

    if (
      normalized.includes('web')
    ) {
      return '🌐'
    }

    if (
      normalized.includes('knowledge')
    ) {
      return '📚'
    }

    if (
      normalized.includes('memory')
    ) {
      return '🧠'
    }

    return '🔧'
  }

  /* =========================
  UI
  ========================= */

  return (
    <div className="app-shell">

      {/* =========================
          TOPBAR
      ========================= */}

      <header className="topbar">
        <div className="brand">
          Vibe
        </div>

        <button
          onClick={handleLogout}
        >
          Logout
        </button>
      </header>

      {/* =========================
          APP BODY
      ========================= */}

      <div className="app-body">

        {/* =========================
            SIDEBAR
        ========================= */}

        <aside className="sidebar">

          <button
            className="new-chat-button"
            onClick={handleNewChat}
          >
            + New Chat
          </button>

          <div className="sidebar-section">

            <p className="sidebar-label">
              Chats
            </p>

            {activeChats.length ===
            0 ? (
              <p className="empty-chats">
                No conversations yet
              </p>
            ) : (
              activeChats.map(
                renderChatItem,
              )
            )}

          </div>

          {archivedChats.length >
            0 && (
            <div className="sidebar-section archived-section">

              <p className="sidebar-label">
                Archived
              </p>

              {archivedChats.map(
                renderChatItem,
              )}

            </div>
          )}

        </aside>

        {/* =========================
            CHAT AREA
        ========================= */}

        <main className="chat-area">

          {!activeChat ? (
            <div className="welcome">

              <h1>
                Welcome to Vibe
              </h1>

              <p>
                Create a chat to start
                talking with your AI
                developer workspace.
              </p>

            </div>
          ) : (
            <>
              <div className="chat-header">

                <h2>
                  {activeChat.title}
                </h2>

              </div>

              {/* =========================
                  MESSAGES
              ========================= */}

              <div className="messages">

                {messages.length ===
                0 ? (
                  <div className="empty-messages">

                    <p>
                      Start a conversation with Vibe.
                    </p>

                  </div>
                ) : (
                  messages.map(
                    (message) => (
                      <div
                        key={message.id}
                        className={`message ${message.role}`}
                      >

                        <strong>
                          {message.role ===
                          'user'
                            ? 'You'
                            : 'Vibe'}
                        </strong>

                        <p>
                          {message.content}
                        </p>

                      </div>
                    ),
                  )
                )}

              

              </div>

              {/* =========================
                  TOOL ACTIVITY
              ========================= */}

              {renderToolActivityPanel()}

              {/* =========================
                  MESSAGE COMPOSER
              ========================= */}

              <div className="message-composer">

                <textarea
                  value={input}
                  onChange={(event) =>
                    setInput(
                      event.target.value,
                    )
                  }
                  placeholder="Message Vibe..."
                  rows={1}
                  disabled={loading}
                  onKeyDown={(event) => {
                    if (
                      event.key ===
                        'Enter' &&
                      !event.shiftKey
                    ) {
                      event.preventDefault()

                      handleSendMessage()
                    }
                  }}
                />

                <button
                  className="send-button"
                  onClick={
                    handleSendMessage
                  }
                  disabled={
                    loading ||
                    !input.trim()
                  }
                >
                  {loading
                    ? 'Streaming...'
                    : 'Send'}
                </button>

              </div>
            </>
          )}

          {/* =========================
              ERROR
          ========================= */}

          {error && (
            <p className="auth-error">
              {error}
            </p>
          )}

        </main>

      </div>

    </div>
  )
}

export default App