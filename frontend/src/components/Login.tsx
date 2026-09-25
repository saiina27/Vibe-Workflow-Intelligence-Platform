
import { useState } from 'react'
import type { FormEvent } from 'react'
import { login } from '../api/client'

interface LoginProps {
  onLogin: (token: string) => void
  onSignup: () => void
}

function Login({ onLogin, onSignup }: LoginProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    setError('')
    setLoading(true)

    try {
      const data = await login(email, password)

      localStorage.setItem(
        'access_token',
        data.access_token,
      )

      onLogin(data.access_token)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Login failed',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <h1>Welcome to Vibe</h1>

        <p className="auth-subtitle">
          Sign in to continue
        </p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>

          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) =>
              setEmail(event.target.value)
            }
            placeholder="you@example.com"
            required
          />

          <label htmlFor="password">Password</label>

          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) =>
              setPassword(event.target.value)
            }
            placeholder="••••••••"
            required
          />

          {error && (
            <p className="auth-error">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
          >
            {loading
              ? 'Signing in...'
              : 'Sign in'}
          </button>
        </form>

        <button
          type="button"
          className="auth-switch-button"
          onClick={onSignup}
        >
          Don't have an account? Sign up
        </button>
      </div>
    </main>
  )
}

export default Login