import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { AuthScreen, IntroScreen, VoiceButton, getExpiredChatIds } from "./App";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { api } from "./src/api/client";

jest.mock("expo-av", () => ({ Audio: { requestPermissionsAsync: jest.fn().mockResolvedValue({ granted: false }), setAudioModeAsync: jest.fn(), Sound: { createAsync: jest.fn() }, Recording: { createAsync: jest.fn() }, RecordingOptionsPresets: { HIGH_QUALITY: {} } } }));
jest.mock("expo-location", () => ({ PermissionStatus: { GRANTED: "granted", DENIED: "denied" }, requestForegroundPermissionsAsync: jest.fn(), requestBackgroundPermissionsAsync: jest.fn(), getCurrentPositionAsync: jest.fn(), reverseGeocodeAsync: jest.fn(), Accuracy: { Balanced: 3 } }));
jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn(), setItem: jest.fn(), removeItem: jest.fn(),
}));
jest.mock("@react-navigation/native", () => ({
  NavigationContainer: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock("@react-navigation/native-stack", () => {
  const React = require("react");
  return { createNativeStackNavigator: () => ({
    Navigator: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    Screen: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  }) };
});

describe("ALTER mobile critical screens", () => {
  beforeEach(() => jest.clearAllMocks());

  it("archives only messages older than the timeout, keeping the last three per role", () => {
    const now = 120_000;
    const items = [
      ...Array.from({ length: 4 }, (_, index) => ({ id: "u" + index, role: "user", text: "", createdAt: index * 10_000 })),
      ...Array.from({ length: 4 }, (_, index) => ({ id: "a" + index, role: "assistant", text: "", createdAt: index * 10_000 })),
    ];
    expect(getExpiredChatIds(items, now)).toEqual(["u0", "a0"]);
  });

  it("does not archive the last three messages even after the timeout", () => {
    const items = [
      { id: "u1", role: "user", text: "", createdAt: 0 },
      { id: "u2", role: "user", text: "", createdAt: 0 },
      { id: "u3", role: "user", text: "", createdAt: 0 },
    ];
    expect(getExpiredChatIds(items, 120_000)).toEqual([]);
  });

  it("finishes the offline intro scene smoothly", () => {
    jest.useFakeTimers();
    const onFinished = jest.fn();
    render(<IntroScreen onFinished={onFinished} />);
    act(() => { jest.advanceTimersByTime(2300); });
    expect(onFinished).toHaveBeenCalledTimes(1);
    jest.useRealTimers();
  });

  it("registers and moves the user to email verification", async () => {
    const register = jest.spyOn(api, "register").mockResolvedValue({ verification_required: true, email: "user@example.com" } as never);
    const { getByPlaceholderText, getByText } = render(<AuthScreen onAuthenticated={jest.fn()} />);
    fireEvent.changeText(getByPlaceholderText("Email"), "user@example.com");
    fireEvent.press(getByText("Создать аккаунт"));
    fireEvent.press(getByText(/Принимаю/));
    fireEvent.press(getByText("Создать аккаунт"));
    await waitFor(() => expect(register).toHaveBeenCalledWith("user@example.com", ""));
  });

  it("logs in and stores the access token", async () => {
    jest.spyOn(api, "login").mockResolvedValue({ access_token: "token", token_type: "bearer" });
    const authenticated = jest.fn();
    const { getByPlaceholderText, getByText } = render(<AuthScreen onAuthenticated={authenticated} />);
    fireEvent.changeText(getByPlaceholderText("Email"), "user@example.com");
    fireEvent.changeText(getByPlaceholderText("Пароль"), "password123");
    fireEvent.press(getByText("Войти"));
    await act(async () => { await Promise.resolve(); });
    expect(authenticated).toHaveBeenCalledWith("token");
    expect(AsyncStorage.setItem).toHaveBeenCalledWith("alter_access_token", "token");
  });

  it("does not start recording when microphone permission is denied", async () => {
    const recorded = jest.fn();
    const { getByLabelText } = render(<VoiceButton onRecorded={recorded} />);
    fireEvent(getByLabelText("Записать голосовое сообщение"), "pressIn");
    fireEvent(getByLabelText("Записать голосовое сообщение"), "pressOut");
    await waitFor(() => expect(recorded).not.toHaveBeenCalled());
  });
});
