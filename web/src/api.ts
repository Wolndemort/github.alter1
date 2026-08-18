import type { Account, Agent, AlterNotification, ApiErrorShape, AuthResponse, CreditPack, DiagnosticsQuality, MediaJob, MemoryResponse, MyDay, Reminder, Scenario, Subscription, Workflow } from "./types";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const idempotencyKey = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;

async function parseError(response: Response): Promise<never> {
  const body = await response.text();
  let message = "Не удалось выполнить запрос. Попробуй ещё раз.";
  try {
    const payload = JSON.parse(body) as ApiErrorShape;
    message = payload.detail || payload.message || payload.error || message;
  } catch { /* stable fallback for plain-text errors */ }
  if (response.status === 401) message = "Сессия закончилась. Войди в ALTER снова.";
  if (response.status === 402) message = "Доступ приостановлен: trial или подписка закончились. Память, история и настройки сохранены. Продолжить можно на alterai.ru.";
  if (response.status === 429) message = "AI-квота исчерпана. Память и история сохранены — пополни баланс или дождись обновления лимита.";
  throw new ApiError(response.status, message);
}

export class AlterApi {
  private readonly url = (path: string) => `${baseUrl}${path}`;
  private async request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
    const response = await fetch(this.url(path), {
      ...init,
      headers: {
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(init.method?.toUpperCase() === "POST" ? { "Idempotency-Key": idempotencyKey() } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers || {}),
      },
    });
    if (!response.ok) return parseError(response);
    return response.json() as Promise<T>;
  }
  private async text(path: string, token?: string) {
    const response = await fetch(this.url(path), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!response.ok) return parseError(response);
    return response.text();
  }
  private async blob(path: string, init: RequestInit = {}, token?: string) {
    const response = await fetch(this.url(path), { ...init, headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers || {}) } });
    if (!response.ok) return parseError(response);
    return response.blob();
  }
  register(email: string, password: string) { return this.request<{ verification_required: boolean; email: string }>("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password, legal_accepted: true }) }); }
  login(email: string, password: string) { return this.request<AuthResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); }
  verifyEmail(email: string, code: string) { return this.request<AuthResponse>("/api/v1/auth/verify-email", { method: "POST", body: JSON.stringify({ email, code }) }); }
  resendVerification(email: string) { return this.request<{ ok: boolean }>("/api/v1/auth/resend-verification", { method: "POST", body: JSON.stringify({ email }) }); }
  account(token: string) { return this.request<Account>("/api/v1/account", {}, token); }
  diagnosticsQuality(token: string) { return this.request<DiagnosticsQuality>("/api/v1/diagnostics/quality", {}, token); }
  diagnosticsLatency(token: string) { return this.request<{ latency: DiagnosticsQuality["latency"] }>("/api/v1/diagnostics/latency", {}, token); }
  logout(token: string) { return this.request<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" }, token); }
  rotateToken(token: string) { return this.request<AuthResponse>("/api/v1/auth/rotate", { method: "POST" }, token); }
  history(token: string) { return this.request<{ session_id: number | null; messages: { role: string; content: string }[] }>("/api/v1/chat/history", {}, token); }
  newSession(token: string) { return this.request<{ ok: boolean }>("/api/v1/chat/new", { method: "POST" }, token); }
  memory(token: string) { return this.request<MemoryResponse>("/api/v1/memory", {}, token); }
  myDay(token: string) { return this.request<MyDay>("/api/v1/my-day", {}, token); }
  usage(token: string) { return this.request<{ used: number; limit: number; remaining: number; credit_balance: number }>("/api/v1/usage", {}, token); }
  subscription(token: string) { return this.request<Subscription>("/api/v1/subscription", {}, token); }
  faq(token: string) { return this.text("/api/v1/faq/text", token); }
  capabilities(token: string) { return this.request<{ version: string; categories: Record<string, string[]>; text: string; reply: string }>("/api/v1/capabilities", {}, token); }
  settings(token: string) { return this.request<{ settings: Record<string, unknown>; checkins_enabled: boolean }>("/api/v1/settings", {}, token); }
  updateSettings(token: string, settings: Record<string, unknown>) { return this.request<{ settings: Record<string, unknown>; checkins_enabled: boolean }>("/api/v1/settings", { method: "PATCH", body: JSON.stringify(settings) }, token); }
  submitFeedback(token: string, payload: { rating: "positive" | "negative"; question?: string; answer: string; source?: string }) { return this.request<{ ok: boolean }>("/api/v1/feedback", { method: "POST", body: JSON.stringify(payload) }, token); }
  feedbackPoll(token: string) { return this.request<{ due: boolean; question: string }>("/api/v1/feedback/poll", {}, token); }
  reminders(token: string) { return this.request<{ reminders: Reminder[] }>("/api/v1/reminders", {}, token); }
  notifications(token: string) { return this.request<{ unread: number; notifications: AlterNotification[] }>("/api/v1/notifications", {}, token); }
  markNotificationRead(token: string, id: string) { return this.request<{ ok: boolean }>(`/api/v1/notifications/${encodeURIComponent(id)}/read`, { method: "POST" }, token); }
  markAllNotificationsRead(token: string) { return this.request<{ ok: boolean }>("/api/v1/notifications/read-all", { method: "POST" }, token); }
  createReminder(token: string, text: string, remind_at: string) { return this.request<Reminder>("/api/v1/reminders", { method: "POST", body: JSON.stringify({ text, remind_at }) }, token); }
  deleteReminder(token: string, id: number) { return this.request<{ ok: boolean }>(`/api/v1/reminders/${id}`, { method: "DELETE" }, token); }
  agent(token: string) { return this.request<{ agent: Agent }>("/api/v1/agent", {}, token); }
  startAgent(token: string, payload: Record<string, unknown>) { return this.request<{ agent: Agent }>("/api/v1/agent/start", { method: "POST", body: JSON.stringify(payload) }, token); }
  nextAgent(token: string) { return this.request<{ agent: Agent }>("/api/v1/agent/next", { method: "POST", body: JSON.stringify({}) }, token); }
  runAgent(token: string, max_steps = 8) { return this.request<{ agent: Agent }>("/api/v1/agent/run", { method: "POST", body: JSON.stringify({ max_steps }) }, token); }
  updateAgentTask(token: string, task_id: string, status: string, result?: string) { return this.request<{ agent: Agent }>("/api/v1/agent/task", { method: "POST", body: JSON.stringify({ task_id, status, result }) }, token); }
  replanAgent(token: string, tasks: unknown[], reason = "") { return this.request<{ agent: Agent }>("/api/v1/agent/replan", { method: "POST", body: JSON.stringify({ tasks, reason }) }, token); }
  workflow(token: string) { return this.request<{ workflow: Workflow }>("/api/v1/workflow", {}, token); }
  scenarios(token: string) { return this.request<{ items: Scenario[] }>("/api/v1/scenarios", {}, token); }
  startWorkflow(token: string, workflow_id: string, goal: string) { return this.request<{ workflow: Workflow }>("/api/v1/workflow/start", { method: "POST", body: JSON.stringify({ workflow_id, goal }) }, token); }
  nextWorkflow(token: string, complete = false) { return this.request<{ workflow: Workflow }>("/api/v1/workflow/next", { method: "POST", body: JSON.stringify({ complete }) }, token); }
  createPayment(token: string, plan = "personal", return_url = "https://alterai.ru/?payment=success&billing=1") { return this.request<{ payment_url: string; price_rub: string; plan: string; days: number }>("/api/v1/subscription/create-payment", { method: "POST", body: JSON.stringify({ plan, return_url }) }, token); }
  creditPacks(token: string) { return this.request<{ packs: CreditPack[] }>("/api/v1/credits/packs", {}, token); }
  createCreditPackPayment(token: string, pack: string, return_url = "https://alterai.ru/?payment=success&billing=1") { return this.request<{ payment_url: string }>("/api/v1/credits/packs/create-payment", { method: "POST", body: JSON.stringify({ pack, return_url }) }, token); }
  setAutoRenew(token: string, enabled: boolean) { return this.request<{ auto_renew: boolean }>("/api/v1/subscription/auto-renew", { method: "PATCH", body: JSON.stringify({ enabled }) }, token); }
  startTelegramLink(token: string) { return this.request<{ url: string }>("/api/v1/telegram/link", { method: "POST" }, token); }
  mediaHistory(token: string) { return this.request<{ items: MediaJob[] }>("/api/v1/media/history", {}, token); }
  async createMediaJob(token: string, kind: "image" | "video", prompt: string, options: Record<string, unknown> = {}) { const result = await this.request<{ job_id: string; status: MediaJob["status"]; progress: number }>("/api/v1/media/jobs", { method: "POST", body: JSON.stringify({ kind, prompt, options }) }, token); return { id: result.job_id, kind, status: result.status, progress: result.progress } as MediaJob; }
  mediaJob(token: string, id: string) { return this.request<MediaJob>(`/api/v1/media/jobs/${encodeURIComponent(id)}`, {}, token); }
  cancelMediaJob(token: string, id: string) { return this.request<{ ok: boolean; status: string }>(`/api/v1/media/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }, token); }
  confirmMemory(token: string, category: string, key: string) { return this.request<{ ok: boolean }>(`/api/v1/memory/${encodeURIComponent(category)}/${encodeURIComponent(key)}/confirm`, { method: "POST" }, token); }
  forgetMemory(token: string, category: string) { return this.request<{ ok: boolean }>(`/api/v1/memory/${encodeURIComponent(category)}`, { method: "DELETE" }, token); }
  clearMemory(token: string) { return this.request<{ ok: boolean }>("/api/v1/memory", { method: "DELETE" }, token); }
  clearContext(token: string) { return this.request<{ ok: boolean }>("/api/v1/context", { method: "DELETE" }, token); }
  clearPersonalData(token: string) { return this.request<{ ok: boolean; deleted: string[] }>("/api/v1/account/personal-data", { method: "DELETE", body: JSON.stringify({ confirm: "DELETE" }) }, token); }
  acceptLegal(token: string) { return this.request<{ ok: boolean; legal_accepted: boolean }>("/api/v1/legal/accept", { method: "POST" }, token); }
  actionLog(token: string) { return this.request<{ items: Record<string, string>[]; private_mode: boolean }>("/api/v1/action-log", {}, token); }
  setCheckins(token: string, enabled: boolean) { return this.request<{ checkins_enabled: boolean }>("/api/v1/checkins", { method: "POST", body: JSON.stringify({ enabled }) }, token); }
  updateLoop(token: string, index: number, status: "active" | "done" | "snoozed") { return this.request<{ ok: boolean }>(`/api/v1/memory/open-loops/${index}`, { method: "PATCH", body: JSON.stringify({ status }) }, token); }
  downloadArtifact(token: string, artifactId: string) { return this.blob(`/api/v1/artifacts/${encodeURIComponent(artifactId)}`, {}, token); }
  mediaCapabilities(token: string) { return this.request<{ provider: string; models: Record<string, { id: string | null; mode: string; requires_source: boolean; options: Record<string, unknown> }> }>("/api/v1/media/capabilities", {}, token); }
  async sendMessageStream(token: string, message: string, onDelta: (text: string) => void, signal?: AbortSignal) {
    const response = await fetch(this.url("/api/v1/chat/stream"), { method: "POST", signal, headers: { "Content-Type": "application/json", Accept: "text/event-stream", Authorization: `Bearer ${token}`, "Idempotency-Key": idempotencyKey() }, body: JSON.stringify({ message }) });
     if (!response.ok) return parseError(response);
     let reply = "";
     let completedAudio: { audio_base64?: string; audio_filename?: string; audio_mime?: string } = {};
     let completedMedia: { media_base64?: string; media_filename?: string; media_mime?: string; artifact_id?: string } = {};
    const consume = (raw: string) => raw.split(/\r?\n\r?\n/).forEach((event) => {
      const line = event.split(/\r?\n/).find((item) => item.startsWith("data: "));
      if (!line) return;
       const payload = JSON.parse(line.slice(6)) as { type?: string; text?: string; reply?: string; artifact_id?: string; audio_base64?: string; audio_filename?: string; audio_mime?: string; media_base64?: string; media_filename?: string; media_mime?: string };
       if (payload.type === "done" && typeof payload.audio_base64 === "string") completedAudio = { audio_base64: payload.audio_base64, audio_filename: payload.audio_filename, audio_mime: payload.audio_mime };
       if (payload.type === "done" && (typeof payload.media_base64 === "string" || typeof payload.media_mime === "string" || typeof payload.media_filename === "string")) completedMedia = { ...completedMedia, ...(typeof payload.media_base64 === "string" ? { media_base64: payload.media_base64 } : {}), media_filename: payload.media_filename, media_mime: payload.media_mime };
       if (payload.type === "done" && typeof payload.artifact_id === "string") completedMedia.artifact_id = payload.artifact_id;
      if (payload.type === "delta" && typeof payload.text === "string") { reply += payload.text; onDelta(reply); }
      if (payload.type === "done" && typeof payload.reply === "string" && !reply) { reply = payload.reply; onDelta(reply); }
    });
    if (!response.body) consume(await response.text());
    else { const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; while (true) { const part = await reader.read(); if (part.done) break; buffer += decoder.decode(part.value, { stream: true }); const events = buffer.split(/\r?\n\r?\n/); buffer = events.pop() || ""; consume(events.join("\n\n")); } buffer += decoder.decode(); if (buffer.trim()) consume(buffer); }
     return { reply, ...completedAudio, ...completedMedia };
  }
  async upload(token: string, path: string, fields: Record<string, string>, file: File, fileField = "file") {
    const form = new FormData(); Object.entries(fields).forEach(([key, value]) => form.append(key, value)); form.append(fileField, file);
    return this.request<{ reply: string; transcript?: string; artifact_id?: string; media_base64?: string; media_mime?: string; media_filename?: string; audio_base64?: string; audio_mime?: string; audio_filename?: string; document?: { filename: string; media_type: string } }>(path, { method: "POST", body: form }, token);
  }
  sendMedia(token: string, message: string, files: File | File[]) {
    const form = new FormData(); form.append("message", message);
    for (const file of (Array.isArray(files) ? files : [files])) form.append("file", file);
    return this.request<{ reply: string; transcript?: string; artifact_id?: string; media_base64?: string; media_mime?: string; media_filename?: string; audio_base64?: string; audio_mime?: string; audio_filename?: string }>("/api/v1/chat/media", { method: "POST", body: form }, token);
  }
  sendDocument(token: string, prompt: string, file: File, agent = false) { return this.upload(token, "/api/v1/chat/document", { prompt, agent: String(agent) }, file); }
  editDocument(token: string, file: File, instruction: string) { return this.upload(token, "/api/v1/chat/document/edit", { instruction }, file); }
  async editArtifact(token: string, artifactId: string, instruction: string) {
    const form = new FormData(); form.append("artifact_id", artifactId); form.append("instruction", instruction);
    const response = await fetch(this.url("/api/v1/chat/document/edit"), { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    if (!response.ok) return parseError(response);
    return { blob: await response.blob(), artifactId: response.headers.get("X-ALTER-Artifact-ID") || "", filename: response.headers.get("Content-Disposition") || "alter-edited-document" };
  }
  async editDocumentFile(token: string, file: File, instruction: string) {
    const form = new FormData(); form.append("instruction", instruction); form.append("file", file);
    const response = await fetch(this.url("/api/v1/chat/document/edit"), { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    if (!response.ok) return parseError(response);
    return { blob: await response.blob(), artifactId: response.headers.get("X-ALTER-Artifact-ID") || "", filename: response.headers.get("Content-Disposition") || file.name };
  }
  async generateMedia(token: string, message: string, file: File | null, kind: "image" | "video", options: Record<string, unknown> = {}) {
    const form = new FormData(); form.append("message", message); form.append("kind", kind); form.append("options", JSON.stringify(options)); if (file) form.append("file", file);
    return this.request<{ media_type: string; filename: string; data_base64: string; artifact_id?: string }>("/api/v1/media/generate", { method: "POST", body: form }, token);
  }
  async voiceReply(token: string, text: string) { const blob = await this.blob("/api/v1/voice/reply", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }, token); const dataUrl = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onloadend = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(blob); }); return { audio_base64: dataUrl.split(",", 2)[1], audio_mime: blob.type || "audio/wav", audio_filename: "alter-voice.wav" }; }
  voiceGeneration(token: string, description: string) { return this.request<{ voice_id?: string; previews?: { audio_base_64?: string }[] }>("/api/v1/audio/voice-generation", { method: "POST", body: JSON.stringify({ description }) }, token); }
  audioAction(token: string, path: "process" | "isolate" | "speech-to-text" | "speech-to-speech", file: File, prompt = "", voiceId?: string) { const suffix = path === "speech-to-speech" && voiceId ? `?voice_id=${encodeURIComponent(voiceId)}` : ""; const form = new FormData(); if (prompt) form.append("prompt", prompt); form.append("file", file); return this.blob(`/api/v1/audio/${path}${suffix}`, { method: "POST", body: form }, token); }
  async transcribeAudio(token: string, file: File) { const form = new FormData(); form.append("file", file); return this.request<{ text?: string; transcript?: string }>("/api/v1/audio/speech-to-text", { method: "POST", body: form }, token); }
  audioVoices(token: string) { return this.request<{ voices?: unknown[] }>("/api/v1/audio/voices", {}, token); }
  audioModels(token: string) { return this.request<{ models: unknown[] }>("/api/v1/audio/models", {}, token); }
  youtubeSearch(token: string, query: string) { return this.request<{ results: { title: string; url: string; channel?: string; thumbnail?: string }[] }>("/api/v1/youtube/search", { method: "POST", body: JSON.stringify({ query }) }, token); }
  youtubeAudio(token: string, url: string) { return this.blob("/api/v1/youtube/audio", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey() }, body: JSON.stringify({ url }) }, token); }
  calendarStatus(token: string) { return this.request<{ configured: boolean; connected: boolean }>("/api/v1/calendar/status", {}, token); }
  calendarConnect(token: string) { return this.request<{ authorization_url: string }>("/api/v1/calendar/connect", {}, token); }
  calendarEvents(token: string, params: Record<string, string> = {}) { const query = new URLSearchParams(params).toString(); return this.request<{ events: unknown[] }>(`/api/v1/calendar/events${query ? `?${query}` : ""}`, {}, token); }
}

export const api = new AlterApi();
