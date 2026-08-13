import { AlterApi } from "./client";

describe("stream final events", () => {
  it("uses reply and audio from a done event without deltas", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: undefined,
      text: async () => 'data: {"type":"done","reply":"Голос создан","audio_base64":"bW...","audio_filename":"preview.mp3","audio_mime":"audio/mpeg"}\n\n',
    });
    await expect(new AlterApi("https://alter.example").sendMessageStream("token", "создай голос", null, jest.fn())).resolves.toMatchObject({ reply: "Голос создан", audio_filename: "preview.mp3" });
  });
});
