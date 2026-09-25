
export interface Workspace {
  id: number
  name: string
  description: string | null
}

export interface Chat {
  id: number
  title: string
  status: string
  topic: string | null
}

export interface Message {
  id: number
  content: string
  role: string
}

