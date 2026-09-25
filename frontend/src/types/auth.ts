export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: number
  full_name: string
  email: string
}