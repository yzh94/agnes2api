import http from './http'

export interface DiscordAuthUrlResponse {
  authorize_url: string
}

export async function getDiscordAuthUrl(state: string): Promise<DiscordAuthUrlResponse> {
  return http.get('/discord/authorize', { params: { state } })
}
