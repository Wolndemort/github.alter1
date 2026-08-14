import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App, { MarkdownText, Message } from "./App";

describe("ALTER web shell", () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

  it("renders auth and lets the user switch to registration", () => {
    render(<App />);
    expect(screen.getByText("Твой контекст", { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByText("Создать новый аккаунт"));
    expect(screen.getByText("Создать аккаунт →")).toBeTruthy();
  });

  it("renders assistant markdown as premium text instead of raw markup", () => {
    const text = ["**Важная тема**", "1. Первый шаг", "2. Второй шаг"].join(String.fromCharCode(10));
    render(<MarkdownText text={text} />);
    expect(screen.getByText("Важная тема")).toBeTruthy();
    expect(screen.queryByText("**Важная тема**")).toBeNull();
    expect(screen.getByText("Первый шаг")).toBeTruthy();
  });

  it("exposes the mobile parity actions under assistant messages", () => {
    const listener = vi.fn();
    window.addEventListener("alter:message-action", listener);
    render(<Message item={{ id: "a1", role: "assistant", text: "Ответ", createdAt: 1 }} />);
    expect(screen.getByTitle("Повторить запрос")).toBeTruthy();
    expect(screen.getByTitle("Продолжить ответ")).toBeTruthy();
    expect(screen.getByTitle("Скопировать ответ")).toBeTruthy();
    expect(screen.getByTitle("Озвучить ответ")).toBeTruthy();
    fireEvent.click(screen.getByTitle("Полезно"));
    expect(listener).toHaveBeenCalled();
    window.removeEventListener("alter:message-action", listener);
  });
});
