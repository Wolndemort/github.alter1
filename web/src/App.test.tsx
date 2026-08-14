import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App, { MarkdownText } from "./App";

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
});
