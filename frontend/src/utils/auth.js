import Cookies from 'js-cookie'

const LEGACY_TOKEN_KEY = 'Admin-Token'

function currentTokenKey() {
  if (typeof window === 'undefined') {
    return LEGACY_TOKEN_KEY
  }
  return `${LEGACY_TOKEN_KEY}:${window.location.host}`
}

export function getToken() {
  return Cookies.get(currentTokenKey())
}

export function setToken(token) {
  Cookies.remove(LEGACY_TOKEN_KEY)
  return Cookies.set(currentTokenKey(), token)
}

export function removeToken() {
  Cookies.remove(LEGACY_TOKEN_KEY)
  return Cookies.remove(currentTokenKey())
}
