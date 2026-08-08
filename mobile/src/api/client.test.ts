import { AlterApi, ApiError } from "./client";

describe("AlterApi", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("sends legal acceptance to the backend", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ ok: true, legal_accepted: true }) });
    await new AlterApi("https://alter.example").acceptLegal("token");
    expect(fetch).toHaveBeenCalledWith("https://alter.example/api/v1/legal/accept", expect.objectContaining({ method: "POST", headers: expect.objectContaining({ Authorization: "Bearer token" }) }));
  });

  it("sends bearer token and JSON chat payload", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ reply: "ok", session_id: 3 }) });
    const result = await new AlterApi("https://alter.example/").sendMessage("token", "hello");
    expect(result.reply).toBe("ok");
    expect(fetch).toHaveBeenCalledWith("https://alter.example/api/v1/chat/messages", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ Authorization: "Bearer token" }),
      body: JSON.stringify({ message: "hello" }),
    }));
  });

  it("sends consented location only with the chat payload", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ reply: "weather", session_id: 3 }) });
    await new AlterApi("https://alter.example").sendMessage("token", "weather", { latitude: 55.75, longitude: 37.62, city: "Moscow", region: "Moscow" });
    expect(fetch).toHaveBeenCalledWith("https://alter.example/api/v1/chat/messages", expect.objectContaining({
      body: JSON.stringify({ message: "weather", location: { latitude: 55.75, longitude: 37.62, city: "Moscow", region: "Moscow" } }),
    }));
  });

  it("turns HTTP failures into ApiError", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: false, status: 401, text: async () => "unauthorized" });
    await expect(new AlterApi("https://alter.example").me("bad"))
      .rejects.toEqual(new ApiError(401, "unauthorized"));
  });

  it("verifies an email code", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ access_token: "verified-token", token_type: "bearer" }) });
    await expect(new AlterApi("https://alter.example").verifyEmail("user@example.com", "123456"))
      .resolves.toEqual({ access_token: "verified-token", token_type: "bearer" });
    expect(fetch).toHaveBeenCalledWith("https://alter.example/api/v1/auth/verify-email", expect.objectContaining({
      method: "POST", body: JSON.stringify({ email: "user@example.com", code: "123456" }),
    }));
  });

  it("resends a verification code", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    await new AlterApi("https://alter.example").resendVerification("user@example.com");
    expect(fetch).toHaveBeenCalledWith("https://alter.example/api/v1/auth/resend-verification", expect.objectContaining({
      method: "POST", body: JSON.stringify({ email: "user@example.com" }),
    }));
  });

  it("loads shared account data and starts Telegram linking", async () => {
    (fetch as jest.Mock)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 7, name: "Adam", email: "a@b.c", telegram_linked: false, subscription_expires_at: null, auto_renew: false }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ url: "https://t.me/alter_ai_bot?start=link_x" }) });
    await expect(new AlterApi("https://alter.example").account("token")).resolves.toMatchObject({ id: 7 });
    await expect(new AlterApi("https://alter.example").startTelegramLink("token")).resolves.toEqual({ url: "https://t.me/alter_ai_bot?start=link_x" });
    expect(fetch).toHaveBeenLastCalledWith("https://alter.example/api/v1/telegram/link", expect.objectContaining({
      method: "POST", headers: expect.objectContaining({ Authorization: "Bearer token" }),
    }));
  });

  it("sends media as multipart without overriding the boundary", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ reply: "seen", session_id: 4 }) });
    await new AlterApi("https://alter.example").sendMedia("token", "describe", "file:///photo.jpg", "image");
    expect(fetch).toHaveBeenCalledWith("https://alter.example/api/v1/chat/media", expect.objectContaining({
      method: "POST", headers: { Authorization: "Bearer token" }, body: expect.any(FormData),
    }));
  });

  it("uses the shared generation endpoint for image/video operations", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ media_type: "image/png", data_base64: "aA==" }) });
    await new AlterApi("https://alter.example").generateMedia("token", "make it cinematic", "file:///photo.jpg", "image");
    expect(fetch).toHaveBeenCalledWith("https://alter.example/api/v1/media/generate", expect.objectContaining({
      method: "POST", headers: { Authorization: "Bearer token" },
    }));
  });

  it("updates settings and manages reminders", async () => {
    (fetch as jest.Mock)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ settings: { voice_replies: true }, checkins_enabled: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 1, text: "call", remind_at: "2026-08-07T10:00:00+03:00" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) });
    await expect(new AlterApi("https://alter.example").updateSettings("token", { voice_replies: true })).resolves.toMatchObject({ checkins_enabled: true });
    await expect(new AlterApi("https://alter.example").createReminder("token", "call", "2026-08-07T10:00:00+03:00")).resolves.toMatchObject({ id: 1 });
    await expect(new AlterApi("https://alter.example").deleteReminder("token", 1)).resolves.toEqual({ ok: true });
  });

  it("searches YouTube through the protected API", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ results: [{ title: "Rain", url: "https://youtu.be/x" }] }) });
    await expect(new AlterApi("https://alter.example").youtubeSearch("token", "rain")).resolves.toMatchObject({ results: [{ title: "Rain" }] });
    expect(fetch).toHaveBeenCalledWith("https://alter.example/api/v1/youtube/search", expect.objectContaining({
      method: "POST", headers: expect.objectContaining({ Authorization: "Bearer token" }), body: JSON.stringify({ query: "rain" }),
    }));
  });
});
