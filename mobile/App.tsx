import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";
import * as Location from "expo-location";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import * as Notifications from "expo-notifications";
import { StatusBar } from "expo-status-bar";
import { Audio } from "expo-av";
import * as ImagePicker from "expo-image-picker";
import * as Clipboard from "expo-clipboard";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Animated, AppState, Easing, FlatList, Image, Keyboard, KeyboardAvoidingView, LayoutAnimation, Linking, Modal, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, UIManager, View } from "react-native";
import { AccountResponse, LocationContext, MemoryResponse, api } from "./src/api/client";

const Stack = createNativeStackNavigator();
type AuthProps = { onAuthenticated: (token: string) => void };
type ChatItem = { id: string; role: string; text: string; createdAt?: number; mediaUri?: string; feedback?: "positive" | "negative" };
export function getExpiredChatIds(items: ChatItem[], now: number, timeoutMs = 60000): string[] {
  const cutoff = now - timeoutMs;
  const keep = new Set<string>();
  for (const role of ["user", "assistant"]) {
    items.filter((item) => item.role === role).slice(-3).forEach((item) => keep.add(item.id));
  }
  return items.filter((item) => item.createdAt !== undefined && item.createdAt <= cutoff && !keep.has(item.id)).map((item) => item.id);
}

Notifications.setNotificationHandler({ handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false }) });

if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

async function registerPushNotifications(token: string) {
  if (Platform.OS === "web") return;
  let status = await Notifications.getPermissionsAsync();
  if (!status.granted) status = await Notifications.requestPermissionsAsync();
  if (!status.granted) return;
  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  const pushToken = (await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined)).data;
  await api.registerPushToken(token, pushToken);
}

export function IntroScreen({ onFinished }: { onFinished: () => void }) {
  const opacity = React.useRef(new Animated.Value(0)).current;
  const scale = React.useRef(new Animated.Value(0.94)).current;
  const line = React.useRef(new Animated.Value(0)).current;

  useEffect(() => {
    let sound: Audio.Sound | null = null;
    const soundUrl = process.env.EXPO_PUBLIC_INTRO_SOUND_URL;
    if (soundUrl) {
      Audio.setAudioModeAsync({ playsInSilentModeIOS: true }).then(async () => {
        const loaded = await Audio.Sound.createAsync({ uri: soundUrl }, { shouldPlay: true, volume: 0.22 });
        sound = loaded.sound;
      }).catch(() => undefined);
    }
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 700, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 8, tension: 35, useNativeDriver: true }),
      Animated.timing(line, { toValue: 1, duration: 1500, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
    ]).start();
    const timer = setTimeout(() => {
      Animated.timing(opacity, { toValue: 0, duration: 420, useNativeDriver: true }).start(() => onFinished());
    }, 1850);
    return () => { clearTimeout(timer); if (sound) sound.unloadAsync().catch(() => undefined); };
  }, [line, opacity, onFinished, scale]);

  return <View style={[styles.intro, { backgroundColor: "#050505" }]}><Animated.View style={{ opacity, transform: [{ scale }] }}><Text style={styles.introLogo}>ALTER</Text><Text style={styles.introCaption}>PERSONAL INTELLIGENCE</Text></Animated.View><Animated.View style={[styles.introLine, { width: line.interpolate({ inputRange: [0, 1], outputRange: [0, 150] }) }]} /><StatusBar style="light" /></View>;
}

function TypingText({ text }: { text: string }) {
  const [visible, setVisible] = useState("");
  useEffect(() => {
    setVisible("");
    let index = 0;
    const timer = setInterval(() => {
      index += Math.max(1, Math.ceil((text.length - index) / 18));
      setVisible(text.slice(0, index));
      if (index >= text.length) clearInterval(timer);
    }, 42);
    return () => clearInterval(timer);
  }, [text]);
  const parts = visible.split(/(https?:\/\/[^\s]+)/g);
  return <Text style={styles.message}>{parts.map((part, index) => part.match(/^https?:\/\//) ? <Text key={`${part}-${index}`} style={linkStyles.link} onPress={() => Linking.openURL(part.replace(/[),.!?]+$/, ""))}>{part}</Text> : <Text key={`${part}-${index}`}>{part}</Text>)}{visible.length < text.length ? <Text style={styles.cursor}>▋</Text> : null}</Text>;
}

function ActivityPulse() {
  const scale = React.useRef(new Animated.Value(0.72)).current;
  useEffect(() => {
    const animation = Animated.loop(Animated.sequence([
      Animated.timing(scale, { toValue: 1.35, duration: 1300, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
      Animated.timing(scale, { toValue: 0.72, duration: 1300, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
    ]));
    animation.start();
    return () => animation.stop();
  }, [scale]);
  return <Animated.View style={[activityStyles.activityDot, { transform: [{ scale }] }]} />;
}

function IdleAlterScreen({ opacity }: { opacity: Animated.Value }) {
  const pulse = React.useRef(new Animated.Value(0.72)).current;
  const line = React.useRef(new Animated.Value(0)).current;
  const drift = React.useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const pulseLoop = Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 1, duration: 2200, useNativeDriver: true }),
      Animated.timing(pulse, { toValue: 0.72, duration: 2200, useNativeDriver: true }),
    ]));
    const lineLoop = Animated.loop(Animated.sequence([
      Animated.timing(line, { toValue: 1, duration: 2600, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
      Animated.timing(line, { toValue: 0, duration: 2600, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
    ]));
    const textLoop = Animated.loop(Animated.sequence([
      Animated.timing(drift, { toValue: -1, duration: 42000, easing: Easing.linear, useNativeDriver: true }),
      Animated.timing(drift, { toValue: 0, duration: 1, useNativeDriver: true }),
    ]));
    pulseLoop.start(); lineLoop.start(); textLoop.start();
    return () => { pulseLoop.stop(); lineLoop.stop(); textLoop.stop(); };
  }, [drift, line, pulse]);
  const capabilities = "память\nживой диалог\nголосовые ответы\nтранскрипция речи\nфото и видео\nсоздание изображений\nпоиск и музыка\nпогода и напоминания\nнапоминания о важном\nмягкая забота\nобщий контекст\nALTER рядом";
  return <Animated.View pointerEvents="none" style={[idleStyles.overlay, { opacity, zIndex: 20, backgroundColor: "#050505" }]}>
    <Animated.Text style={[styles.introLogo, idleStyles.logo, { opacity: pulse }]}>ALTER</Animated.Text>
    <Animated.View style={[styles.introLine, idleStyles.line, { width: line.interpolate({ inputRange: [0, 1], outputRange: [0, 150] }) }]} />
    <View style={idleStyles.capabilityViewport}><Animated.Text style={[idleStyles.capabilities, { transform: [{ translateY: drift.interpolate({ inputRange: [-1, 0], outputRange: [-320, 230] }) }] }]}>{capabilities}</Animated.Text><View pointerEvents="none" style={[idleStyles.capabilityFade, idleStyles.capabilityFadeTop]} /><View pointerEvents="none" style={[idleStyles.capabilityFade, idleStyles.capabilityFadeBottom]} /></View><View style={{ width: "100%", overflow: "hidden", marginTop: 12, gap: 4 }}><Animated.Text style={{ color: "#777777", fontSize: 9, letterSpacing: 2, width: 700, textAlign: "center", transform: [{ translateX: drift.interpolate({ inputRange: [-1, 0], outputRange: [-360, 260] }) }] }}>ALTER · 2026 · ™</Animated.Text><Animated.Text style={{ color: "#666666", fontSize: 8, letterSpacing: 2, width: 700, textAlign: "center", transform: [{ translateX: drift.interpolate({ inputRange: [-1, 0], outputRange: [260, -360] }) }] }}>PERSONAL INTELLIGENCE · VERSION 0.1.0</Animated.Text></View>
    <View pointerEvents="none" style={{ position: "absolute", left: 0, right: 0, bottom: 18, height: 28, backgroundColor: "#050505", alignItems: "center", justifyContent: "center", overflow: "hidden" }}><Animated.Text style={{ color: "#777777", fontSize: 9, letterSpacing: 2, width: 900, textAlign: "center", transform: [{ translateX: drift.interpolate({ inputRange: [-1, 0], outputRange: [-520, 300] }) }] }}>ALTER · PERSONAL INTELLIGENCE · 2026 · ™ · VERSION 0.1.0</Animated.Text></View>
  </Animated.View>;
}

export function VoiceButton({ onRecorded, onRecordingChange }: { onRecorded: (uri: string) => void; onRecordingChange?: (active: boolean) => void }) {
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const pulse = React.useRef(new Animated.Value(1)).current;
  const pulseLoop = React.useRef<Animated.CompositeAnimation | null>(null);
  const start = async () => {
    const permission = await Audio.requestPermissionsAsync();
    if (!permission.granted) return;
    await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
    const result = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
    setRecording(result.recording);
    onRecordingChange?.(true);
    pulseLoop.current = Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 1.22, duration: 500, useNativeDriver: true }),
      Animated.timing(pulse, { toValue: 1, duration: 500, useNativeDriver: true }),
    ]));
    pulseLoop.current.start();
  };
  const stop = async () => {
    const current = recording;
    if (!current) return;
    pulseLoop.current?.stop(); pulse.setValue(1);
    await current.stopAndUnloadAsync();
    const uri = current.getURI();
    setRecording(null);
    onRecordingChange?.(false);
    if (uri) onRecorded(uri);
  };
  return <Pressable onPressIn={start} onPressOut={stop} accessibilityLabel="Записать голосовое сообщение"><Animated.View style={[mediaStyles.voiceHalo, { transform: [{ scale: pulse }] }, recording ? mediaStyles.voiceHaloActive : null]}><Animated.View style={[mediaStyles.voiceButton, recording ? mediaStyles.voiceButtonActive : null]}><Text style={mediaStyles.voiceIcon}>◉</Text></Animated.View></Animated.View></Pressable>;
}

export function AuthScreen({ onAuthenticated }: AuthProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [registerMode, setRegisterMode] = useState(false);
  const [verificationEmail, setVerificationEmail] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [legalAccepted, setLegalAccepted] = useState(false);

  const submit = async () => {
    if (registerMode && !email.trim()) { setError("Введите email"); return; }
    if (registerMode && !legalAccepted) { setError("Прими документы ALTER, чтобы продолжить регистрацию"); return; }
    setBusy(true); setError("");
    try {
      if (registerMode) {
        await api.register(email, password);
        setVerificationEmail(email.trim().toLowerCase());
      } else {
        const result = await api.login(email, password);
        await AsyncStorage.setItem("alter_access_token", result.access_token);
        onAuthenticated(result.access_token);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось выполнить запрос"); }
    finally { setBusy(false); }
  };

  const verify = async () => {
    if (!/^\d{6}$/.test(code)) { setError("Введите 6-значный код"); return; }
    setBusy(true); setError("");
    try {
      const result = await api.verifyEmail(verificationEmail || email, code);
      await AsyncStorage.setItem("alter_access_token", result.access_token);
      onAuthenticated(result.access_token);
    } catch (err) { setError(err instanceof Error ? err.message : "Неверный код"); }
    finally { setBusy(false); }
  };

  const resend = async () => {
    if (!verificationEmail || resending) return;
    setResending(true); setError("");
    try { await api.resendVerification(verificationEmail); }
    catch (err) { setError(err instanceof Error ? err.message : "Не удалось отправить код"); }
    finally { setResending(false); }
  };

  if (verificationEmail) return <SafeAreaView style={styles.container}><View style={styles.card}>
    <Text style={styles.title}>Проверь почту</Text>
    <Text style={styles.subtitle}>Код отправлен на {verificationEmail}. Он действует 10 минут.</Text>
    <TextInput autoFocus keyboardType="number-pad" maxLength={6} placeholder="6-значный код" placeholderTextColor="#78809a" style={styles.input} value={code} onChangeText={(value) => setCode(value.replace(/\D/g, ""))} />
    {error ? <Text style={styles.error}>{error}</Text> : null}
    {busy ? <ActivityIndicator color="#ffffff" /> : <Pressable style={authStyles.primary} onPress={verify}><Text style={authStyles.primaryText}>Подтвердить email</Text></Pressable>}
    <Pressable style={authStyles.secondary} onPress={resend} disabled={busy || resending}><Text style={authStyles.secondaryText}>{resending ? "Отправляем…" : "Отправить код ещё раз"}</Text></Pressable>
  </View><StatusBar style="light" /></SafeAreaView>;

  return <SafeAreaView style={styles.container}><View style={styles.card}>
    <Text style={styles.title}>ALTER</Text><Text style={styles.subtitle}>Твоё личное AI-пространство</Text>
    <TextInput autoCapitalize="none" keyboardType="email-address" placeholder="Email" placeholderTextColor="#78809a" style={styles.input} value={email} onChangeText={setEmail} />
    <TextInput secureTextEntry placeholder="Пароль" placeholderTextColor="#78809a" style={styles.input} value={password} onChangeText={setPassword} />
    {error ? <Text style={styles.error}>{error}</Text> : null}
    {registerMode ? <Pressable style={authStyles.legalRow} onPress={() => setLegalAccepted(!legalAccepted)}><Text style={authStyles.check}>{legalAccepted ? "✓" : "○"}</Text><Text style={authStyles.legalText}>Принимаю <Text style={linkStyles.link} onPress={() => Linking.openURL("https://alterai.ru/legal/privacy.html")}>политику конфиденциальности</Text> и <Text style={linkStyles.link} onPress={() => Linking.openURL("https://alterai.ru/legal/offer.html")}>условия ALTER</Text></Text></Pressable> : null}
    {busy ? <ActivityIndicator color="#ffffff" /> : <Pressable style={authStyles.primary} onPress={submit}><Text style={authStyles.primaryText}>{registerMode ? "Создать аккаунт" : "Войти"}</Text></Pressable>}
    <Pressable style={authStyles.secondary} onPress={() => { setRegisterMode(!registerMode); setLegalAccepted(false); }}><Text style={authStyles.secondaryText}>{registerMode ? "У меня уже есть аккаунт" : "Создать аккаунт"}</Text></Pressable>
  </View><StatusBar style="light" /></SafeAreaView>;
}

export function ChatScreen({ token, onLogout }: { token: string; onLogout: () => void }) {
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<ChatItem[]>([]);
  const [archivedItems, setArchivedItems] = useState<ChatItem[]>([]);
  const [historyVisible, setHistoryVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [memoryData, setMemoryData] = useState<MemoryResponse | null>(null);
  const [memoryVisible, setMemoryVisible] = useState(false);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memoryError, setMemoryError] = useState("");
  const [reminders, setReminders] = useState<{ id: number; text: string; remind_at: string }[]>([]);
  const [remindersVisible, setRemindersVisible] = useState(false);
  // Reminders are created from the main chat (text or voice), not by a fixed
  // one-hour shortcut. The reminders screen is read/delete only.
  const [reminderText, setReminderText] = useState("");
  const [menuVisible, setMenuVisible] = useState(false);
  const [newChatPromptVisible, setNewChatPromptVisible] = useState(false);
  const [newChatLoading, setNewChatLoading] = useState(false);
  const [permissionOfferVisible, setPermissionOfferVisible] = useState(false);
  const [permissionBusy, setPermissionBusy] = useState(false);
  const [menuError, setMenuError] = useState("");
  const [plansVisible, setPlansVisible] = useState(false);
  const [voiceReplies, setVoiceReplies] = useState(false);
  const [checkinsEnabled, setCheckinsEnabled] = useState(true);
  const [autoVoiceReplies, setAutoVoiceReplies] = useState(false);
  const [ttsVoice, setTtsVoice] = useState("alloy");
  const [language, setLanguage] = useState("Русский");
  const [voiceMenuOpen, setVoiceMenuOpen] = useState(false);
  const [emailVisible, setEmailVisible] = useState(false);
  const [openSection, setOpenSection] = useState<"profile" | "connections" | "tools" | "app" | null>(null);
  const [usage, setUsage] = useState<{ used: number; limit: number; remaining: number } | null>(null);
  const [mediaPickerVisible, setMediaPickerVisible] = useState(false);
  const [feedbackFor, setFeedbackFor] = useState<string | null>(null);
  const [idle, setIdle] = useState(false);
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [attachment, setAttachment] = useState<{ uri: string; type: "image" | "video" | "audio" } | null>(null);
  const [activity, setActivity] = useState<"" | "thinking" | "analyzing" | "recording">("");
  const [location, setLocation] = useState<LocationContext | null>(null);
  const listRef = React.useRef<FlatList<ChatItem>>(null);
  const autoScrollAfterUpdate = React.useRef(false);
  const drawerX = React.useRef(new Animated.Value(-420)).current;
  const logoPulse = React.useRef(new Animated.Value(0.72)).current;
  const idleShade = React.useRef(new Animated.Value(0)).current;
  const idleTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const resetIdle = React.useCallback(() => {
    setIdle(false);
    Animated.timing(idleShade, { toValue: 0, duration: 700, useNativeDriver: true }).start();
    if (idleTimer.current) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => {
      setIdle(true);
      Animated.sequence([Animated.timing(idleShade, { toValue: 0.32, duration: 2200, easing: Easing.inOut(Easing.quad), useNativeDriver: true }), Animated.timing(idleShade, { toValue: 0.68, duration: 2600, easing: Easing.inOut(Easing.quad), useNativeDriver: true }), Animated.timing(idleShade, { toValue: 1, duration: 3600, easing: Easing.inOut(Easing.quad), useNativeDriver: true })]).start();
    }, 120000);
  }, [idleShade]);
  const refreshAccount = () => { api.account(token).then(setAccount).catch(() => undefined); };
  useEffect(() => {
    AsyncStorage.getItem(`alter_permission_offer_seen_${token}`).then((value) => {
      if (value !== "1") setPermissionOfferVisible(true);
    }).catch(() => setPermissionOfferVisible(true));
    refreshAccount();
    api.usage(token).then(setUsage).catch(() => undefined);
    api.settings(token).then(({ settings, checkins_enabled }) => {
      setCheckinsEnabled(checkins_enabled);
      setVoiceReplies(settings.voice_replies === true);
      setAutoVoiceReplies(settings.voice_auto_replies === true);
      if (typeof settings.tts_voice === "string") setTtsVoice(settings.tts_voice);
    }).catch(() => undefined);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") refreshAccount();
    });
    return () => subscription.remove();
  }, [token]);
  useEffect(() => {
    api.history(token).then((result) => setItems(result.messages.map((item, index) => ({ id: `history-${index}`, role: item.role, text: item.content })))).catch(() => undefined);
  }, [token]);
  useEffect(() => {
    const timer = setInterval(() => {
        const cutoff = Date.now();
      setItems((current) => {
        const keep = new Set<string>();
        for (const role of ["user", "assistant"]) {
          current.filter((item) => item.role === role).slice(-3).forEach((item) => keep.add(item.id));
        }
        const expiredIds = new Set(getExpiredChatIds(current, cutoff));
        const expired = current.filter((item) => expiredIds.has(item.id));
        if (expired.length) setArchivedItems((old) => [...old, ...expired.filter((item) => !old.some((entry) => entry.id === item.id))]);
        const next = current.filter((item) => !expiredIds.has(item.id));
        if (next.length === current.length) return current;
        LayoutAnimation.configureNext({
          duration: 900,
          create: { type: LayoutAnimation.Types.easeInEaseOut, property: LayoutAnimation.Properties.opacity },
          update: { type: LayoutAnimation.Types.easeInEaseOut },
          delete: { type: LayoutAnimation.Types.easeInEaseOut, property: LayoutAnimation.Properties.scaleXY },
        });
        return next;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    setItems((current) => {
      const now = Date.now();
      const normalized = current.map((item) => item.createdAt ? item : { ...item, createdAt: now });
      return normalized.some((item, index) => item !== current[index]) ? normalized : current;
    });
  }, [items]);
  useEffect(() => {
    if (menuVisible) {
      drawerX.setValue(-420);
      Animated.spring(drawerX, { toValue: 0, damping: 22, stiffness: 220, mass: 0.8, useNativeDriver: true }).start();
    }
  }, [drawerX, menuVisible]);
  useEffect(() => {
    const animation = Animated.loop(Animated.sequence([
      Animated.timing(logoPulse, { toValue: 1, duration: 1400, useNativeDriver: true }),
      Animated.timing(logoPulse, { toValue: 0.72, duration: 1400, useNativeDriver: true }),
    ]));
    animation.start();
    return () => animation.stop();
  }, [logoPulse]);
  useEffect(() => { resetIdle(); return () => { if (idleTimer.current) clearTimeout(idleTimer.current); }; }, [resetIdle]);
  const playVoiceReply = async (text: string, id?: string) => {
    if (playingVoiceId) return;
    setPlayingVoiceId(id || "manual");
    try {
      const blob = await api.voiceReply(token, text);
      const dataUrl = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onloadend = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(blob); });
      const base64 = dataUrl.split(",", 2)[1];
      if (!base64 || !FileSystem.cacheDirectory) throw new Error("Аудиофайл пустой");
      const uri = `${FileSystem.cacheDirectory}alter-reply-${Date.now()}.wav`;
      await FileSystem.writeAsStringAsync(uri, base64, { encoding: FileSystem.EncodingType.Base64 });
      const loaded = await Audio.Sound.createAsync({ uri }, { shouldPlay: true });
      loaded.sound.setOnPlaybackStatusUpdate((status) => { if ("didJustFinish" in status && status.didJustFinish) { setPlayingVoiceId(null); loaded.sound.unloadAsync(); } });
    } catch (err) { setPlayingVoiceId(null); setMenuError(err instanceof Error ? err.message : "Не удалось озвучить ответ"); }
  };
  const send = async () => {
    const text = message.trim(); if ((!text && !attachment) || busy) return;
    const currentAttachment = attachment;
    const userMessageId = `${Date.now()}u`;
    autoScrollAfterUpdate.current = true;
    Keyboard.dismiss(); setMessage(""); setAttachment(null); setItems((old) => [...old, { id: userMessageId, role: "user", text: currentAttachment?.type === "audio" ? " " : currentAttachment ? `${text || "Вложение"} · ${currentAttachment.type}` : text }]); setBusy(true); setActivity(currentAttachment ? "analyzing" : "thinking");
    try { const result = currentAttachment ? await api.sendMedia(token, text, currentAttachment.uri, currentAttachment.type) : await api.sendMessage(token, text, location); if (currentAttachment?.type === "audio" && result.transcript) setItems((old) => old.map((item) => item.id === userMessageId ? { ...item, text: result.transcript! } : item)); autoScrollAfterUpdate.current = true; const answerId = `${Date.now()}a`; setItems((old) => [...old, { id: answerId, role: "assistant", text: result.reply }]); if (voiceReplies && autoVoiceReplies) playVoiceReply(result.reply, answerId); }
    catch (err) { setItems((old) => [...old, { id: `${Date.now()}e`, role: "assistant", text: err instanceof Error ? err.message : "Ошибка запроса" }]); }
    finally { setBusy(false); setActivity(""); }
  };
  const generateAttachment = async () => {
    if (!attachment || attachment.type === "audio" || busy) return;
    const current = attachment;
    const kind = current.type as "image" | "video";
    setBusy(true); setActivity("analyzing");
    try {
      const result = await api.generateMedia(token, message.trim(), current.uri, kind);
      setItems((old) => [...old, { id: `${Date.now()}g`, role: "assistant", text: "Готово.", mediaUri: `data:${result.media_type};base64,${result.data_base64}` }]);
      setMessage(""); setAttachment(null); autoScrollAfterUpdate.current = true;
    } catch (err) { setItems((old) => [...old, { id: `${Date.now()}e`, role: "assistant", text: err instanceof Error ? err.message : "Не удалось изменить медиа" }]); }
    finally { setBusy(false); setActivity(""); }
  };
  const openTelegramLink = async () => {
    setMenuError("");
    try { const result = await api.startTelegramLink(token); await Linking.openURL(result.url); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось открыть Telegram"); }
  };
  const buySubscription = async (plan: "personal" | "ego") => {
    setMenuError("");
    try { const result = await api.createPayment(token, plan); await Linking.openURL(result.payment_url); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Оплата пока недоступна"); }
  };
  const requestLocation = async (background: boolean) => {
    setMenuError("");
    const foreground = await Location.requestForegroundPermissionsAsync();
    if (foreground.status !== Location.PermissionStatus.GRANTED) { setMenuError("Геолокация не разрешена."); return; }
    if (background) {
      const backgroundPermission = await Location.requestBackgroundPermissionsAsync();
      if (backgroundPermission.status !== Location.PermissionStatus.GRANTED) setMenuError("Фоновая геолокация не разрешена. Оставляю режим только при использовании.");
    }
    try {
      const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const place = await Location.reverseGeocodeAsync({ latitude: position.coords.latitude, longitude: position.coords.longitude });
      const first = place[0];
      setLocation({ latitude: position.coords.latitude, longitude: position.coords.longitude, city: first?.city || first?.district || undefined, region: first?.region || undefined, country: first?.country || undefined });
    } catch { setMenuError("Не удалось определить местоположение."); }
  };
  const acceptPermissionOffer = async () => {
    setPermissionBusy(true);
    try {
      await registerPushNotifications(token);
      await requestLocation(false);
    } finally { await AsyncStorage.setItem(`alter_permission_offer_seen_${token}`, "1"); setPermissionBusy(false); setPermissionOfferVisible(false); }
  };
  const chooseLocationMode = () => Alert.alert("Геолокация", "Выбери, как ALTER может использовать местоположение.", [
    { text: "Только при использовании", onPress: () => requestLocation(false) },
    { text: "Всегда, если разрешит iPhone", onPress: () => requestLocation(true) },
    { text: "Отмена", style: "cancel" },
  ]);
  const toggleAutoRenew = async () => {
    if (!account?.payment_method_saved) { setMenuError("Сначала нужна обычная оплата с сохранением карты."); return; }
    try {
      const result = await api.setAutoRenew(token, !account.auto_renew);
      setAccount({ ...account, auto_renew: result.auto_renew });
    } catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось изменить автопродление"); }
  };
  const removePaymentMethod = () => Alert.alert("Удалить карту?", "Автопродление будет выключено. Следующую оплату можно будет провести заново.", [
    { text: "Отмена", style: "cancel" },
    { text: "Удалить", style: "destructive", onPress: async () => {
      try { await api.removePaymentMethod(token); setAccount(account ? { ...account, auto_renew: false, payment_method_saved: false } : account); }
      catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось удалить карту"); }
    } },
  ]);
  const openMemory = async () => {
    setMemoryVisible(true); setMemoryLoading(true); setMemoryError(""); setMenuVisible(false);
    try { setMemoryData(await api.memory(token)); }
    catch (err) { setMemoryError(err instanceof Error ? err.message : "Не удалось загрузить память"); }
    finally { setMemoryLoading(false); }
  };
  const openReminders = async () => {
    setRemindersVisible(true); setMenuVisible(false);
    try { setReminders((await api.reminders(token)).reminders); } catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось загрузить напоминания"); }
  };
  const createQuickReminder = async () => {
    const text = reminderText.trim(); if (!text) return;
    try { const item = await api.createReminder(token, text, new Date(Date.now() + 60 * 60 * 1000).toISOString()); setReminders((old) => [...old, item]); setReminderText(""); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось создать напоминание"); }
  };
  const toggleCheckins = async () => {
    const next = !checkinsEnabled; setCheckinsEnabled(next);
    try { await api.setCheckins(token, next); } catch (err) { setCheckinsEnabled(!next); setMenuError(err instanceof Error ? err.message : "Не удалось изменить check-in"); }
  };
  const pickMediaLibrary = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) { setMenuError("Разреши доступ к медиатеке"); return; }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.All, quality: 0.85 });
    if (!result.canceled && result.assets[0]) {
      const asset = result.assets[0];
      setAttachment({ uri: asset.uri, type: asset.type === "video" ? "video" : "image" });
    }
  };
  const pickFile = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: ["image/*", "video/*", "audio/*"], copyToCacheDirectory: true });
    if (!result.canceled && result.assets[0]) {
      const asset = result.assets[0];
      const mime = asset.mimeType || "";
      setAttachment({ uri: asset.uri, type: mime.startsWith("video/") ? "video" : mime.startsWith("audio/") ? "audio" : "image" });
    }
  };
  const pickMedia = () => setMediaPickerVisible(true);
  const takePhoto = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) { setMenuError("Разреши доступ к камере"); return; }
    const result = await ImagePicker.launchCameraAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.85 });
    if (!result.canceled && result.assets[0]) setAttachment({ uri: result.assets[0].uri, type: "image" });
  };
  const keepVoice = (uri: string) => setAttachment({ uri, type: "audio" });
  const setFeedback = async (id: string, feedback: "positive" | "negative") => {
    setItems((old) => old.map((item) => item.id === id ? { ...item, feedback } : item)); setFeedbackFor(null);
    try {
      const { settings } = await api.settings(token);
      const previous = Array.isArray(settings.reply_feedback) ? settings.reply_feedback : [];
      await api.updateSettings(token, { reply_feedback: [...previous, { rating: feedback, at: new Date().toISOString() }].slice(-100) });
    } catch { /* Rating is optional; keep the local acknowledgement. */ }
  };
  const startNewChat = async () => { if (busy || newChatLoading) return; setNewChatPromptVisible(false); setNewChatLoading(true); try { await api.newSession(token); setItems([]); setMessage(""); setAttachment(null); setMenuVisible(false); resetIdle(); } catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось начать новый чат"); } finally { setNewChatLoading(false); } };
  const memorySections = memoryData?.sections || [];
  const maskedEmail = account?.email ? account.email.replace(/^(.{2}).*(@.*)$/, "$1•••$2") : "Почта не указана";
  return <SafeAreaView style={[styles.container, { backgroundColor: "#000000" }]} onTouchStart={resetIdle}><Animated.View pointerEvents="none" style={[idleStyles.shade, { opacity: idleShade }]} /><IdleAlterScreen opacity={idleShade} /><Pressable style={historyStyles.handle} onPress={() => setHistoryVisible(true)} accessibilityLabel="Открыть историю переписки"><Text style={historyStyles.arrow}>›</Text></Pressable><KeyboardAvoidingView style={styles.chat} behavior={Platform.OS === "ios" ? "padding" : undefined}>
    <View style={styles.header}><Pressable style={premiumStyles.headerAction} onPress={() => { Keyboard.dismiss(); refreshAccount(); setMenuVisible(true); }} accessibilityLabel="Открыть боковую панель"><Text style={premiumStyles.headerActionText}>☰</Text></Pressable><Text style={styles.headerTitle}>ALTER</Text><Pressable style={premiumStyles.refreshAction} onPress={() => setNewChatPromptVisible((value) => !value)} accessibilityLabel="Новый чат"><Text style={premiumStyles.refreshIcon}>↻</Text></Pressable></View>
    {newChatPromptVisible ? <View style={premiumStyles.newChatPrompt}><Text style={premiumStyles.newChatPromptText}>Начать новый чат?</Text><View style={premiumStyles.newChatActions}><Pressable onPress={() => setNewChatPromptVisible(false)} accessibilityLabel="Отменить новый чат"><Text style={premiumStyles.newChatAction}>×</Text></Pressable><Pressable onPress={startNewChat} accessibilityLabel="Подтвердить новый чат"><Text style={premiumStyles.newChatAction}>✓</Text></Pressable></View></View> : null}
    {newChatLoading ? <View style={premiumStyles.newChatLoading} pointerEvents="none"><Animated.Text style={[premiumStyles.newChatLoadingLogo, { opacity: logoPulse }]}>ALTER</Animated.Text><Text style={premiumStyles.newChatLoadingText}>Начинаем новый чат</Text></View> : null}
    <FlatList ref={listRef} data={items} keyExtractor={(item) => item.id} contentContainerStyle={styles.messages} keyboardShouldPersistTaps="handled" keyboardDismissMode="interactive" automaticallyAdjustKeyboardInsets onContentSizeChange={() => { if (autoScrollAfterUpdate.current) { autoScrollAfterUpdate.current = false; requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true })); } }} renderItem={({ item }) => <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.aiBubble]}>{item.role === "assistant" ? <><TypingText text={item.text} /><View style={answerActionStyles.row}><Pressable onPress={async () => { await Clipboard.setStringAsync(item.text); setCopiedId(item.id); setTimeout(() => setCopiedId(null), 1600); }} style={({ pressed }) => [answerActionStyles.button, pressed && answerActionStyles.pressed]} accessibilityLabel="Скопировать ответ"><Text style={answerActionStyles.icon}>{copiedId === item.id ? "✓" : "⧉"}</Text>{copiedId === item.id ? <Text style={answerActionStyles.hint}>Скопировано</Text> : null}</Pressable><Pressable onPress={() => playVoiceReply(item.text, item.id)} disabled={playingVoiceId !== null} style={({ pressed }) => [answerActionStyles.voiceButton, pressed && answerActionStyles.pressed, playingVoiceId === item.id && answerActionStyles.active]} accessibilityLabel="Озвучить ответ"><Text style={answerActionStyles.icon}>{playingVoiceId === item.id ? "◼" : "◖))"}</Text></Pressable><Pressable onPress={() => setFeedbackFor(item.id)} style={({ pressed }) => [answerActionStyles.button, pressed && answerActionStyles.pressed]} accessibilityLabel="Оценить ответ"><Text style={[answerActionStyles.icon, item.feedback ? answerActionStyles.selected : null]}>{item.feedback === "positive" ? "👍" : item.feedback === "negative" ? "👎" : "♡"}</Text></Pressable></View></> : <Text style={[styles.message, styles.userMessage]}>{item.text}</Text>}{item.mediaUri ? <Image source={{ uri: item.mediaUri }} style={{ width: 240, height: 240, borderRadius: 12, marginTop: 8 }} /> : null}</View>} />
    {activity ? <View style={activityStyles.activityPill}><ActivityPulse /><Text style={activityStyles.activityText}>{activity === "recording" ? "Записываю голосовое…" : activity === "analyzing" ? "Изучаю вложение…" : "Думаю над ответом…"}</Text></View> : null}
    {attachment ? <View style={mediaStyles.attachmentChip}><Text style={mediaStyles.attachmentText}>{attachment.type === "audio" ? "Голосовое сообщение" : attachment.type === "video" ? "Видео прикреплено" : "Фото прикреплено"}</Text>{attachment.type !== "audio" ? <Pressable onPress={generateAttachment} disabled={busy}><Text style={mediaStyles.generateAction}>✦ Изменить</Text></Pressable> : null}<Pressable onPress={() => setAttachment(null)}><Text style={mediaStyles.removeAttachment}>×</Text></Pressable></View> : null}
    <View style={styles.composer}><Pressable style={mediaStyles.attachButton} onPress={() => { resetIdle(); pickMedia(); }} accessibilityLabel="Прикрепить фото или видео"><Text style={mediaStyles.attachIcon}>＋</Text></Pressable><TextInput style={[styles.input, styles.composerInput]} placeholder="Напиши ALTER..." placeholderTextColor="#78809a" value={message} onChangeText={(value) => { resetIdle(); setMessage(value); }} onSubmitEditing={send} /><VoiceButton onRecorded={keepVoice} onRecordingChange={(active) => { resetIdle(); setActivity(active ? "recording" : ""); }} /><Pressable style={mediaStyles.sendButton} onPress={send} accessibilityLabel="Отправить сообщение"><Text style={mediaStyles.sendIcon}>{busy ? "…" : "↑"}</Text></Pressable></View>
    {!message ? <View pointerEvents="none" style={mediaStyles.inputMask}><View style={mediaStyles.inputGlow} /></View> : null}
  </KeyboardAvoidingView>
  <Modal visible={historyVisible} transparent animationType="fade" onRequestClose={() => setHistoryVisible(false)}><Pressable style={historyStyles.backdrop} onPress={() => setHistoryVisible(false)}><Pressable style={historyStyles.panel} onPress={(event) => event.stopPropagation()}><Pressable onPress={() => setHistoryVisible(false)} accessibilityLabel="Закрыть историю"><Text style={historyStyles.panelClose}>‹</Text></Pressable><Text style={historyStyles.title}>История</Text><FlatList data={archivedItems} keyExtractor={(item) => item.id} renderItem={({ item }) => <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.aiBubble]}><Text style={styles.message}>{item.text}</Text></View>} ListEmptyComponent={<Text style={historyStyles.empty}>Здесь появятся старые сообщения</Text>} /></Pressable></Pressable></Modal>
  <Modal visible={permissionOfferVisible} transparent animationType="fade" onRequestClose={() => setPermissionOfferVisible(false)}>
    <View style={permissionStyles.backdrop}><View style={permissionStyles.card}><Text style={permissionStyles.kicker}>ALTER · PERSONAL MODE</Text><Text style={permissionStyles.title}>Понимать тебя точнее</Text><Text style={permissionStyles.body}>Разреши уведомления и примерную геолокацию — тогда ALTER сможет мягко напоминать о важном, ориентировать по погоде и лучше чувствовать контекст твоего дня.</Text><Pressable style={permissionStyles.primary} onPress={acceptPermissionOffer} disabled={permissionBusy}><Text style={permissionStyles.primaryText}>{permissionBusy ? "Настраиваем…" : "Разрешить для лучшего опыта"}</Text></Pressable><Pressable onPress={() => setPermissionOfferVisible(false)}><Text style={permissionStyles.later}>Позже</Text></Pressable></View></View>
  </Modal>
  <Modal visible={menuVisible} transparent animationType="none" onRequestClose={() => setMenuVisible(false)}>
    <Pressable style={premiumStyles.drawerBackdrop} onPress={() => setMenuVisible(false)}>
      <Animated.View style={[premiumStyles.menuCard, { transform: [{ translateX: drawerX }] }]}> 
      <Pressable style={premiumStyles.drawerContent} onPress={(event) => event.stopPropagation()}>
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={premiumStyles.drawerScroll}>
        <Animated.Text style={[premiumStyles.drawerLogo, { opacity: logoPulse }]}>ALTER</Animated.Text>
        <Pressable style={premiumStyles.sectionHeader} onPress={() => setOpenSection((value) => value === "profile" ? null : "profile")}><Text style={premiumStyles.sectionLabel}>ПРОФИЛЬ</Text><Text style={premiumStyles.sectionChevron}>{openSection === "profile" ? "⌃" : "⌄"}</Text></Pressable>
        {openSection === "profile" ? <View style={premiumStyles.sectionBody}>
        <Pressable style={premiumStyles.accountRow} onPress={() => setEmailVisible((value) => !value)}><Text style={premiumStyles.menuEmail}>{emailVisible ? (account?.email || "Почта не указана") : maskedEmail}</Text><Text style={premiumStyles.menuActionArrow}>{emailVisible ? "⌃" : "⌄"}</Text></Pressable>
        {account?.owner ? <Text style={premiumStyles.ownerBadge}>OWNER · FULL ACCESS</Text> : <Text style={premiumStyles.menuStatus}>ТАРИФ · {account?.subscription_plan === "ego" ? "ALTER EGO" : "ALTER PERSONAL"}</Text>}
        <View style={premiumStyles.usageRow}><Text style={premiumStyles.menuActionText}>Лимиты</Text><Text style={premiumStyles.usageText}>{usage ? `${usage.remaining} из ${usage.limit}` : "…"}</Text></View>
        <Pressable style={premiumStyles.menuAction} onPress={() => { const values = ["Русский", "English", "Español", "Deutsch", "中文"]; setLanguage(values[(values.indexOf(language) + 1) % values.length]); }}><Text style={premiumStyles.menuActionText}>Язык · {language}</Text><Text style={premiumStyles.menuActionArrow}>›</Text></Pressable>
        {account?.payment_method_saved ? <>
          <Pressable style={premiumStyles.menuAction} onPress={toggleAutoRenew}><Text style={premiumStyles.menuActionText}>{account.auto_renew ? "Выключить автопродление" : "Включить автопродление"}</Text><Text style={premiumStyles.menuActionArrow}>↔</Text></Pressable>
          <Pressable style={[premiumStyles.menuAction, premiumStyles.dangerAction]} onPress={removePaymentMethod}><Text style={premiumStyles.menuActionText}>Удалить карту</Text><Text style={premiumStyles.menuActionArrow}>×</Text></Pressable>
        </> : null}
        {!account?.owner ? <Pressable style={premiumStyles.menuAction} onPress={() => setPlansVisible(true)}><Text style={premiumStyles.menuActionText}>Подписка</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable> : null}
        </View> : null}
        <View style={styles.menuDivider} />
        <Pressable style={premiumStyles.sectionHeader} onPress={() => setOpenSection((value) => value === "connections" ? null : "connections")}><Text style={premiumStyles.sectionLabel}>ПОДКЛЮЧЕНИЯ</Text><Text style={premiumStyles.sectionChevron}>{openSection === "connections" ? "⌃" : "⌄"}</Text></Pressable>
        {openSection === "connections" ? <View style={premiumStyles.sectionBody}>
        <Text style={[styles.menuStatus, premiumStyles.menuStatus]}>{account?.telegram_linked ? "TELEGRAM · ПОДКЛЮЧЁН" : "TELEGRAM · НЕ ПОДКЛЮЧЁН"}</Text>
        {account?.subscription_expires_at ? <Text style={[styles.menuStatus, premiumStyles.menuStatus]}>ДОСТУП · {new Date(account.subscription_expires_at).toLocaleDateString()}</Text> : <Text style={[styles.menuStatus, premiumStyles.menuStatus]}>ДОСТУП · НЕ АКТИВИРОВАН</Text>}
        {menuError ? <Text style={styles.error}>{menuError}</Text> : null}
        </View> : null}
        <Pressable style={premiumStyles.sectionHeader} onPress={() => setOpenSection((value) => value === "tools" ? null : "tools")}><Text style={premiumStyles.sectionLabel}>ИНСТРУМЕНТЫ</Text><Text style={premiumStyles.sectionChevron}>{openSection === "tools" ? "⌃" : "⌄"}</Text></Pressable>
        {openSection === "tools" ? <View style={premiumStyles.sectionBody}>
        <Pressable style={premiumStyles.menuAction} onPress={openMemory}><Text style={premiumStyles.menuActionText}>Память</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={openReminders}><Text style={premiumStyles.menuActionText}>Напоминания</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={toggleCheckins}><View style={{ flex: 1 }}><Text style={premiumStyles.menuActionText}>Забота · {checkinsEnabled ? "включена" : "выключена"}</Text><Text style={{ color: "#777", fontSize: 12, marginTop: 3 }}>ALTER возвращается к важным темам и задаёт контекстный вопрос</Text></View><Text style={premiumStyles.menuActionArrow}>{checkinsEnabled ? "✓" : "○"}</Text></Pressable>
        {!account?.telegram_linked ? <Pressable style={premiumStyles.menuAction} onPress={openTelegramLink}><Text style={premiumStyles.menuActionText}>Подключить Telegram</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable> : null}
        <Pressable style={premiumStyles.menuAction} onPress={chooseLocationMode}><Text style={premiumStyles.menuActionText}>{location?.city ? `Геолокация · ${location.city}` : "Разрешить геолокацию"}</Text><Text style={premiumStyles.menuActionArrow}>⌖</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={async () => { const next = !voiceReplies; setVoiceReplies(next); setVoiceMenuOpen(next); try { await api.updateSettings(token, { voice_replies: next }); } catch (err) { setVoiceReplies(!next); setVoiceMenuOpen(false); setMenuError(err instanceof Error ? err.message : "Не удалось сохранить настройку"); } }}><Text style={premiumStyles.menuActionText}>Голосовые ответы</Text><Text style={premiumStyles.menuActionArrow}>{voiceReplies ? "✓" : "○"}</Text></Pressable>
        {voiceReplies && voiceMenuOpen ? <View style={premiumStyles.submenu}><Pressable style={premiumStyles.submenuAction} onPress={async () => { const next = !autoVoiceReplies; setAutoVoiceReplies(next); try { await api.updateSettings(token, { voice_auto_replies: next }); } catch (err) { setAutoVoiceReplies(!next); setMenuError(err instanceof Error ? err.message : "Не удалось сохранить настройку"); } }}><Text style={premiumStyles.menuActionText}>Озвучивать автоматически</Text><Text style={premiumStyles.menuActionArrow}>{autoVoiceReplies ? "✓" : "○"}</Text></Pressable><Pressable style={premiumStyles.submenuAction} onPress={async () => { const voices = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"]; const next = voices[(voices.indexOf(ttsVoice) + 1) % voices.length]; const preview = "Привет, я ALTER, твой персональный ассистент."; setTtsVoice(next); try { await api.updateSettings(token, { tts_voice: next }); await playVoiceReply(preview, "voice-preview"); } catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось выбрать голос"); } }}><Text style={premiumStyles.menuActionText}>Голос · {ttsVoice}</Text><Text style={premiumStyles.menuActionArrow}>›</Text></Pressable></View> : null}
        </View> : null}
        <Text style={premiumStyles.version}>ALTER · 0.1.0</Text><Pressable style={[premiumStyles.menuAction, premiumStyles.menuLogout]} onPress={() => { setMenuVisible(false); onLogout(); }}><Text style={premiumStyles.menuActionText}>Выйти</Text><Text style={premiumStyles.menuActionArrow}>↗</Text></Pressable>
        </ScrollView>
      </Pressable>
      </Animated.View>
    </Pressable>
  </Modal>
  <Modal visible={plansVisible} transparent animationType="fade" onRequestClose={() => setPlansVisible(false)}>
    <View style={planStyles.backdrop}><View style={planStyles.sheet}><Text style={planStyles.title}>Выбери ALTER</Text><Text style={planStyles.subtitle}>Память, Telegram и мобильное приложение входят в оба тарифа.</Text>
      <Pressable style={planStyles.card} onPress={() => buySubscription("personal")}><Text style={planStyles.name}>ALTER Personal</Text><Text style={planStyles.price}>990 ₽ <Text style={planStyles.period}>/ месяц</Text></Text><Text style={planStyles.features}>Личный чат · память · премиум-голос ElevenLabs · медиа · поиск · Telegram</Text><Text style={planStyles.action}>ПОДПИСАТЬСЯ</Text></Pressable>
      <Pressable style={[planStyles.card, planStyles.featured]} onPress={() => buySubscription("ego")}><Text style={planStyles.badge}>БОЛЬШЕ ВОЗМОЖНОСТЕЙ</Text><Text style={planStyles.name}>ALTER Ego</Text><Text style={planStyles.price}>2 990 ₽ <Text style={planStyles.period}>/ месяц</Text></Text><Text style={planStyles.features}>Всё из Personal · ElevenLabs · изменение и очистка голоса · создание звуков и медиа · расширенные квоты · приоритет</Text><Text style={planStyles.action}>ПОДПИСАТЬСЯ</Text></Pressable>
      <Pressable onPress={() => setPlansVisible(false)}><Text style={planStyles.cancel}>Закрыть</Text></Pressable>
    </View></View>
  </Modal>
  <Modal visible={remindersVisible} animationType="slide" onRequestClose={() => { setRemindersVisible(false); setMenuVisible(true); }}>
    <SafeAreaView style={styles.memoryScreen}><View style={styles.memoryHeader}><Text style={styles.memoryTitle}>Напоминания</Text><Pressable style={premiumStyles.menuAction} onPress={() => { setRemindersVisible(false); setMenuVisible(true); }}><Text style={premiumStyles.menuActionText}>Назад</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable></View>
      <Text style={{ color: "#999", paddingHorizontal: 20, paddingBottom: 8, lineHeight: 21 }}>Скажи ALTER в основном чате, о чём и к какому времени напомнить. Можно голосом.</Text>
      {reminders.length === 0 ? <Text style={styles.emptyMemory}>Активных напоминаний пока нет.</Text> : <FlatList data={reminders} keyExtractor={(item) => String(item.id)} contentContainerStyle={styles.memoryList} renderItem={({ item }) => <View style={styles.memoryRow}><Text style={styles.memoryValue}>{item.text}</Text><Text style={styles.memoryKey}>{new Date(item.remind_at).toLocaleString()}</Text><Pressable style={premiumStyles.menuAction} onPress={async () => { await api.deleteReminder(token, item.id); setReminders((old) => old.filter((entry) => entry.id !== item.id)); }}><Text style={premiumStyles.menuActionText}>Удалить</Text><Text style={premiumStyles.menuActionArrow}>×</Text></Pressable></View>} />}
    </SafeAreaView>
  </Modal>
  <Modal visible={mediaPickerVisible} transparent animationType="fade" onRequestClose={() => setMediaPickerVisible(false)}>
    <Pressable style={sheetStyles.backdrop} onPress={() => setMediaPickerVisible(false)}><Pressable style={sheetStyles.sheet} onPress={(event) => event.stopPropagation()}><View style={sheetStyles.handle} /><Text style={sheetStyles.title}>Добавить вложение</Text><Pressable style={sheetStyles.action} onPress={() => { setMediaPickerVisible(false); takePhoto(); }}><Text style={sheetStyles.actionIcon}>◉</Text><Text style={sheetStyles.actionText}>Камера</Text></Pressable><Pressable style={sheetStyles.action} onPress={() => { setMediaPickerVisible(false); pickMediaLibrary(); }}><Text style={sheetStyles.actionIcon}>▧</Text><Text style={sheetStyles.actionText}>Выбрать из медиатеки</Text></Pressable><Pressable style={sheetStyles.action} onPress={() => { setMediaPickerVisible(false); pickFile(); }}><Text style={sheetStyles.actionIcon}>▤</Text><Text style={sheetStyles.actionText}>Файлы</Text></Pressable><Pressable style={sheetStyles.cancel} onPress={() => setMediaPickerVisible(false)}><Text style={sheetStyles.cancelText}>Отмена</Text></Pressable></Pressable></Pressable>
  </Modal>
  <Modal visible={feedbackFor !== null} transparent animationType="fade" onRequestClose={() => setFeedbackFor(null)}>
    <Pressable style={sheetStyles.backdrop} onPress={() => setFeedbackFor(null)}><Pressable style={sheetStyles.sheet} onPress={(event) => event.stopPropagation()}><View style={sheetStyles.handle} /><Text style={sheetStyles.title}>Насколько полезен ответ?</Text><Pressable style={sheetStyles.action} onPress={() => feedbackFor && setFeedback(feedbackFor, "positive")}><Text style={sheetStyles.actionIcon}>👍</Text><Text style={sheetStyles.actionText}>Полезно</Text></Pressable><Pressable style={sheetStyles.action} onPress={() => feedbackFor && setFeedback(feedbackFor, "negative")}><Text style={sheetStyles.actionIcon}>👎</Text><Text style={sheetStyles.actionText}>Мимо</Text></Pressable></Pressable></Pressable>
  </Modal>
  <Modal visible={memoryVisible} animationType="slide" onRequestClose={() => setMemoryVisible(false)}>
    <SafeAreaView style={styles.memoryScreen}>
      <View style={styles.memoryHeader}><Text style={styles.memoryTitle}>Память</Text><Pressable style={premiumStyles.menuAction} onPress={() => { setMemoryVisible(false); setMenuVisible(true); }}><Text style={premiumStyles.menuActionText}>Назад</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable></View>
      <Text style={{ color: "#888", paddingHorizontal: 20, paddingBottom: 8, lineHeight: 20 }}>ALTER сама запоминает важные факты. Скажи в чате «запомни…», если хочешь сохранить что-то точно.</Text>
      {memoryLoading ? <ActivityIndicator color="#fff" /> : memoryError ? <Text style={styles.error}>{memoryError}</Text> : memorySections.length === 0 ? <Text style={styles.emptyMemory}>Пока здесь пусто. ALTER заполнит память по мере ваших разговоров.</Text> : <FlatList data={memorySections} keyExtractor={(item) => item.title} contentContainerStyle={styles.memoryList} renderItem={({ item }) => <View style={styles.memoryRow}><Text style={styles.memoryKey}>{item.title}</Text>{item.items.map((fact, index) => <Text key={item.title + index} style={styles.memoryValue}>{fact.label ? fact.label + ": " + fact.value : fact.value}</Text>)}</View>} />}
    </SafeAreaView>
  </Modal>
  <StatusBar style="light" /></SafeAreaView>;
}

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [introDone, setIntroDone] = useState(false);
  const [, setForegroundTick] = useState(0);
  useEffect(() => { AsyncStorage.getItem("alter_access_token").then((value) => { setToken(value); setLoading(false); }); }, []);
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") setTimeout(() => setForegroundTick((value) => value + 1), 0);
    });
    return () => subscription.remove();
  }, []);
  if (!introDone) return <IntroScreen onFinished={() => setIntroDone(true)} />;
  if (loading) return <SafeAreaView style={styles.container}><ActivityIndicator color="#ffffff" /></SafeAreaView>;
  return <NavigationContainer><Stack.Navigator screenOptions={{ headerShown: false }}>{token ? <Stack.Screen name="Chat">{() => <ChatScreen token={token} onLogout={() => { AsyncStorage.removeItem("alter_access_token"); setToken(null); }} />}</Stack.Screen> : <Stack.Screen name="Auth">{() => <AuthScreen onAuthenticated={setToken} />}</Stack.Screen>}</Stack.Navigator></NavigationContainer>;
}

const styles = StyleSheet.create({
  intro: { flex: 1, backgroundColor: "#050505", alignItems: "center", justifyContent: "center" }, introLogo: { color: "#fff", fontSize: 54, fontWeight: "800", letterSpacing: 8, textAlign: "center" }, introCaption: { color: "#666", fontSize: 9, letterSpacing: 3, textAlign: "center", marginTop: 12 }, introLine: { height: 1, backgroundColor: "#fff", opacity: 0.8, marginTop: 38 }, container: { flex: 1, backgroundColor: "#050505", justifyContent: "center" }, card: { margin: 24, gap: 14 }, title: { color: "#fff", fontSize: 42, fontWeight: "800", textAlign: "center", letterSpacing: 2 }, subtitle: { color: "#999", textAlign: "center", marginBottom: 18 }, input: { backgroundColor: "#151515", color: "#fff", borderRadius: 12, padding: 14, fontSize: 16, borderWidth: 1, borderColor: "#292929" }, error: { color: "#ff9d9d" }, chat: { flex: 1 }, header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 16 }, headerTitle: { color: "#fff", fontSize: 24, fontWeight: "800", letterSpacing: 2 }, menuButton: { padding: 8 }, menuIcon: { color: "#fff", fontSize: 20, letterSpacing: 3 }, modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.72)", alignItems: "flex-end", paddingTop: 56, paddingRight: 12 }, menuCard: { width: 290, backgroundColor: "#111", borderRadius: 18, padding: 20, gap: 12, borderWidth: 1, borderColor: "#2b2b2b" }, menuTitle: { color: "#fff", fontSize: 22, fontWeight: "700" }, menuEmail: { color: "#999" }, menuStatus: { color: "#ddd", fontSize: 14 }, menuDivider: { height: 1, backgroundColor: "#292929" }, messages: { padding: 16, gap: 10 }, bubble: { maxWidth: "86%", padding: 12, borderRadius: 16 }, userBubble: { alignSelf: "flex-end", backgroundColor: "#fff" }, userMessage: { color: "#050505" }, aiBubble: { alignSelf: "flex-start", backgroundColor: "#151515", borderWidth: 1, borderColor: "#292929" }, message: { color: "#fff", fontSize: 16, lineHeight: 23 }, cursor: { color: "#fff" }, composer: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12 }, composerInput: { flex: 1 }, memoryScreen: { flex: 1, backgroundColor: "#050505" }, memoryHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 20 }, memoryTitle: { color: "#fff", fontSize: 30, fontWeight: "700" }, memoryList: { padding: 20, gap: 14 }, memoryRow: { borderBottomWidth: 1, borderBottomColor: "#292929", paddingBottom: 14, gap: 6 }, memoryKey: { color: "#888", fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }, memoryValue: { color: "#eee", fontSize: 16, lineHeight: 23 }, emptyMemory: { color: "#999", padding: 24, fontSize: 16, lineHeight: 24 },
});

// Keep the composer surface pure black while retaining the native field size.
(styles as Record<string, unknown>).input = { ...StyleSheet.flatten(styles.input), backgroundColor: "#000000", borderColor: "#ffffff", borderWidth: StyleSheet.hairlineWidth };
(styles as Record<string, unknown>).aiBubble = { ...StyleSheet.flatten(styles.aiBubble), backgroundColor: "#000000", borderWidth: 0, borderColor: "transparent" };
(styles as Record<string, unknown>).messages = { ...StyleSheet.flatten(styles.messages), padding: 10, gap: 3 };
(styles as Record<string, unknown>).bubble = { ...StyleSheet.flatten(styles.bubble), padding: 8, maxWidth: "92%" };
(styles as Record<string, unknown>).intro = { ...StyleSheet.flatten(styles.intro), backgroundColor: "#050505" };
const reminderComposerStyle = { flexDirection: "row" as const, gap: 8, padding: 20, alignItems: "center" as const };

const planStyles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.88)", justifyContent: "center", padding: 18 },
  sheet: { backgroundColor: "#101010", borderRadius: 28, borderWidth: 1, borderColor: "#fff", padding: 20, gap: 12, shadowColor: "#fff", shadowOpacity: 0.35, shadowRadius: 28, elevation: 16 },
  title: { color: "#fff", fontSize: 28, fontWeight: "900", letterSpacing: 1 },
  subtitle: { color: "#aaa", fontSize: 13, lineHeight: 19, marginBottom: 4 },
  card: { backgroundColor: "#181818", borderRadius: 22, borderWidth: 1, borderColor: "#444", padding: 18, gap: 8 },
  featured: { borderColor: "#fff", shadowColor: "#fff", shadowOpacity: 0.28, shadowRadius: 18, elevation: 8 },
  badge: { color: "#fff", fontSize: 10, fontWeight: "800", letterSpacing: 1.3 },
  name: { color: "#fff", fontSize: 20, fontWeight: "800" },
  price: { color: "#fff", fontSize: 24, fontWeight: "900" },
  period: { color: "#999", fontSize: 12, fontWeight: "400" },
  features: { color: "#bbb", fontSize: 13, lineHeight: 19 },
  action: { color: "#fff", fontSize: 12, fontWeight: "900", letterSpacing: 1.4, marginTop: 4 },
  cancel: { color: "#fff", textAlign: "center", padding: 8, fontWeight: "700" },
});

const linkStyles = StyleSheet.create({
  link: { color: "#ffffff", textDecorationLine: "underline" },
});

const answerActionStyles = StyleSheet.create({
  row: { flexDirection: "row", gap: 12, marginTop: 10, alignItems: "center" }, button: { minWidth: 34, minHeight: 34, borderRadius: 17, paddingHorizontal: 5, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 4 }, voiceButton: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" }, pressed: { backgroundColor: "#262626", transform: [{ scale: 0.94 }] }, active: { backgroundColor: "#3a3a3a" },
  icon: { color: "#ffffff", fontSize: 16, paddingVertical: 2 }, selected: { color: "#ffffff" },
  hint: { color: "#ffffff", fontSize: 11 },
});

const idleStyles = StyleSheet.create({ shade: { ...StyleSheet.absoluteFillObject, backgroundColor: "#000", zIndex: 5 }, overlay: { ...StyleSheet.absoluteFillObject, zIndex: 6, backgroundColor: "#050505", alignItems: "center", justifyContent: "center", overflow: "hidden" }, logo: { fontSize: 52, letterSpacing: 8 }, line: { marginTop: 28 }, capabilityViewport: { width: "100%", overflow: "hidden", marginTop: 34, height: 190, justifyContent: "center" }, capabilities: { color: "#f4f4f4", fontSize: 13, lineHeight: 25, letterSpacing: 1.2, width: "100%", textAlign: "center" }, capabilityFade: { position: "absolute", left: 0, right: 0, height: 55, backgroundColor: "#050505" }, capabilityFadeTop: { top: 0 }, capabilityFadeBottom: { bottom: 0 } });

// The idle scene uses a soft matte black instead of absolute OLED black.
(idleStyles as Record<string, unknown>).overlay = { ...StyleSheet.flatten(idleStyles.overlay), backgroundColor: "#0b0b0b" };
(idleStyles as Record<string, unknown>).capabilityFade = { ...StyleSheet.flatten(idleStyles.capabilityFade), backgroundColor: "#0b0b0b" };
const historyStyles = StyleSheet.create({ handle: { position: "absolute", left: 0, top: 92, zIndex: 12, width: 38, height: 68, borderTopRightRadius: 34, borderBottomRightRadius: 34, backgroundColor: "#000000", alignItems: "center", justifyContent: "center", shadowColor: "#ffffff", shadowOpacity: 0.22, shadowRadius: 8, elevation: 5 }, arrow: { color: "#ffffff", fontSize: 36, fontWeight: "300" }, backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.72)", justifyContent: "flex-start" }, panel: { width: "86%", height: "72%", marginTop: 92, backgroundColor: "#000000", padding: 22, paddingTop: 24, borderTopRightRadius: 18, borderBottomRightRadius: 18 }, panelClose: { color: "#ffffff", fontSize: 32, fontWeight: "300", paddingVertical: 2 }, title: { color: "#ffffff", fontSize: 24, fontWeight: "700", marginBottom: 18 }, empty: { color: "#ffffff", opacity: 0.6, fontSize: 14 } });
(historyStyles as Record<string, unknown>).handle = { ...StyleSheet.flatten(historyStyles.handle), shadowOpacity: 0, shadowRadius: 0, elevation: 0 };
(historyStyles as Record<string, unknown>).panelClose = { ...StyleSheet.flatten(historyStyles.panelClose), position: "absolute", left: undefined, right: 0, top: 0, width: 72, height: 68, paddingHorizontal: 20, textAlign: "center" };
(historyStyles as Record<string, unknown>).panel = { ...StyleSheet.flatten(historyStyles.panel), width: "91%", height: "78%" };
const sheetStyles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "transparent" },
  sheet: { backgroundColor: "transparent", padding: 20, paddingBottom: 34, gap: 10, marginBottom: 78 },
  handle: { display: "none" },
  title: { color: "#fff", fontSize: 19, fontWeight: "800", marginBottom: 6 },
  action: { minHeight: 54, paddingHorizontal: 0, flexDirection: "row", alignItems: "center", gap: 14, backgroundColor: "transparent" },
  actionIcon: { display: "none" }, actionText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  cancel: { alignItems: "center", paddingVertical: 12 }, cancelText: { color: "#ffffff", fontWeight: "700" },
});

const authStyles = StyleSheet.create({
  primary: { backgroundColor: "#f7f4ff", borderRadius: 12, paddingVertical: 14, alignItems: "center" },
  primaryText: { color: "#17121f", fontWeight: "800", letterSpacing: 0.4 },
  secondary: { borderWidth: 1, borderColor: "#ffffff", borderRadius: 12, paddingVertical: 13, alignItems: "center" },
  secondaryText: { color: "#ffffff", fontWeight: "700" },
  legalRow: { flexDirection: "row", alignItems: "flex-start", gap: 8 }, check: { color: "#ffffff", fontSize: 22, lineHeight: 22 }, legalText: { color: "#aaa", flex: 1, fontSize: 12, lineHeight: 18 },
});

const permissionStyles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.82)", justifyContent: "center", padding: 24 },
  card: { backgroundColor: "#101010", borderRadius: 26, borderWidth: 1, borderColor: "#ffffff", padding: 24, shadowColor: "#ffffff", shadowOpacity: 0.45, shadowRadius: 24, elevation: 12 },
  kicker: { color: "#ffffff", fontSize: 11, letterSpacing: 2, fontWeight: "800", marginBottom: 14 },
  title: { color: "#fff", fontSize: 28, fontWeight: "800", letterSpacing: 0.4, marginBottom: 12 },
  body: { color: "#c9c5d4", fontSize: 15, lineHeight: 23, marginBottom: 22 },
  primary: { backgroundColor: "#f7f4ff", borderRadius: 14, paddingVertical: 15, alignItems: "center" },
  primaryText: { color: "#17121f", fontWeight: "800" },
  later: { color: "#aaa", textAlign: "center", paddingTop: 16, fontSize: 14 },
});

const premiumStyles = StyleSheet.create({
  drawerBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.58)", alignItems: "flex-start" },
  headerAction: { minWidth: 54, height: 40, alignItems: "center", justifyContent: "center" }, headerActionText: { color: "#ffffff", fontSize: 22 }, refreshAction: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" }, refreshIcon: { color: "#ffffff", fontSize: 27, fontWeight: "300" },
  newChatPrompt: { position: "absolute", top: 58, right: 14, zIndex: 10, flexDirection: "row", alignItems: "center", gap: 14, paddingVertical: 8, paddingHorizontal: 12, backgroundColor: "transparent" }, newChatPromptText: { color: "#ffffff", fontSize: 13 }, newChatActions: { flexDirection: "row", alignItems: "center", gap: 14 }, newChatAction: { color: "#ffffff", fontSize: 23, lineHeight: 24 },
  newChatLoading: { ...StyleSheet.absoluteFillObject, zIndex: 20, backgroundColor: "#050505", alignItems: "center", justifyContent: "center" }, newChatLoadingLogo: { color: "#ffffff", fontSize: 42, fontWeight: "900", letterSpacing: 8 }, newChatLoadingText: { color: "#888888", fontSize: 12, letterSpacing: 1, marginTop: 14 },
  menuCard: { width: "84%", height: "100%", backgroundColor: "#000000" },
  drawerContent: { flex: 1, paddingHorizontal: 22, paddingTop: 58, paddingBottom: 18 },
  drawerLogo: { color: "#fff", fontSize: 30, fontWeight: "900", letterSpacing: 7, marginBottom: 2 },
  drawerScroll: { paddingBottom: 34, gap: 12 },
  sectionHeader: { minHeight: 38, borderRadius: 10, paddingHorizontal: 4, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, sectionChevron: { color: "#ffffff", fontSize: 18 }, sectionBody: { gap: 8 },
  usageRow: { minHeight: 42, paddingHorizontal: 0, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, usageText: { color: "#ffffff", fontSize: 13, fontWeight: "700" },
  submenu: { marginTop: -4, marginLeft: 10, gap: 6, paddingLeft: 10 }, submenuAction: { minHeight: 42, paddingHorizontal: 0, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  menuAction: { minHeight: 48, paddingHorizontal: 0, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  menuActionText: { color: "#fff", fontSize: 15, fontWeight: "600", letterSpacing: 0.5 },
  menuActionArrow: { color: "#fff", fontSize: 20 },
  menuTitle: { color: "#fff", fontSize: 24, fontWeight: "800", letterSpacing: 2 },
  menuEmail: { color: "#fff", fontSize: 13, letterSpacing: 0.4 },
  menuStatus: { color: "#fff", fontSize: 14, letterSpacing: 0.2 },
  menuLogout: { backgroundColor: "transparent", borderColor: "#292632" },
  dangerAction: { borderColor: "#5b3042" },
  ownerBadge: { color: "#ffffff", fontSize: 12, fontWeight: "800", letterSpacing: 1.2, textAlign: "center", paddingVertical: 8 },
  sectionLabel: { color: "#ffffff", fontSize: 10, fontWeight: "800", letterSpacing: 1.6, marginTop: 6 }, version: { color: "#888888", fontSize: 11, letterSpacing: 1.2, textAlign: "center", paddingVertical: 4 },
  accountRow: { minHeight: 38, paddingHorizontal: 0, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
});

const activityStyles = StyleSheet.create({
  activityPill: { alignSelf: "center", flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 2, paddingHorizontal: 4, paddingVertical: 4, backgroundColor: "transparent" },
  activityDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#ffffff" },
  activityText: { color: "#ffffff", fontSize: 12, letterSpacing: 0.3 },
});

const mediaStyles = StyleSheet.create({
  attachmentChip: { marginHorizontal: 12, marginBottom: 2, padding: 9, borderRadius: 10, backgroundColor: "#1d1d1d", flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, generateAction: { color: "#ffffff", fontSize: 12, fontWeight: "700" },
  attachmentText: { color: "#ddd", fontSize: 13 }, removeAttachment: { color: "#fff", fontSize: 20, paddingLeft: 12 },
  attachButton: { width: 62, height: 38, alignItems: "center", justifyContent: "center" }, attachLabel: { color: "#ffffff", fontSize: 12 }, attachIcon: { color: "#ffffff", fontSize: 23, lineHeight: 24, includeFontPadding: false, textAlign: "center" },
  voiceHalo: { width: 34, height: 38, alignItems: "center", justifyContent: "center" }, voiceHaloActive: { opacity: 0.72 }, voiceButton: { width: 34, height: 38, alignItems: "center", justifyContent: "center" }, voiceButtonActive: { opacity: 0.72 }, voiceIcon: { color: "#ffffff", fontSize: 14, fontWeight: "800", letterSpacing: 0.8 },
  sendButton: { width: 34, height: 38, alignItems: "center", justifyContent: "center" }, sendIcon: { color: "#ffffff", fontSize: 21, fontWeight: "700" }, inputMask: { display: "none" }, inputGlow: { height: 0.5, backgroundColor: "#ffffff", opacity: 0.72, shadowColor: "#ffffff", shadowOpacity: 0.45, shadowRadius: 4, elevation: 2 },
});
