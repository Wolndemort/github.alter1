import { AlterApi, ApiError } from "./client";

describe("AlterApi", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
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

  it("turns HTTP failures into ApiError", async () => {
    (fetch as jest.Mock).mockResolvedValue({ ok: false, status: 401, text: async () => "unauthorized" });
    await expect(new AlterApi("https://alter.example").me("bad"))
      .rejects.toEqual(new ApiError(401, "unauthorized"));
  });
});
