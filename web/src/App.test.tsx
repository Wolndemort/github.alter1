import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

describe("ALTER web shell", () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

  it("renders auth and lets the user switch to registration", () => {
    render(<App />);
    expect(screen.getByText("Твой контекст", { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByText("Создать новый аккаунт"));
    expect(screen.getByText("Создать аккаунт →")).toBeTruthy();
  });
});
