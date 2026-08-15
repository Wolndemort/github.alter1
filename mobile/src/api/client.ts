export type AuthResponse = { access_token: string; token_type: string };
export type MeResponse = {
  id: number;
  name: string;
  subscription_expires_at: string | null;
};
export type ChatResponse = { reply: string; session_id: number; transcript?: string | null; audio_base64?: string; audio_filename?: string; audio_mime?: string; media_base64?: string; media_filename?: string; media_mime?: string; media_job_id?: string; artifact_id?: string };
export type ChatHistoryResponse = { session_id: number | null; messages: { role: string; content: string }[] };
export type AccountResponse = {
  id: number; name: string; email: string; telegram_linked: boolean;
  subscription_expires_at: string | null; auto_renew: boolean; owner?: boolean; payment_method_saved?: boolean; subscription_plan?: string; legal_accepted?: boolean; trial_active?: boolean; trial_days?: number; credit_balance?: number;
};
export type CreditPack = { id: string; name: string; price: string; credits: number };
export type MemorySection = { category: string; title: string; items: { label: string; value: string }[] };
export type MemoryAudit = { category: string; key: string; confirmed: boolean; first_seen?: string; last_seen?: string; replacements: number };
export type MemoryResponse = { sections: MemorySection[]; permanent?: boolean; description?: string; audit?: MemoryAudit[] };
export type MyDayItem = { kind: string; title: string; detail: string; at: string | null; priority: string; loop_index?: number };
export type MyDayResponse = { date: string; focus: MyDayItem[]; next_step: { title: string; prompt: string }; counts: { reminders: number; open_loops: number; goals: number }; memory_permanent: boolean };
export type MediaJob = { id: string; user_id?: number; kind: "image" | "video"; status: "queued" | "running" | "completed" | "failed" | "cancelled"; progress: number; media_type?: string; filename?: string; data_base64?: string; error?: string };
export type CapabilityResponse = { version: string; categories: Record<string, string[]>; text: string; reply: string };
export type SubscriptionResponse = { active: boolean; trial_active?: boolean; trial_days?: number; plan: string; plans: { id: string; name: string; price: string; credits: number }[]; credit_packs?: CreditPack[]; credit_balance?: number; price_rub: string; days: number; expires_at: string | null; auto_renew: boolean };
export type Reminder = { id: number; text: string; kind?: string; remind_at: string };
export type AlterNotification = { id: string; title: string; body: string; kind: string; route: string; data?: Record<string, unknown>; read: boolean; created_at: string | null };
export type LocationContext = { latitude: number; longitude: number; city?: string; region?: string; country?: string };
export type YouTubeResult = { title: string; url: string; channel?: string; thumbnail?: string };
export type CalendarEvent = { id?: string; summary: string; description?: string; location?: string; start: Record<string, string>; end: Record<string, string>; htmlLink?: string };

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

function readableErrorBody(_body: string, status: number): string {
  try {
    const payload = JSON.parse(_body);
    const detail = typeof payload?.detail === "string" ? payload.detail : typeof payload?.message === "string" ? payload.message : typeof payload?.error === "string" ? payload.error : "";
    if (detail) return detail;
  } catch { /* Fall back to stable client copy for non-JSON errors. */ }
  const messages: Record<number, string> = {
    400: "Проверь запрос и попробуй ещё раз.", 401: "Сессия закончилась. Войди в ALTER снова.",
    402: "Доступ приостановлен: trial или подписка закончились. Память, история и настройки сохранены.", 404: "Запрошенные данные не найдены.",
    409: "Запрос уже выполняется. Подожди результат.", 413: "Файл слишком большой. Выбери файл меньшего размера.",
    429: "AI-квота исчерпана. Память и история сохранены — пополни баланс или дождись обновления лимита.", 502: "Внешний сервис временно недоступен. Попробуй позже.",
    503: "Сервис временно недоступен. Попробуй ещё раз позже.",
  };
  return messages[status] || "Не удалось выполнить запрос. Попробуй ещё раз позже.";
}

function idempotencyKey(): string {
  const random = globalThis.crypto?.randomUUID?.();
  return random || `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

function withIdempotency(init: RequestInit): Record<string, string> {
  const headers = (init.headers || {}) as Record<string, string>;
  return init.method?.toUpperCase() === "POST" && !headers["Idempotency-Key"] && !headers["idempotency-key"]
    ? { "Idempotency-Key": idempotencyKey() }
    : {};
}

export class AlterApi {
  constructor(private readonly baseUrl: string) {}

  private async requestBlob(path: string, init: RequestInit = {}, token?: string): Promise<Blob> {
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: {
        ...(init.headers || {}),
        ...withIdempotency(init),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.blob();
  }

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
          ...withIdempotency(init),
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

  private async requestText(path: string, token?: string): Promise<string> {
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.text();
  }

  register(email: string, password: string) {
    return this.request<AuthResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, legal_accepted: true }),
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
  logout(token: string) {
    return this.request<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" }, token);
  }
  rotateToken(token: string) {
    return this.request<AuthResponse>("/api/v1/auth/rotate", { method: "POST" }, token);
  }

  sendMessage(token: string, message: string, location?: LocationContext | null, signal?: AbortSignal) {
    return this.request<ChatResponse>("/api/v1/chat/messages", {
      method: "POST", signal,
      body: JSON.stringify({ message, ...(location ? { location } : {}) }),
    }, token);
  }
  async sendMessageStream(token: string, message: string, location: LocationContext | null | undefined, onDelta: (text: string) => void, signal?: AbortSignal, onStatus?: (status: string) => void): Promise<ChatResponse> {
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/chat/stream`, {
      method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream", "Idempotency-Key": idempotencyKey(), Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message, ...(location ? { location } : {}) }), signal,
    });
    if (response.status === 404 || response.status === 405 || response.status === 409) return this.sendMessage(token, message, location, signal);
    let full = "";
    let completedReply = "";
    let completedAudio: Pick<ChatResponse, "audio_base64" | "audio_filename" | "audio_mime"> = {};
    let completedMedia: Pick<ChatResponse, "media_base64" | "media_filename" | "media_mime"> = {};
    let completedJobId: string | undefined;
    let completed = false;
    const consume = (raw: string) => {
      const events = raw.split(/\r?\n\r?\n/);
      for (const event of events) {
        const line = event.split(/\r?\n/).find((value) => value.startsWith("data: "));
        if (!line) continue;
        const payload = JSON.parse(line.slice(6));
        if (payload.type === "error") throw new ApiError(502, "Поток ответа прервался.");
        if (payload.type === "done") {
          completed = true;
          if (typeof payload.reply === "string") completedReply = payload.reply;
          if (typeof payload.audio_base64 === "string") completedAudio = { audio_base64: payload.audio_base64, audio_filename: payload.audio_filename, audio_mime: payload.audio_mime };
          if (typeof payload.media_base64 === "string") completedMedia = { media_base64: payload.media_base64, media_filename: payload.media_filename, media_mime: payload.media_mime };
          if (typeof payload.media_job_id === "string") completedJobId = payload.media_job_id;
        }
        if (payload.type === "status" && typeof payload.status === "string") onStatus?.(payload.status);
        if (payload.type === "delta" && typeof payload.text === "string") { full += payload.text; onDelta(full); }
      }
    };
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    try {
      if (!response.body) {
        // React Native/Expo can expose a successful fetch without ReadableStream.
        // Read the already completed SSE response; never retry the paid request.
        consume(await response.text());
      } else {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buffer += decoder.decode(chunk.value, { stream: true });
          const events = buffer.split(/\r?\n\r?\n/);
          buffer = events.pop() || "";
          consume(events.join("\n\n"));
        }
        buffer += decoder.decode();
        if (buffer.trim()) consume(buffer);
      }
    } catch (error) {
      // The server can finish successfully while mobile closes the socket
      // during the final SSE chunk. Keep the answer already received.
      if (completed || full.trim() || completedReply.trim()) return { reply: full || completedReply, session_id: 0, ...completedAudio, ...completedMedia, media_job_id: completedJobId };
      throw error;
    }
    return { reply: full || completedReply, session_id: 0, ...completedAudio, ...completedMedia, media_job_id: completedJobId };
  }
  newSession(token: string) { return this.request<{ ok: boolean }>("/api/v1/chat/new", { method: "POST" }, token); }
  history(token: string) { return this.request<ChatHistoryResponse>("/api/v1/chat/history", {}, token); }
  async downloadArtifact(token: string, artifactId: string) {
    return this.requestBlob(`/api/v1/artifacts/${encodeURIComponent(artifactId)}`, {}, token);
  }

  async sendMedia(token: string, message: string, uri: string | { uri: string; mediaType: "image" | "video" | "audio"; mimeType?: string; filename?: string }[], mediaType?: "image" | "video" | "audio", mimeType?: string, filename?: string) {
    const form = new FormData();
    form.append("message", message);
    const files = Array.isArray(uri) ? uri : [{ uri, mediaType: mediaType!, mimeType, filename }];
    files.forEach((file) => {
      const mime = file.mimeType || (file.mediaType === "image" ? "image/jpeg" : file.mediaType === "video" ? "video/mp4" : "audio/m4a");
      form.append("file", { uri: file.uri, type: mime, name: file.filename || `alter.${file.mediaType === "audio" ? "m4a" : file.mediaType === "image" ? "jpg" : "mp4"}` } as unknown as Blob);
    });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90_000);
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/chat/media`, {
        method: "POST", signal: controller.signal, headers: { Authorization: `Bearer ${token}`, "Idempotency-Key": idempotencyKey() }, body: form,
      });
    } catch (error) {
      throw new ApiError(0, (error as { name?: string })?.name === "AbortError" ? "Вложение обрабатывается слишком долго." : "Сетевая ошибка при отправке вложения.");
    } finally {
      clearTimeout(timeout);
    }
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.json() as Promise<ChatResponse>;
  }
  async sendDocument(token: string, prompt: string, uri: string, filename: string, mimeType?: string) {
    const form = new FormData();
    form.append("prompt", prompt);
    form.append("agent", "true");
    form.append("file", { uri, type: mimeType || "application/octet-stream", name: filename } as unknown as Blob);
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/chat/document`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.json() as Promise<ChatResponse & { document?: { filename: string; media_type: string; chars: number; pages?: number | null } }>;
  }
  async editDocument(token: string, uri: string, filename: string, instruction: string, mimeType?: string) {
    const form = new FormData(); form.append("instruction", instruction); form.append("file", { uri, type: mimeType || "application/octet-stream", name: filename } as unknown as Blob);
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/chat/document/edit`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return { blob: await response.blob(), filename: response.headers?.get("Content-Disposition") || filename };
  }
  async editArtifact(token: string, artifactId: string, instruction: string) {
    const form = new FormData(); form.append("artifact_id", artifactId); form.append("instruction", instruction);
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/chat/document/edit`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return { blob: await response.blob(), filename: response.headers?.get("Content-Disposition") || "alter-edited-document" };
  }
  async compareDocuments(token: string, beforeUri: string, beforeName: string, afterUri: string, afterName: string) {
    const form = new FormData(); form.append("before", { uri: beforeUri, type: "application/octet-stream", name: beforeName } as unknown as Blob); form.append("after", { uri: afterUri, type: "application/octet-stream", name: afterName } as unknown as Blob);
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/chat/document/compare`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.json() as Promise<{ changed: boolean; added: string[]; removed: string[]; change_count: number }>;
  }
  async audioAction(token: string, path: "process" | "isolate" | "speech-to-text" | "speech-to-speech", uri: string, prompt = "", filename = "alter-audio.m4a", voiceId?: string) {
    const form = new FormData(); if (prompt) form.append("prompt", prompt); form.append("file", { uri, type: "audio/m4a", name: filename } as unknown as Blob);
    const suffix = path === "speech-to-speech" && voiceId ? `?voice_id=${encodeURIComponent(voiceId)}` : "";
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/audio/${path}${suffix}`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.blob();
  }
  async generateMedia(token: string, message: string, uri: string | null, kind: "image" | "video", options: Record<string, unknown> = {}, artifactId?: string) {
    const form = new FormData();
    form.append("message", message);
    form.append("kind", kind);
    form.append("options", JSON.stringify(options));
    if (artifactId) form.append("artifact_id", artifactId);
    if (uri) {
      form.append("file", { uri, type: kind === "image" ? "image/jpeg" : "video/mp4", name: `alter-source.${kind === "image" ? "jpg" : "mp4"}` } as unknown as Blob);
    }
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/media/generate`, {
      method: "POST", headers: { Authorization: `Bearer ${token}`, "Idempotency-Key": idempotencyKey() }, body: form,
    });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.json() as Promise<{ media_type: string; filename: string; data_base64: string; artifact_id?: string }>;
  }
  mediaCapabilities(token: string) {
    return this.request<{ provider: string; models: Record<string, { id: string | null; mode: string; requires_source: boolean; options: Record<string, unknown> }> }>("/api/v1/media/capabilities", {}, token);
  }
  createMediaJob(token: string, kind: "image" | "video", prompt: string, options: Record<string, unknown> = {}) {
    return this.request<MediaJob>("/api/v1/media/jobs", { method: "POST", body: JSON.stringify({ kind, prompt, options }) }, token);
  }
  mediaJob(token: string, id: string) { return this.request<MediaJob>(`/api/v1/media/jobs/${encodeURIComponent(id)}`, {}, token); }
  cancelMediaJob(token: string, id: string) { return this.request<{ ok: boolean; status: string }>(`/api/v1/media/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }, token); }
  mediaHistory(token: string) { return this.request<{ items: MediaJob[] }>("/api/v1/media/history", {}, token); }

  account(token: string) { return this.request<AccountResponse>("/api/v1/account", {}, token); }
  capabilities(token: string) { return this.request<CapabilityResponse>("/api/v1/capabilities", {}, token); }
  faq(token: string) { return this.requestText("/api/v1/faq/text", token); }
  acceptLegal(token: string) { return this.request<{ ok: boolean; legal_accepted: boolean }>("/api/v1/legal/accept", { method: "POST" }, token); }
  memory(token: string) { return this.request<MemoryResponse>("/api/v1/memory", {}, token); }
  confirmMemory(token: string, category: string, key: string) { return this.request<{ ok: boolean }>(`/api/v1/memory/${encodeURIComponent(category)}/${encodeURIComponent(key)}/confirm`, { method: "POST" }, token); }
  myDay(token: string) { return this.request<MyDayResponse>("/api/v1/my-day", {}, token); }
  updateLoop(token: string, index: number, status: "active" | "done" | "snoozed") { return this.request<{ ok: boolean }>(`/api/v1/memory/open-loops/${index}`, { method: "PATCH", body: JSON.stringify({ status }) }, token); }
  forgetMemoryCategory(token: string, category: string) { return this.request<{ ok: boolean; deleted: boolean }>(`/api/v1/memory/${encodeURIComponent(category)}`, { method: "DELETE" }, token); }
  clearMemory(token: string) { return this.request<{ ok: boolean }>("/api/v1/memory", { method: "DELETE" }, token); }
  clearAllPersonalData(token: string) { return this.request<{ ok: boolean; deleted: string[] }>("/api/v1/account/personal-data", { method: "DELETE", body: JSON.stringify({ confirm: "DELETE" }) }, token); }
  clearContext(token: string) { return this.request<{ ok: boolean }>("/api/v1/context", { method: "DELETE" }, token); }
  usage(token: string) { return this.request<{ used: number; limit: number; remaining: number; credit_balance: number }>("/api/v1/usage", {}, token); }
  subscription(token: string) { return this.request<SubscriptionResponse>("/api/v1/subscription", {}, token); }
  setAutoRenew(token: string, enabled: boolean) { return this.request<{ auto_renew: boolean }>("/api/v1/subscription/auto-renew", { method: "PATCH", body: JSON.stringify({ enabled }) }, token); }
  removePaymentMethod(token: string) { return this.request<{ ok: boolean; auto_renew: boolean; payment_method_saved: boolean }>("/api/v1/subscription/payment-method", { method: "DELETE" }, token); }
  createPayment(token: string, plan: string = "personal") { return this.request<{ payment_url: string; price_rub: string; plan: string; days: number }>("/api/v1/subscription/create-payment", { method: "POST", body: JSON.stringify({ plan }) }, token); }
  creditPacks(token: string) { return this.request<{ packs: CreditPack[] }>("/api/v1/credits/packs", {}, token); }
  createCreditPackPayment(token: string, pack: string) { return this.request<{ payment_url: string }>("/api/v1/credits/packs/create-payment", { method: "POST", body: JSON.stringify({ pack }) }, token); }
  startTelegramLink(token: string) { return this.request<{ url: string }>("/api/v1/telegram/link", { method: "POST" }, token); }
  settings(token: string) { return this.request<{ settings: Record<string, unknown>; checkins_enabled: boolean }>("/api/v1/settings", {}, token); }
  updateSettings(token: string, settings: Record<string, unknown>) { return this.request<{ settings: Record<string, unknown>; checkins_enabled: boolean }>("/api/v1/settings", { method: "PATCH", body: JSON.stringify(settings) }, token); }
  actionLog(token: string) { return this.request<{ items: Array<Record<string, string>>; private_mode: boolean }>("/api/v1/action-log", {}, token); }
  scenarios(token: string) { return this.request<{ items: Array<{ id: string; title: string; prompt: string; mode: string }> }>("/api/v1/scenarios", {}, token); }
  startWorkflow(token: string, workflowId: string, goal: string) { return this.request<{ workflow: Record<string, unknown> }>("/api/v1/workflow/start", { method: "POST", body: JSON.stringify({ workflow_id: workflowId, goal }) }, token); }
  workflow(token: string) { return this.request<{ workflow: Record<string, unknown> | null }>("/api/v1/workflow", {}, token); }
  nextWorkflowStep(token: string, complete = false) { return this.request<{ workflow: Record<string, unknown> | null }>("/api/v1/workflow/next", { method: "POST", body: JSON.stringify({ complete }) }, token); }
  async voiceReply(token: string, text: string) {
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/api/v1/voice/reply`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey(), Authorization: `Bearer ${token}` }, body: JSON.stringify({ text }) });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.blob();
  }
  async soundEffect(token: string, prompt: string) {
    const response = await fetch(this.baseUrl.replace(/\/$/, "") + "/api/v1/audio/sound-effects", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + token }, body: JSON.stringify({ prompt }) });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody("", response.status));
    return response.blob();
  }
  async isolateAudio(token: string, uri: string) {
    const form = new FormData();
    form.append("file", { uri, type: "audio/m4a", name: "alter-audio.m4a" } as unknown as Blob);
    const response = await fetch(this.baseUrl.replace(/\/$/, "") + "/api/v1/audio/isolate", { method: "POST", headers: { Authorization: "Bearer " + token }, body: form });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody("", response.status));
    return response.blob();
  }
  async processAudio(token: string, prompt: string, uri?: string) {
    const form = new FormData();
    form.append("prompt", prompt);
    if (uri) form.append("file", { uri, type: "audio/m4a", name: "alter-audio.m4a" } as unknown as Blob);
    const response = await fetch(this.baseUrl.replace(/\/$/, "") + "/api/v1/audio/process", { method: "POST", headers: { Authorization: "Bearer " + token }, body: form });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.json() as Promise<ChatResponse>;
  }
  async speechToText(token: string, uri: string) {
    const form = new FormData();
    form.append("file", { uri, type: "audio/m4a", name: "alter-voice.m4a" } as unknown as Blob);
    const response = await fetch(this.baseUrl.replace(/\/$/, "") + "/api/v1/audio/speech-to-text", { method: "POST", headers: { Authorization: "Bearer " + token }, body: form });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.json() as Promise<{ text?: string; language_code?: string; words?: unknown[] }>;
  }
  async speechToSpeech(token: string, voiceId: string, uri: string) {
    const form = new FormData();
    form.append("file", { uri, type: "audio/m4a", name: "alter-voice.m4a" } as unknown as Blob);
    const response = await fetch(this.baseUrl.replace(/\/$/, "") + "/api/v1/audio/speech-to-speech?voice_id=" + encodeURIComponent(voiceId), { method: "POST", headers: { Authorization: "Bearer " + token }, body: form });
    if (!response.ok) throw new ApiError(response.status, readableErrorBody(await response.text(), response.status));
    return response.blob();
  }
  voices(token: string) { return this.request<{ voices?: unknown[] }>("/api/v1/audio/voices", {}, token); }
  models(token: string) { return this.request<{ models: unknown[] }>("/api/v1/audio/models", {}, token); }
  voiceGeneration(token: string, description: string) { return this.request<{ voice_id?: string; previews?: { audio_base_64?: string }[]; [key: string]: unknown }>("/api/v1/audio/voice-generation", { method: "POST", body: JSON.stringify({ description }) }, token); }
  setCheckins(token: string, enabled: boolean) { return this.request<{ checkins_enabled: boolean }>("/api/v1/checkins", { method: "POST", body: JSON.stringify({ enabled }) }, token); }
  registerPushToken(token: string, pushToken: string) { return this.request<{ ok: boolean }>("/api/v1/push-token", { method: "POST", body: JSON.stringify({ token: pushToken }) }, token); }
  notifications(token: string) { return this.request<{ unread: number; notifications: AlterNotification[] }>("/api/v1/notifications", {}, token); }
  markNotificationRead(token: string, id: string) { return this.request<{ ok: boolean }>(`/api/v1/notifications/${encodeURIComponent(id)}/read`, { method: "POST" }, token); }
  markAllNotificationsRead(token: string) { return this.request<{ ok: boolean }>("/api/v1/notifications/read-all", { method: "POST" }, token); }
  reminders(token: string) { return this.request<{ reminders: Reminder[] }>("/api/v1/reminders", {}, token); }
  createReminder(token: string, text: string, remindAt: string) { return this.request<Reminder>("/api/v1/reminders", { method: "POST", body: JSON.stringify({ text, remind_at: remindAt }) }, token); }
  deleteReminder(token: string, id: number) { return this.request<{ ok: boolean }>(`/api/v1/reminders/${id}`, { method: "DELETE" }, token); }
  calendarConnect(token: string) { return this.request<{ authorization_url: string }>("/api/v1/calendar/connect", {}, token); }
  calendarStatus(token: string) { return this.request<{ configured: boolean; connected: boolean }>("/api/v1/calendar/status", {}, token); }
  calendarEvents(token: string, params: { calendar_id?: string; time_min?: string; time_max?: string } = {}) {
    const query = new URLSearchParams(params as Record<string, string>).toString();
    return this.request<{ events: CalendarEvent[] }>(`/api/v1/calendar/events${query ? `?${query}` : ""}`, {}, token);
  }
  createCalendarEvent(token: string, event: CalendarEvent, calendarId = "primary") {
    return this.request<CalendarEvent>("/api/v1/calendar/events", { method: "POST", body: JSON.stringify({ calendar_id: calendarId, event }) }, token);
  }
  deleteCalendarEvent(token: string, eventId: string, calendarId = "primary") {
    return this.request<{ ok: boolean }>(`/api/v1/calendar/events/${encodeURIComponent(eventId)}?calendar_id=${encodeURIComponent(calendarId)}`, { method: "DELETE" }, token);
  }
  youtubeAudio(token: string, url: string) {
    return this.requestBlob("/api/v1/youtube/audio", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) }, token);
  }
  youtubeSearch(token: string, query: string) {
    return this.request<{ results: YouTubeResult[] }>("/api/v1/youtube/search", {
      method: "POST", body: JSON.stringify({ query }),
    }, token);
  }
}

export const api = new AlterApi(process.env.EXPO_PUBLIC_API_URL || "http://localhost:8080");
