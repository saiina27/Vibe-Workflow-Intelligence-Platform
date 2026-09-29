import { useEffect, useRef, useState } from 'react'
import './App.css'

import Login from './components/Login'
import Signup from './components/Signup'

import {
  archiveChat,
  createChat,
  deleteChat,
  getChats,
  connectGitHub,
  connectSlack,
  getCurrentUser,
  getGitHubStatus,
  getSlackStatus,
  getMessages,
  getWorkspaces,
  createWorkspace,
  renameChat,
  restoreChat,
  streamMessage,
  uploadKnowledgeDocument,
  getMemories,
  updateMemory,
  deleteMemory,
} from './api/client'

import type {
  Memory,
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

  const [githubConnected, setGithubConnected] =
    useState(false)

  const [slackConnected, setSlackConnected] =
    useState(false)

  const [workspace, setWorkspace] =
    useState<Workspace | null>(null)

  const [workspaces, setWorkspaces] =
    useState<Workspace[]>([])

  const [workspacesLoaded, setWorkspacesLoaded] =
    useState(false)

  const [workspaceMenuOpen, setWorkspaceMenuOpen] =
    useState(false)

  const [creatingWorkspace, setCreatingWorkspace] =
    useState(false)

  const [newWorkspaceName, setNewWorkspaceName] =
    useState('')

  const [workspaceBusy, setWorkspaceBusy] =
    useState(false)

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

  const [uploadStatus, setUploadStatus] =
    useState('')

  const fileInputRef =
    useRef<HTMLInputElement | null>(null)

  const [isListening, setIsListening] =
    useState(false)

  const recognitionRef =
    useRef<any>(null)

  const [memoryPanelOpen, setMemoryPanelOpen] =
    useState(false)

  const [memories, setMemories] =
    useState<Memory[]>([])

  const [memoriesLoading, setMemoriesLoading] =
    useState(false)

  const [editingMemoryId, setEditingMemoryId] =
    useState<number | null>(null)

  const [editMemoryTitle, setEditMemoryTitle] =
    useState('')

  const [editMemoryContent, setEditMemoryContent] =
    useState('')

  const [memoryBusy, setMemoryBusy] =
    useState(false)

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

        const githubStatus =
          await getGitHubStatus()

        setGithubConnected(
          githubStatus.connected,
        )

        const slackStatus =
          await getSlackStatus()

        setSlackConnected(
          slackStatus.connected,
        )

        const loadedWorkspaces: Workspace[] =
          await getWorkspaces()

        setWorkspaces(loadedWorkspaces)
        setWorkspacesLoaded(true)

        if (!loadedWorkspaces.length) {
          setWorkspace(null)
          setChats([])
          setActiveChat(null)
          setMessages([])
          return
        }

        const savedId = Number(
          localStorage.getItem('workspace_id'),
        )

        const initialWorkspace =
          loadedWorkspaces.find(
            (item: Workspace) =>
              item.id === savedId,
          ) ?? loadedWorkspaces[0]

        await openWorkspace(initialWorkspace)
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

  async function handleGitHubConnect() {
    try {
      setError('')

      const response =
        await connectGitHub()

      window.location.href =
        response.authorization_url
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to connect GitHub',
      )
    }
  }

  async function handleSlackConnect() {
    try {
      setError('')

      const response =
        await connectSlack()

      window.location.href =
        response.authorization_url
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to connect Slack',
      )
    }
  }

  /* =========================
  WORKSPACES
  ========================= */

  async function openWorkspace(
    target: Workspace,
  ) {
    setWorkspace(target)

    try {
      localStorage.setItem(
        'workspace_id',
        String(target.id),
      )
    } catch {
      // storage unavailable: selection just won't persist
    }

    setToolActivities([])
    setUploadStatus('')
    setOpenMenuChatId(null)
    setRenamingChatId(null)
    setRenameTitle('')
    setActiveChat(null)
    setMessages([])

    const workspaceChats: Chat[] =
      await getChats(target.id)

    setChats(workspaceChats)

    const firstChat = workspaceChats.find(
      (chat) => chat.status !== 'archived',
    )

    if (firstChat) {
      setActiveChat(firstChat)
      setMessages(
        await getMessages(firstChat.id),
      )
    }
  }

  async function handleSwitchWorkspace(
    target: Workspace,
  ) {
    setWorkspaceMenuOpen(false)
    setCreatingWorkspace(false)

    if (target.id === workspace?.id) {
      return
    }

    try {
      setError('')
      await openWorkspace(target)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to switch workspace',
      )
    }
  }

  async function handleCreateWorkspace() {
    const name = newWorkspaceName.trim()

    if (!name) {
      setError('Workspace name cannot be empty.')
      return
    }

    try {
      setError('')
      setWorkspaceBusy(true)

      const created: Workspace =
        await createWorkspace(name)

      setWorkspaces((current) => [
        ...current,
        created,
      ])
      setWorkspacesLoaded(true)
      setNewWorkspaceName('')
      setCreatingWorkspace(false)
      setWorkspaceMenuOpen(false)

      await openWorkspace(created)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to create workspace',
      )
    } finally {
      setWorkspaceBusy(false)
    }
  }

  function renderCreateWorkspaceForm() {
    return (
      <div className="workspace-create-form">
        <input
          className="workspace-create-input"
          value={newWorkspaceName}
          onChange={(event) =>
            setNewWorkspaceName(
              event.target.value,
            )
          }
          placeholder="Workspace name"
          maxLength={100}
          autoFocus
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              handleCreateWorkspace()
            }

            if (event.key === 'Escape') {
              setCreatingWorkspace(false)
              setNewWorkspaceName('')
            }
          }}
        />

        <div className="workspace-create-actions">
          {workspaces.length > 0 && (
            <button
              type="button"
              onClick={() => {
                setCreatingWorkspace(false)
                setNewWorkspaceName('')
              }}
            >
              Cancel
            </button>
          )}

          <button
            type="button"
            onClick={handleCreateWorkspace}
            disabled={
              workspaceBusy ||
              !newWorkspaceName.trim()
            }
          >
            {workspaceBusy
              ? 'Creating...'
              : 'Create'}
          </button>
        </div>
      </div>
    )
  }

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

  function toggleVoiceInput() {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition

    if (!SpeechRecognition) {
      setError("Voice input is not supported in this browser.")
      return
    }

    if (isListening) {
      recognitionRef.current?.stop()
      setIsListening(false)
      return
    }

    const recognition = new SpeechRecognition()

    recognition.lang = "en-IN"
    recognition.interimResults = false
    recognition.continuous = false

    recognition.onstart = () => {
      setError("")
      setIsListening(true)
    }

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript

      setInput((currentInput) =>
        currentInput.trim()
          ? `${currentInput.trim()} ${transcript}`
          : transcript,
      )
    }

    recognition.onerror = () => {
      setIsListening(false)
      setError("Could not capture your voice. Please try again.")
    }

    recognition.onend = () => {
      setIsListening(false)
    }

    recognitionRef.current = recognition
    recognition.start()
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
  KNOWLEDGE UPLOAD
  ========================= */

  async function handleFileSelected(
    event: React.ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0]

    event.target.value = ''

    if (!file || !workspace) {
      return
    }

    try {
      setError('')
      setUploadStatus(`Uploading ${file.name}...`)

      await uploadKnowledgeDocument(
        workspace.id,
        file,
      )

      setUploadStatus(`✓ Indexed: ${file.name}`)
    } catch (err) {
      setUploadStatus('')
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to upload document',
      )
    }
  }

  /* =========================
  MEMORY MANAGEMENT
  ========================= */

  async function handleOpenMemoryPanel() {
    setMemoryPanelOpen(true)
    setEditingMemoryId(null)

    if (!workspace) {
      return
    }

    try {
      setError('')
      setMemoriesLoading(true)

      const loaded: Memory[] =
        await getMemories(workspace.id)

      setMemories(loaded)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to load memories',
      )
    } finally {
      setMemoriesLoading(false)
    }
  }

  function handleStartEditMemory(
    memory: Memory,
  ) {
    setEditingMemoryId(memory.id)
    setEditMemoryTitle(memory.title)
    setEditMemoryContent(memory.content)
  }

  function handleCancelEditMemory() {
    setEditingMemoryId(null)
    setEditMemoryTitle('')
    setEditMemoryContent('')
  }

  async function handleSaveMemory(
    memory: Memory,
  ) {
    if (!workspace) {
      return
    }

    try {
      setError('')
      setMemoryBusy(true)

      const updated: Memory =
        await updateMemory(
          workspace.id,
          memory.id,
          {
            title: editMemoryTitle.trim(),
            content: editMemoryContent.trim(),
          },
        )

      setMemories((current) =>
        current.map((item) =>
          item.id === memory.id
            ? updated
            : item,
        ),
      )

      setEditingMemoryId(null)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to update memory',
      )
    } finally {
      setMemoryBusy(false)
    }
  }

  async function handleDeleteMemory(
    memory: Memory,
  ) {
    if (!workspace) {
      return
    }

    const confirmed = window.confirm(
      `Delete memory "${memory.title}"?`,
    )

    if (!confirmed) {
      return
    }

    try {
      setError('')
      setMemoryBusy(true)

      await deleteMemory(
        workspace.id,
        memory.id,
      )

      setMemories((current) =>
        current.filter(
          (item) => item.id !== memory.id,
        ),
      )
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to delete memory',
      )
    } finally {
      setMemoryBusy(false)
    }
  }

  function renderMemoryPanel() {
    if (!memoryPanelOpen) {
      return null
    }

    return (
      <div className="memory-overlay">
        <div className="memory-backdrop"
          onClick={() =>
            setMemoryPanelOpen(false)
          }
        />

        <div className="memory-panel">
          <div className="memory-panel-header">
            <strong>Memory</strong>

            <button
              type="button"
              onClick={() =>
                setMemoryPanelOpen(false)
              }
              aria-label="Close memory panel"
            >
              ✕
            </button>
          </div>

          <div className="memory-panel-body">
            {memoriesLoading ? (
              <p>Loading...</p>
            ) : memories.length === 0 ? (
              <p className="memory-empty">
                No memories saved yet.
              </p>
            ) : (
              memories.map((memory) => (
                <div
                  key={memory.id}
                  className="memory-item"
                >
                  {editingMemoryId === memory.id ? (
                    <div className="memory-edit-form">
                      <input
                        className="memory-edit-title"
                        value={editMemoryTitle}
                        onChange={(event) =>
                          setEditMemoryTitle(
                            event.target.value,
                          )
                        }
                        maxLength={200}
                      />

                      <textarea
                        className="memory-edit-content"
                        value={editMemoryContent}
                        onChange={(event) =>
                          setEditMemoryContent(
                            event.target.value,
                          )
                        }
                        rows={3}
                      />

                      <div className="memory-edit-actions">
                        <button
                          type="button"
                          onClick={
                            handleCancelEditMemory
                          }
                        >
                          Cancel
                        </button>

                        <button
                          type="button"
                          disabled={
                            memoryBusy ||
                            !editMemoryTitle.trim()
                          }
                          onClick={() =>
                            handleSaveMemory(memory)
                          }
                        >
                          Save
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="memory-item-header">
                        <span className="memory-title">
                          {memory.title}
                        </span>

                        <span className="memory-type">
                          {memory.memory_type}
                        </span>
                      </div>

                      <p className="memory-content">
                        {memory.content}
                      </p>

                      <div className="memory-item-actions">
                        <button
                          type="button"
                          onClick={() =>
                            handleStartEditMemory(memory)
                          }
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          disabled={memoryBusy}
                          onClick={() =>
                            handleDeleteMemory(memory)
                          }
                        >
                          Delete
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    )
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
    setWorkspaces([])
    setWorkspacesLoaded(false)
    setWorkspaceMenuOpen(false)
    setCreatingWorkspace(false)
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

        <div className="workspace-switcher">
          <button
            type="button"
            className="workspace-button"
            onClick={() =>
              setWorkspaceMenuOpen(
                (open) => !open,
              )
            }
          >
            <span className="workspace-label">
              Workspace
            </span>
            <span className="workspace-name">
              {workspace
                ? workspace.name
                : 'No workspace'}
            </span>
            <span>▾</span>
          </button>

          {workspaceMenuOpen && (
            <div className="workspace-dropdown">
              {workspaces.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`workspace-option ${
                    workspace?.id === item.id
                      ? 'active'
                      : ''
                  }`}
                  onClick={() =>
                    handleSwitchWorkspace(item)
                  }
                >
                  {item.name}
                  {workspace?.id === item.id
                    ? ' ✓'
                    : ''}
                </button>
              ))}

              <div className="workspace-divider" />

              {creatingWorkspace ? (
                renderCreateWorkspaceForm()
              ) : (
                <button
                  type="button"
                  className="workspace-option workspace-create"
                  onClick={() =>
                    setCreatingWorkspace(true)
                  }
                >
                  + Create Workspace
                </button>
              )}
            </div>
          )}
        </div>

        <div className="topbar-integrations">
          <button
            className="integration-button"
            type="button"
            onClick={
              githubConnected
                ? undefined
                : handleGitHubConnect
            }
          >
            <svg
              className="integration-logo github-logo"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                fill="currentColor"
                d="M12 .5C5.65.5.5 5.65.5 12c0 5.09 3.3 9.41 7.88 10.94.58.1.79-.25.79-.56v-2.17c-3.21.7-3.89-1.54-3.89-1.54-.53-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.76 2.7 1.25 3.36.95.1-.74.4-1.25.73-1.54-2.56-.29-5.26-1.28-5.26-5.7 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.47.11-3.06 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.77.12 3.06.74.81 1.19 1.84 1.19 3.1 0 4.43-2.7 5.41-5.27 5.69.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z"
              />
            </svg>

            <span>
              {githubConnected ? 'GitHub · Connected' : 'GitHub'}
            </span>
          </button>

          <button
            className="integration-button"
            type="button"
            onClick={
              slackConnected
                ? undefined
                : handleSlackConnect
            }
          >
            <svg
              className="integration-logo slack-logo"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                fill="#36C5F0"
                d="M6.5 15.5A2.5 2.5 0 1 1 4 13h2.5v2.5Zm1.25 0A2.5 2.5 0 1 1 10.25 18v-2.5H7.75Z"
              />
              <path
                fill="#2EB67D"
                d="M8.5 6.5A2.5 2.5 0 1 1 11 4v2.5H8.5Zm0 1.25A2.5 2.5 0 1 1 6 10.25H8.5V7.75Z"
              />
              <path
                fill="#ECB22E"
                d="M17.5 8.5A2.5 2.5 0 1 1 20 11h-2.5V8.5Zm-1.25 0A2.5 2.5 0 1 1 13.75 6v2.5h2.5Z"
              />
              <path
                fill="#E01E5A"
                d="M15.5 17.5A2.5 2.5 0 1 1 13 20v-2.5h2.5Zm0-1.25A2.5 2.5 0 1 1 18 13.75h-2.5v2.5Z"
              />
            </svg>

            <span>
              {slackConnected
                ? 'Slack · Connected'
                : 'Slack'}
            </span>
          </button>
        </div>

        <button
          type="button"
          className="memory-open-button"
          onClick={handleOpenMemoryPanel}
        >
          🧠 Memory
        </button>

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
            disabled={!workspace}
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

          {!workspace ? (
            workspacesLoaded ? (
              <div className="welcome">
                <div className="welcome-title">
                  <h1>Create your first workspace</h1>
                </div>

                <p>
                  A workspace holds your chats,
                  memory and knowledge.
                </p>

                {renderCreateWorkspaceForm()}
              </div>
            ) : (
              <div className="welcome">
                <p>Loading...</p>
              </div>
            )
          ) : !activeChat ? (
            <div className="welcome">

              <div className="welcome-title">
                <h1>
                  Welcome to Vibe
                </h1>

                <svg
                  className="vibe-eye"
                  viewBox="0 0 64 40"
                  aria-hidden="true"
                >
                  <path
                    d="M4 20 C14 5, 50 5, 60 20 C50 35, 14 35, 4 20 Z"
                    fill="none"
                    stroke="#09090b"
                    strokeWidth="3.2"
                    strokeLinecap="round"
                  />

                  <path
                    className="vibe-lashes"
                    d="M17 9 L14 5 M23 7 L21 3 M30 6 L29 2"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                  <path
                    className="vibe-pupil"
                    d="M28 20 C28 14, 36 11, 40 15 C44 19, 42 27, 37 29 C32 31, 28 26, 28 20 Z"
                    fill="currentColor"
                  />
                  <circle
                    className="vibe-eye-highlight"
                    cx="36"
                    cy="19"
                    r="2.5"
                    fill="white"
                  />
                </svg>
              </div>

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

              {uploadStatus && (
                <p className="upload-status">
                  {uploadStatus}
                </p>
              )}

              <div className="message-composer">

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt,.docx"
                  style={{ display: 'none' }}
                  onChange={handleFileSelected}
                />

                <button
                  type="button"
                  className="attach-button"
                  title="Upload a document (.pdf, .txt, .docx)"
                  aria-label="Upload a document"
                  onClick={() =>
                    fileInputRef.current?.click()
                  }
                  disabled={loading}
                >
                  +
                </button>

                <button
                  type="button"
                  className={`voice-button ${isListening ? 'listening' : ''}`}
                  title={isListening ? 'Stop listening' : 'Voice input'}
                  aria-label={isListening ? 'Stop listening' : 'Voice input'}
                  onClick={toggleVoiceInput}
                  disabled={loading}
                >
                  {isListening ? '⏹' : '🎤'}
                </button>

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

      {renderMemoryPanel()}

    </div>
  )
}

export default App