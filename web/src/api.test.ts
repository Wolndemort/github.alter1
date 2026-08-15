import { afterEach, describe, expect, it, vi } from "vitest";
import { AlterApi } from "./api";

describe("ALTER web API contract", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the shared bearer token and JSON payload for login", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ access_token: "token", token_type: "bearer" }), { status: 200 }));
    await new AlterApi().login("user@example.com", "password123");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/login", expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "user@example.com", password: "password123" }) }));
  });

  it("keeps SSE deltas in order and returns the completed reply", async () => {
    const stream = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode('data: {"type":"delta","text":"Привет"}\n\ndata: {"type":"delta","text":"ALTER"}\n\ndata: {"type":"done"}\n\n')); controller.close(); } });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }));
    const deltas: string[] = [];
    const result = await new AlterApi().sendMessageStream("token", "hello", (value) => deltas.push(value));
    expect(deltas).toEqual(["Привет", "ПриветALTER"]);
    expect(result.reply).toBe("ПриветALTER");
  });

  it("maps API authentication failures to a stable client error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "expired" }), { status: 401 }));
    await expect(new AlterApi().account("expired-token")).rejects.toMatchObject({ status: 401, message: "Сессия закончилась. Войди в ALTER снова." });
  });

  it("keeps owner diagnostics behind the shared bearer token", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ counters: {}, latency: {}, tool_success: 0, tool_empty: 0, tool_failures: 0, quality_warnings: 0, model_reliability: { success: 0, failures: 0, fallback_rate: 0 } }), { status: 200 }));
    await new AlterApi().diagnosticsQuality("owner-token");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/diagnostics/quality", expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer owner-token" }) }));
  });

  it("edits the latest document artifact without re-uploading the source file", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("edited", { status: 200, headers: { "Content-Type": "text/plain", "X-ALTER-Artifact-ID": "edited-2", "Content-Disposition": "attachment; filename=latest.txt" } }));
    const result = await new AlterApi().editArtifact("token", "source-1", "replace old => new");
    expect(result.artifactId).toBe("edited-2");
    // Node's fetch Blob and the jsdom Blob may come from different realms in CI.
    // Verify the response contract without relying on cross-realm instanceof.
    expect(result.blob).toMatchObject({ size: 6, type: "text/plain" });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/chat/document/edit", expect.objectContaining({ method: "POST", headers: { Authorization: "Bearer token" }, body: expect.any(FormData) }));
  });

  it("keeps audio transcription on the shared mobile-compatible route", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ text: "готово" }), { status: 200 }));
    const file = new File(["audio"], "voice.webm", { type: "audio/webm" });
    await expect(new AlterApi().transcribeAudio("token", file)).resolves.toEqual({ text: "готово" });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/audio/speech-to-text", expect.objectContaining({ method: "POST", body: expect.any(FormData) }));
  });
});
