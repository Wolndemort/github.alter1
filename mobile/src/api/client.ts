export type AuthResponse = { access_token: string; token_type: string };
export type MeResponse = {
  id: number;
  name: string;
  subscription_expires_at: string | null;
};
export type ChatResponse = { reply: string; session_id: number };
export type AccountResponse = {
  id: number; name: string; email: string; telegram_linked: boolean;
  subscription_expires_at: string | null; auto_renew: boolean; owner?: boolean; payment_method_saved?: boolean;
};
export type MemoryResponse = { memory: Record<string, unknown>; tech_stack: Record<string, unknown> };
export type SubscriptionResponse = { active: boolean; price_rub: string; days: number; expires_at: string | null; auto_renew: boolean };
export type Reminder = { id: number; text: string; kind?: string; remind_at: string };
export type LocationContext = { latitude: number; longitude: number; city?: string; region?: string; country?: string };

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

function readableErrorBody(body: string, status: number): string {
  const plain = body.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  return plain.length > 240 ? `${plain.slice(0, 237)}...` : plain || `Request failed (HTTP ${status})`;
}

export class AlterApi {
  constructor(private readonly baseUrl: string) {}

  private async request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 45_000);
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(init.headers || {}),
        },
      });
    } catch (error) {
      throw new ApiError(0, (error as { name?: string })?.name === "AbortError" ? "Сервер отвечает слишком долго. Попробуй ещё раз." : "Сетевая ошибка. Проверь интернет и повтори попытку.");
    } finally {
      clearTimeout(timeout);
    }
    if (!response.ok) {
      const message = await response.text();
      throw new ApiError(response.status, readableErrorBody(message, response.status));
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

  verifyEmail(email: string, code: string) {
    return this.request<AuthResponse>("/api/v1/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ email, code }),
    });
  }

  resendVerification(email: string) {
    return this.request<{ ok: boolean }>("/api/v1/auth/resend-verification", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }

  me(token: string) {
    return this.request<MeResponse>("/api/v1/auth/me", {}, token);
  }

  sendMessage(token: string, message: string, location?: LocationContext | null) {
    return this.request<ChatResponse>("/api/v1/chat/messages", {
      method: "POST",
      body: JSON.stringify({ message, ...(location ? { location } : {}) }),
    }, token);
  }

  async sendMedia(token: string, message: string, uri: string, mediaType: "image" | "video" | "audio") {
    const mime = mediaType === "image" ? "image/jpeg" : mediaType === "video" ? "video/mp4" : "audio/m4a";
    const form = new FormData();
    form.append("message", message);
    form.append("file", { uri, type: mime, name: `alter.${mediaType === "audio" ? "m4a" : mediaType === "image" ? "jpg" : "mp4"}` } as unknown as Blob);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90_000);
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/chat/media`, {
        method: "POST", signal: controller.signal, headers: { Authorization: `Bearer ${token}` }, body: form,
      });
    } catch (error) {
      throw new ApiError(0, (error as { name?: string })?.name === "AbortError" ? "Вложение обрабатывается слишком долго." : "Сетевая ошибка при отправке вложения.");
    } finally {
      clearTimeout(timeout);
    }
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.json() as Promise<ChatResponse>;
  }

  async generateMedia(token: string, message: string, uri: string | null, kind: "image" | "video") {
    const form = new FormData();
    form.append("message", message);
    form.append("kind", kind);
    if (uri) {
      form.append("file", { uri, type: kind === "image" ? "image/jpeg" : "video/mp4", name: `alter-source.${kind === "image" ? "jpg" : "mp4"}` } as unknown as Blob);
    }
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/media/generate`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
    });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.json() as Promise<{ media_type: string; filename: string; data_base64: string }>;
  }

  account(token: string) { return this.request<AccountResponse>("/api/v1/account", {}, token); }
  memory(token: string) { return this.request<MemoryResponse>("/api/v1/memory", {}, token); }
  subscription(token: string) { return this.request<SubscriptionResponse>("/api/v1/subscription", {}, token); }
  setAutoRenew(token: string, enabled: boolean) { return this.request<{ auto_renew: boolean }>("/api/v1/subscription/auto-renew", { method: "PATCH", body: JSON.stringify({ enabled }) }, token); }
  removePaymentMethod(token: string) { return this.request<{ ok: boolean; auto_renew: boolean; payment_method_saved: boolean }>("/api/v1/subscription/payment-method", { method: "DELETE" }, token); }
  createPayment(token: string) { return this.request<{ payment_url: string; price_rub: string; days: number }>("/api/v1/subscription/create-payment", { method: "POST" }, token); }
  startTelegramLink(token: string) { return this.request<{ url: string }>("/api/v1/telegram/link", { method: "POST" }, token); }
  settings(token: string) { return this.request<{ settings: Record<string, unknown>; checkins_enabled: boolean }>("/api/v1/settings", {}, token); }
  updateSettings(token: string, settings: Record<string, unknown>) { return this.request<{ settings: Record<string, unknown>; checkins_enabled: boolean }>("/api/v1/settings", { method: "PATCH", body: JSON.stringify(settings) }, token); }
  setCheckins(token: string, enabled: boolean) { return this.request<{ checkins_enabled: boolean }>("/api/v1/checkins", { method: "POST", body: JSON.stringify({ enabled }) }, token); }
  registerPushToken(token: string, pushToken: string) { return this.request<{ ok: boolean }>("/api/v1/push-token", { method: "POST", body: JSON.stringify({ token: pushToken }) }, token); }
  reminders(token: string) { return this.request<{ reminders: Reminder[] }>("/api/v1/reminders", {}, token); }
  createReminder(token: string, text: string, remindAt: string) { return this.request<Reminder>("/api/v1/reminders", { method: "POST", body: JSON.stringify({ text, remind_at: remindAt }) }, token); }
  deleteReminder(token: string, id: number) { return this.request<{ ok: boolean }>(`/api/v1/reminders/${id}`, { method: "DELETE" }, token); }
  youtubeSearch(token: string, query: string) { return this.request<{ results: { title: string; channel: string; url: string }[] }>("/api/v1/youtube/search", { method: "POST", body: JSON.stringify({ query }) }, token); }
  async youtubeAudio(token: string, url: string) {
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/youtube/audio`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ url }) });
    if (!response.ok) throw new ApiError(response.status, (await response.text()) || "Request failed");
    return response.blob();
  }
}

export const api = new AlterApi(process.env.EXPO_PUBLIC_API_URL || "http://localhost:8080");
