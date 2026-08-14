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
});
