export type AuthResponse = { access_token: string; token_type: string };
export type MeResponse = {
  id: number;
  name: string;
  subscription_expires_at: string | null;
};
export type ChatResponse = { reply: string; session_id: number };

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

export class AlterApi {
  constructor(private readonly baseUrl: string) {}

  private async request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers || {}),
      },
    });
    if (!response.ok) {
      const message = await response.text();
      throw new ApiError(response.status, message || "Request failed");
    }
    return response.json() as Promise<T>;
  }

  register(email: string, password: string) {
    return this.request<AuthResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }

  login(email: string, password: string) {
    return this.request<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }

  me(token: string) {
    return this.request<MeResponse>("/api/v1/auth/me", {}, token);
  }

  sendMessage(token: string, message: string) {
    return this.request<ChatResponse>("/api/v1/chat/messages", {
      method: "POST",
      body: JSON.stringify({ message }),
    }, token);
  }
}

export const api = new AlterApi(process.env.EXPO_PUBLIC_API_URL || "http://localhost:8080");
