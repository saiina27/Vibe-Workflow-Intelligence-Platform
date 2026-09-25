import { useState } from 'react'
import type { FormEvent } from 'react'
import { signup } from '../api/client'

interface SignupProps {
onSignup: () => void
}

function Signup({ onSignup }: SignupProps) {
const [fullName, setFullName] =
useState('')

const [email, setEmail] =
useState('')

const [password, setPassword] =
useState('')

const [confirmPassword, setConfirmPassword] =
useState('')

const [error, setError] =
useState('')

const [loading, setLoading] =
useState(false)

async function handleSubmit(
event: FormEvent<HTMLFormElement>,
) {
event.preventDefault()

setError('')

if (password !== confirmPassword) {
  setError(
    'Passwords do not match.',
  )
  return
}

setLoading(true)

try {
  await signup(
    fullName.trim(),
    email.trim(),
    password,
  )

  onSignup()
} catch (err) {
  setError(
    err instanceof Error
      ? err.message
      : 'Signup failed',
  )
} finally {
  setLoading(false)
}

}

return ( <main className="auth-page"> <div className="auth-card">

```
    <h1>Create your Vibe account</h1>

    <p className="auth-subtitle">
      Sign up to get started
    </p>

    <form onSubmit={handleSubmit}>

      <label htmlFor="full-name">
        Full name
      </label>

      <input
        id="full-name"
        type="text"
        value={fullName}
        onChange={(event) =>
          setFullName(
            event.target.value,
          )
        }
        placeholder="Your name"
        required
      />


      <label htmlFor="signup-email">
        Email
      </label>

      <input
        id="signup-email"
        type="email"
        value={email}
        onChange={(event) =>
          setEmail(
            event.target.value,
          )
        }
        placeholder="you@example.com"
        required
      />


      <label htmlFor="signup-password">
        Password
      </label>

      <input
        id="signup-password"
        type="password"
        value={password}
        onChange={(event) =>
          setPassword(
            event.target.value,
          )
        }
        placeholder="••••••••"
        required
      />


      <label htmlFor="confirm-password">
        Confirm password
      </label>

      <input
        id="confirm-password"
        type="password"
        value={confirmPassword}
        onChange={(event) =>
          setConfirmPassword(
            event.target.value,
          )
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
          ? 'Creating account...'
          : 'Create account'}
      </button>

    </form>


    <button
      type="button"
      className="auth-switch-button"
      onClick={onSignup}
    >
      Already have an account? Sign in
    </button>

  </div>
</main>

)
}

export default Signup
