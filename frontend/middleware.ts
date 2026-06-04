export const config = {
  matcher: '/(.*)',
}

export default function middleware(request: Request) {
  const authHeader = request.headers.get('authorization')

  if (authHeader?.startsWith('Basic ')) {
    const encoded = authHeader.slice(6)
    const decoded = atob(encoded)
    const colonIndex = decoded.indexOf(':')
    const user = decoded.slice(0, colonIndex)
    const password = decoded.slice(colonIndex + 1)

    if (
      user === process.env.BASIC_AUTH_USER &&
      password === process.env.BASIC_AUTH_PASSWORD
    ) {
      return
    }
  }

  return new Response('Unauthorized', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="Logistics Dashboard"',
    },
  })
}
