/** Require login for drama routes; redirect to /auth when missing token. */
import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { buildAuthRedirect } from '../../lib/authRedirect'

export default function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation()
  const token = localStorage.getItem('token')
  if (!token) {
    const returnPath = `${location.pathname}${location.search}${location.hash}`
    return <Navigate to={buildAuthRedirect(returnPath)} replace />
  }
  return children
}
