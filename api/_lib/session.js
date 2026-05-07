import { SignJWT, jwtVerify } from 'jose'

const secret = new TextEncoder().encode(process.env.SESSION_SECRET)

export async function createToken() {
  return new SignJWT({ ok: true })
    .setProtectedHeader({ alg: 'HS256' })
    .setExpirationTime('7d')
    .sign(secret)
}

export function getToken(req) {
  const cookies = req.headers.cookie || ''
  const match = cookies.match(/st_session=([^;]+)/)
  return match?.[1] || null
}

export async function isAuthenticated(req) {
  const token = getToken(req)
  if (!token) return false
  try {
    await jwtVerify(token, secret)
    return true
  } catch {
    return false
  }
}

export function setCookie(res, token) {
  const secure = process.env.NODE_ENV === 'production' ? 'Secure; ' : ''
  res.setHeader('Set-Cookie', `st_session=${token}; HttpOnly; ${secure}SameSite=Lax; Max-Age=${7 * 24 * 60 * 60}; Path=/`)
}

export function clearCookie(res) {
  res.setHeader('Set-Cookie', 'st_session=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/')
}
