import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";
import * as Location from "expo-location";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import * as Notifications from "expo-notifications";
import { StatusBar } from "expo-status-bar";
import { AudioModule, AudioPlayer, AudioRecorder, RecordingPresets, createAudioPlayer, requestRecordingPermissionsAsync, setAudioModeAsync } from "expo-audio";
import * as ImagePicker from "expo-image-picker";
import * as Clipboard from "expo-clipboard";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Animated, AppState, Easing, FlatList, Image, Keyboard, KeyboardAvoidingView, LayoutAnimation, Linking, Modal, Platform, Pressable, ScrollView, Share, StyleSheet, Text, TextInput, UIManager, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { AccountResponse, LocationContext, MemoryResponse, MyDayResponse, api } from "./src/api/client";

type ScenarioItem = { id: string; title: string; prompt: string; mode: string };
type ActionItem = { action: string; status: string; at: string; route?: string; tool?: string };
const actionLabel = (item: ActionItem) => item.tool === "web_search" ? "Поиск в интернете" : ({ billing: "Работа с подпиской", memory: "Память", workflow: "Сценарий", chat: "Разговор", media: "Медиа" } as Record<string, string>)[item.action] || "Действие ALTER";
const actionStatusLabel = (status: string) => ({ ok: "Готово", success: "Готово", completed: "Готово", failure: "Не удалось", failed: "Не удалось", reserved: "Подготовлено", refunded: "Возвращено" } as Record<string, string>)[status] || "Обработано";
const memoryAuditLabel = (category: string) => ({ identity: "О тебе", health_sport: "Здоровье", food_drinks: "Еда и напитки", skills_career: "Навыки и работа", interests_hobbies: "Интересы", goals_habits: "Цели и привычки", relationships: "Отношения", preferences: "Предпочтения", important_events: "Важные события", open_loops: "Незавершённые темы" } as Record<string, string>)[category] || "Факт";
import { FAQ_TEXT } from "./src/faq";

const Stack = createNativeStackNavigator();
type AuthProps = { onAuthenticated: (token: string) => void };
type ChatItem = { id: string; role: string; text: string; createdAt?: number; mediaUri?: string; mediaMime?: string; mediaFilename?: string; audioUri?: string; audioMime?: string; audioFilename?: string; feedback?: "positive" | "negative"; streaming?: boolean };

export function userFacingError(error: unknown): string {
  const status = typeof error === "object" && error !== null && "status" in error ? Number((error as { status?: number }).status) : 0;
  const message = error instanceof Error ? error.message : "Не удалось выполнить запрос.";
  if (status === 401) return "Сессия закончилась. Войди в ALTER снова.";
  if (status === 402) return "Для этого действия нужна активная подписка.";
  if (status === 409) return "Запрос уже выполняется. Подожди результат.";
  if (status === 413) return "Файл слишком большой. Выбери файл меньшего размера.";
  if (status === 429) return "Лимит исчерпан. Попробуй позже.";
  if (status >= 500) return "Сервис временно недоступен. Попробуй ещё раз через минуту.";
  if (status === 0 && message === "Сетевая ошибка") return message;
  if (status === 0 && /сетевая|интернет/i.test(message)) return "Сетевая ошибка. Проверь интернет и попробуй ещё раз.";
  return "Не удалось выполнить запрос. Попробуй ещё раз позже.";
}
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
    let sound: AudioPlayer | null = null;
    const soundUrl = process.env.EXPO_PUBLIC_INTRO_SOUND_URL;
    if (soundUrl) {
      setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false }).then(async () => {
        sound = createAudioPlayer({ uri: soundUrl });
        sound.volume = 0.22;
        sound.play();
      }).catch(() => undefined);
    }
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 700, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 8, tension: 35, useNativeDriver: true }),
      Animated.timing(line, { toValue: 1, duration: 1500, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
    ]).start();
    const timer = setTimeout(() => {
      Animated.timing(opacity, { toValue: 0, duration: 420, useNativeDriver: true }).start(() => onFinished());
    }, 3200);
    return () => { clearTimeout(timer); if (sound) { sound.pause(); sound.remove(); } };
  }, [line, opacity, onFinished, scale]);

  return <View style={[styles.intro, { backgroundColor: "#050505" }]}><Animated.View style={{ opacity, transform: [{ scale }] }}><Text style={styles.introLogo}>ALTER</Text><Text style={styles.introCaption}>ТВОЙ ЛИЧНЫЙ ПОМОЩНИК</Text><Text style={[styles.introCaption, { marginTop: 14 }]}>ПАМЯТЬ · ГОЛОС · МЕДИА · ПОИСК · ЗАДАЧИ</Text></Animated.View><Animated.View style={[styles.introLine, { width: line.interpolate({ inputRange: [0, 1], outputRange: [0, 150] }) }]} /><StatusBar style="light" /></View>;
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

function ThinkingDots() {
  const opacity = React.useRef(new Animated.Value(0.35)).current;
  useEffect(() => {
    const animation = Animated.loop(Animated.sequence([
      Animated.timing(opacity, { toValue: 1, duration: 650, useNativeDriver: true }),
      Animated.timing(opacity, { toValue: 0.35, duration: 650, useNativeDriver: true }),
    ]));
    animation.start();
    return () => animation.stop();
  }, [opacity]);
  return <Animated.Text style={[styles.thinkingDots, { opacity }]}>•••</Animated.Text>;
}

function EmptyChat({ onPrompt }: { onPrompt: (value: string) => void }) {
  const prompts = [
    ["Мой день", "Собери мне реалистичный план на сегодня"],
    ["Разобрать идею", "Помоги разобрать мою идею по шагам"],
    ["Найти и сравнить", "Найди и сравни лучшие варианты"],
    ["Запомнить", "Запомни это обо мне: "]
  ];
  return <View style={styles.emptyChat}>
    <Text style={styles.emptyLogo}>ALTER</Text>
    <Text style={styles.emptyTitle}>Твой контекст уже здесь</Text>
    <Text style={styles.emptySubtitle}>Напиши, скажи голосом или прикрепи фото. ALTER поможет разобраться и довести дело до результата.</Text>
    <Pressable style={styles.alterLoopCard} onPress={() => onPrompt("Помоги мне выбрать важное дело, составь план на сегодня и напомни вернуться к нему позже.")}><Text style={styles.alterLoopKicker}>ALTER LOOP</Text><Text style={styles.alterLoopTitle}>Помнит → планирует → возвращает</Text><Text style={styles.alterLoopText}>Скажи, что важно. ALTER сохранит контекст, разложит следующий шаг и поможет не потерять его.</Text></Pressable>
    <View style={styles.quickPromptGrid}>{prompts.map(([title, prompt]) => <Pressable key={title} style={({ pressed }) => [styles.quickPrompt, pressed && styles.quickPromptPressed]} onPress={() => onPrompt(prompt)}><Text style={styles.quickPromptTitle}>{title}</Text><Text style={styles.quickPromptText}>{prompt}</Text></Pressable>)}</View>
    <Text style={styles.emptyHint}>Память · голос · фото · поиск · напоминания</Text>
  </View>;
}

function LegacyIdleAlterScreen({ opacity }: { opacity: Animated.Value }) {
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
  const capabilities = "память\nживой диалог\nголосовые ответы\nфото и видео\nсоздание изображений\nпоиск и музыка\nпогода и напоминания\nзабота о важном\nобщий контекст\nALTER рядом";
  return <Animated.View pointerEvents="none" style={[idleStyles.overlay, { opacity, zIndex: 20, backgroundColor: "#050505" }]}>
    <Animated.Text style={[styles.introLogo, idleStyles.logo, { opacity: pulse }]}>ALTER</Animated.Text>
    <Animated.View style={[styles.introLine, idleStyles.line, { width: line.interpolate({ inputRange: [0, 1], outputRange: [0, 150] }) }]} />
    <View style={idleStyles.capabilityViewport}><Animated.Text style={[idleStyles.capabilities, { transform: [{ translateY: drift.interpolate({ inputRange: [-1, 0], outputRange: [-320, 230] }) }] }]}>{capabilities}</Animated.Text><View pointerEvents="none" style={[idleStyles.capabilityFade, idleStyles.capabilityFadeTop]} /><View pointerEvents="none" style={[idleStyles.capabilityFade, idleStyles.capabilityFadeBottom]} /></View><View style={{ width: "100%", overflow: "hidden", marginTop: 12, gap: 4 }}><Animated.Text style={{ color: "#777777", fontSize: 9, letterSpacing: 2, width: 700, textAlign: "center", transform: [{ translateX: drift.interpolate({ inputRange: [-1, 0], outputRange: [-360, 260] }) }] }}>ALTER · 2026 · ™</Animated.Text><Animated.Text style={{ color: "#666666", fontSize: 8, letterSpacing: 2, width: 700, textAlign: "center", transform: [{ translateX: drift.interpolate({ inputRange: [-1, 0], outputRange: [260, -360] }) }] }}>ЛИЧНЫЙ ПОМОЩНИК</Animated.Text></View>
    <View pointerEvents="none" style={{ position: "absolute", left: 0, right: 0, bottom: 18, height: 28, backgroundColor: "#050505", alignItems: "center", justifyContent: "center", overflow: "hidden" }}><Animated.Text style={{ color: "#777777", fontSize: 9, letterSpacing: 2, width: 900, textAlign: "center", transform: [{ translateX: drift.interpolate({ inputRange: [-1, 0], outputRange: [-520, 300] }) }] }}>ALTER · ЛИЧНЫЙ ПОМОЩНИК · 2026</Animated.Text></View>
  </Animated.View>;
}

function IdleAlterScreen({ opacity }: { opacity: Animated.Value }) {
  const pulse = React.useRef(new Animated.Value(0.78)).current;
  const line = React.useRef(new Animated.Value(0)).current;
  const drift = React.useRef(new Animated.Value(0)).current;
  const date = new Date().toLocaleDateString("ru-RU");
  useEffect(() => {
    const pulseLoop = Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 1, duration: 2200, useNativeDriver: true }),
      Animated.timing(pulse, { toValue: 0.78, duration: 2200, useNativeDriver: true }),
    ]));
    const lineLoop = Animated.loop(Animated.sequence([
      Animated.timing(line, { toValue: 1, duration: 2600, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
      Animated.timing(line, { toValue: 0, duration: 2600, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
    ]));
    const driftLoop = Animated.loop(Animated.sequence([
      Animated.timing(drift, { toValue: -1, duration: 36000, easing: Easing.linear, useNativeDriver: true }),
      Animated.timing(drift, { toValue: 0, duration: 1, useNativeDriver: true }),
    ]));
    pulseLoop.start(); lineLoop.start(); driftLoop.start();
    return () => { pulseLoop.stop(); lineLoop.stop(); driftLoop.stop(); };
  }, [drift, line, pulse]);
  const capabilities = "память · цели · новый разговор · текст · голос · фото · видео · изображения · редактирование · поиск в интернете · источники · погода · напоминания · календарь · забота · уведомления";
  return <Animated.View pointerEvents="none" style={[idleStyles.cleanOverlay, { opacity }]}>
    <Animated.Text style={[styles.introLogo, idleStyles.cleanLogo, { opacity: pulse }]}>ALTER</Animated.Text>
    <Animated.View style={[styles.introLine, idleStyles.cleanLine, { width: line.interpolate({ inputRange: [0, 1], outputRange: [0, 150] }) }]} />
    <View style={idleStyles.cleanCapabilityViewport}><Animated.Text style={[idleStyles.cleanCapabilities, { transform: [{ translateY: drift.interpolate({ inputRange: [-1, 0], outputRange: [-70, 70] }) }] }]}>{capabilities}</Animated.Text></View>
    <View style={idleStyles.cleanMeta}>
      <Text numberOfLines={1} adjustsFontSizeToFit style={idleStyles.cleanMetaText}>{date} · ALTER · ЛИЧНЫЙ ПОМОЩНИК</Text>
    </View>
  </Animated.View>;
}

export function VoiceButton({ onRecorded, onRecordingChange }: { onRecorded: (uri: string) => void; onRecordingChange?: (active: boolean) => void }) {
  const [recording, setRecording] = useState<AudioRecorder | null>(null);
  const pulse = React.useRef(new Animated.Value(1)).current;
  const pulseLoop = React.useRef<Animated.CompositeAnimation | null>(null);
  const start = async () => {
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) return;
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    // Voice messages do not need music-grade stereo quality. The lower bitrate
    // keeps long recordings comfortably below the upload limit while the
    // backend normalizes them to mono WAV before transcription.
    const recorder = new AudioModule.AudioRecorder(RecordingPresets.LOW_QUALITY);
    await recorder.prepareToRecordAsync();
    recorder.record();
    setRecording(recorder);
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
    await current.stop();
    const uri = current.uri;
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
  const [myDayVisible, setMyDayVisible] = useState(false);
  const [myDayData, setMyDayData] = useState<MyDayResponse | null>(null);
  const [myDayLoading, setMyDayLoading] = useState(false);
  const [scenariosVisible, setScenariosVisible] = useState(false);
  const [scenarios, setScenarios] = useState<ScenarioItem[]>([]);
  const [workflowData, setWorkflowData] = useState<Record<string, unknown> | null>(null);
  const [actionLogVisible, setActionLogVisible] = useState(false);
  const [actionLog, setActionLog] = useState<ActionItem[]>([]);
  const [faqVisible, setFaqVisible] = useState(false);
  const [legalVisible, setLegalVisible] = useState(false);
  const [legalChecked, setLegalChecked] = useState(false);
  const [legalBusy, setLegalBusy] = useState(false);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memoryError, setMemoryError] = useState("");
  const [memoryNotice, setMemoryNotice] = useState(false);
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
  const [privateMode, setPrivateMode] = useState(false);
  const [ttsVoice, setTtsVoice] = useState("alloy");
  const [voiceMenuOpen, setVoiceMenuOpen] = useState(false);
  const [voiceCreatorVisible, setVoiceCreatorVisible] = useState(false);
  const [voiceDescription, setVoiceDescription] = useState("");
  const [emailVisible, setEmailVisible] = useState(false);
  const [openSection, setOpenSection] = useState<"profile" | "connections" | "tools" | "settings" | null>(null);
  const [usage, setUsage] = useState<{ used: number; limit: number; remaining: number } | null>(null);
  const [mediaPickerVisible, setMediaPickerVisible] = useState(false);
  const [feedbackFor, setFeedbackFor] = useState<string | null>(null);
  const [idle, setIdle] = useState(false);
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [attachment, setAttachment] = useState<{ uri: string; type: "image" | "video" | "audio" } | null>(null);
  const [activity, setActivity] = useState<"" | "thinking" | "analyzing" | "searching" | "planning" | "recording">("");
  const [location, setLocation] = useState<LocationContext | null>(null);
  const listRef = React.useRef<FlatList<ChatItem>>(null);
  const activeVoiceSound = React.useRef<AudioPlayer | null>(null);
  const voicePlaybackSerial = React.useRef(0);
  const autoScrollAfterUpdate = React.useRef(false);
  const activeRequestController = React.useRef<AbortController | null>(null);
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
    }, 180000);
  }, [idleShade]);
  const showPermissionOfferIfNeeded = () => { AsyncStorage.getItem(`alter_permission_offer_seen_${token}`).then((value) => { if (value !== "1") setPermissionOfferVisible(true); }).catch(() => setPermissionOfferVisible(true)); };
  const refreshAccount = () => { api.account(token).then((value) => { setAccount(value); if (value.legal_accepted) showPermissionOfferIfNeeded(); else setLegalVisible(true); }).catch(() => undefined); };
  useEffect(() => {
    refreshAccount();
    api.usage(token).then(setUsage).catch(() => undefined);
    api.settings(token).then(({ settings, checkins_enabled }) => {
      setCheckinsEnabled(checkins_enabled);
      setVoiceReplies(settings.voice_replies === true);
      setAutoVoiceReplies(settings.voice_auto_replies === true);
      setPrivateMode(settings.private_mode === true);
      if (typeof settings.tts_voice === "string") setTtsVoice(settings.tts_voice);
    }).catch(() => undefined);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") refreshAccount();
    });
    return () => subscription.remove();
  }, [token]);
  useEffect(() => {
    api.history(token).then((result) => setItems(result.messages.filter((item) => item.role === "user" || item.role === "assistant").map((item, index) => ({ id: `history-${index}`, role: item.role, text: item.content })))).catch(() => undefined);
  }, [token]);
  useEffect(() => {
    const key = `alter_draft_${token}`;
    AsyncStorage.getItem(key).then((draft) => { if (draft) setMessage((current) => current || draft); }).catch(() => undefined);
  }, [token]);
  useEffect(() => {
    const key = `alter_draft_${token}`;
    if (message.trim()) AsyncStorage.setItem(key, message).catch(() => undefined);
    else AsyncStorage.removeItem(key).catch(() => undefined);
  }, [message, token]);
  useEffect(() => {
    if (items.length > 0) api.memory(token).then(setMemoryData).catch(() => undefined);
  }, [token, items.length]);
  useEffect(() => { api.workflow(token).then(({ workflow }) => setWorkflowData(workflow)).catch(() => undefined); }, [token]);
  useEffect(() => {
    const latestUser = [...items].reverse().find((item) => item.role === "user");
    if (latestUser && /запомни|помни|не забывай/i.test(latestUser.text)) {
      setMemoryNotice(true);
      const timer = setTimeout(() => setMemoryNotice(false), 5000);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [items]);
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
  useEffect(() => { resetIdle(); return () => { if (idleTimer.current) clearTimeout(idleTimer.current); voicePlaybackSerial.current += 1; const sound = activeVoiceSound.current; activeVoiceSound.current = null; if (sound) { sound.pause(); sound.remove(); } }; }, [resetIdle]);
  const stopRequest = () => {
    activeRequestController.current?.abort();
    activeRequestController.current = null;
  };
  const stopVoicePlayback = async () => {
    voicePlaybackSerial.current += 1;
    const sound = activeVoiceSound.current;
    activeVoiceSound.current = null;
    if (sound) {
      try { sound.pause(); } catch { /* already stopped */ }
      try { sound.remove(); } catch { /* already unloaded */ }
    }
    setPlayingVoiceId(null);
  };
  const playVoiceReply = async (text: string, id?: string) => {
    await stopVoicePlayback();
    const serial = voicePlaybackSerial.current;
    setPlayingVoiceId(id || "manual");
    try {
      const blob = await api.voiceReply(token, text);
      const dataUrl = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onloadend = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(blob); });
      if (serial !== voicePlaybackSerial.current) return;
      await playAudioBase64(dataUrl.split(",", 2)[1], "wav", id, serial);
    } catch (err) { setPlayingVoiceId(null); setMenuError(err instanceof Error ? err.message : "Не удалось озвучить ответ"); }
  };
  const playAudioBase64 = async (base64: string, extension = "mp3", id?: string, serial?: number) => {
    if (!base64 || !FileSystem.cacheDirectory) throw new Error("Аудиофайл пустой");
    if (serial === undefined) {
      await stopVoicePlayback();
      serial = voicePlaybackSerial.current;
    }
    setPlayingVoiceId(id || "audio-action");
    const uri = `${FileSystem.cacheDirectory}alter-audio-${Date.now()}.${extension}`;
    await FileSystem.writeAsStringAsync(uri, base64, { encoding: FileSystem.EncodingType.Base64 });
    // Recording enables the iOS receiver route and can leave subsequent TTS
    // playback extremely quiet. Explicitly restore speaker playback before
    // every voice response; this also prevents Android earpiece routing.
    await setAudioModeAsync({
      allowsRecording: false,
      playsInSilentMode: true,
      shouldPlayInBackground: false,
      shouldRouteThroughEarpiece: false,
    });
    if (serial !== voicePlaybackSerial.current) return;
    const player = createAudioPlayer({ uri });
    player.volume = 1.0;
    if (serial !== voicePlaybackSerial.current) {
      player.remove();
      return;
    }
    activeVoiceSound.current = player;
    player.addListener("playbackStatusUpdate", (status) => {
      if (status.didJustFinish) {
        if (activeVoiceSound.current === player) activeVoiceSound.current = null;
        setPlayingVoiceId(null);
        player.remove();
      }
    });
    player.play();
  };
  const downloadMedia = async (item: ChatItem, kind: "media" | "audio" = "media") => {
    const uriValue = kind === "audio" ? item.audioUri : item.mediaUri;
    const mime = kind === "audio" ? item.audioMime : item.mediaMime;
    const itemFilename = kind === "audio" ? item.audioFilename : item.mediaFilename;
    if (!uriValue || !FileSystem.documentDirectory) return;
    try {
      const comma = uriValue.indexOf(",");
      const base64 = comma >= 0 ? uriValue.slice(comma + 1) : uriValue;
      const filename = itemFilename || `alter-${Date.now()}.${(mime || "application/octet-stream").split("/")[1] || "bin"}`;
      const uri = `${FileSystem.documentDirectory}${filename.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
      await FileSystem.writeAsStringAsync(uri, base64, { encoding: FileSystem.EncodingType.Base64 });
      await Share.share({ url: uri, title: filename, message: Platform.OS === "android" ? uri : undefined });
    } catch (err) {
      setMenuError(err instanceof Error ? err.message : "Не удалось сохранить файл");
    }
  };
  const editMedia = async (item: ChatItem) => {
    if (!item.mediaUri || !item.mediaMime?.startsWith("image/") || !FileSystem.cacheDirectory) return;
    try {
      const comma = item.mediaUri.indexOf(",");
      const base64 = comma >= 0 ? item.mediaUri.slice(comma + 1) : item.mediaUri;
      const uri = `${FileSystem.cacheDirectory}alter-edit-${Date.now()}.png`;
      await FileSystem.writeAsStringAsync(uri, base64, { encoding: FileSystem.EncodingType.Base64 });
      setAttachment({ uri, type: "image" });
      setMessage("");
    } catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось подготовить изображение к редактированию"); }
  };
  const editMediaNow = async (item: ChatItem) => {
    if (!item.mediaUri || !item.mediaMime?.startsWith("image/") || busy) return;
    setBusy(true); setActivity("analyzing");
    try {
      const result = await api.generateMedia(token, "", item.mediaUri, "image");
      setItems((old) => [...old, { id: `${Date.now()}g`, role: "assistant", text: "Готово — создал заметно изменённый вариант изображения.", mediaUri: `data:${result.media_type};base64,${result.data_base64}`, mediaMime: result.media_type, mediaFilename: result.filename }]);
      autoScrollAfterUpdate.current = true;
    } catch (err) { setItems((old) => [...old, { id: `${Date.now()}e`, role: "assistant", text: userFacingError(err) }]); }
    finally { setBusy(false); setActivity(""); }
  };
  const send = async (presetText?: string) => {
    const text = (presetText ?? message).trim(); if ((!text && !attachment) || busy) return;
    const currentAttachment = attachment;
    const controller = new AbortController();
    activeRequestController.current = controller;
    const userMessageId = `${Date.now()}u`;
    const pendingId = `${Date.now()}p`;
    autoScrollAfterUpdate.current = true;
    Keyboard.dismiss(); setMessage(""); setAttachment(null); setItems((old) => [...old, { id: userMessageId, role: "user", text: currentAttachment?.type === "audio" ? "Голосовое сообщение" : currentAttachment ? `${text || "Вложение"} · ${currentAttachment.type}` : text }, { id: pendingId, role: "assistant", text: "" }]); setBusy(true); setActivity(currentAttachment ? "analyzing" : /найди|поищи|проверь|актуальн|новост|цену|погода/i.test(text) ? "searching" : /план|составь|распиши|подготовь|организуй/i.test(text) ? "planning" : "analyzing");
    try { const result = currentAttachment ? await api.sendMedia(token, text, currentAttachment.uri, currentAttachment.type) : await api.sendMessageStream(token, text, location, (partial) => setItems((old) => old.map((item) => item.id === pendingId ? { ...item, text: partial, streaming: true } : item)), controller.signal); if (currentAttachment?.type === "audio" && result.transcript) setItems((old) => old.map((item) => item.id === userMessageId ? { ...item, text: result.transcript! } : item)); autoScrollAfterUpdate.current = true; const answerId = `${Date.now()}a`; const outputAudio = result.audio_base64 ? { audioUri: `data:${result.audio_mime || "audio/mpeg"};base64,${result.audio_base64}`, audioMime: result.audio_mime || "audio/mpeg", audioFilename: result.audio_filename || "alter-audio.mp3" } : {}; const outputMedia = result.media_base64 ? { mediaUri: `data:${result.media_mime || "application/octet-stream"};base64,${result.media_base64}`, mediaMime: result.media_mime, mediaFilename: result.media_filename } : {}; setItems((old) => [...old.filter((item) => item.id !== pendingId), { id: answerId, role: "assistant", text: result.reply, ...outputAudio, ...outputMedia }]); if (result.audio_base64) await playAudioBase64(result.audio_base64, result.audio_filename?.endsWith(".wav") ? "wav" : "mp3", answerId); else if (voiceReplies && autoVoiceReplies) playVoiceReply(result.reply, answerId); }
    catch (err) { if ((err as { name?: string })?.name === "AbortError") setItems((old) => old.filter((item) => item.id !== pendingId)); else { if (text) setMessage((current) => current || text); setItems((old) => old.map((item) => item.id === pendingId ? { ...item, text: userFacingError(err) } : item)); } }
    finally { if (activeRequestController.current === controller) activeRequestController.current = null; setBusy(false); setActivity(""); }
  };
  const promptFromHistory = (id: string) => {
    const index = items.findIndex((item) => item.id === id);
    return index >= 0 ? [...items.slice(0, index)].reverse().find((item) => item.role === "user")?.text : undefined;
  };
  const generateAttachment = async () => {
    if (!attachment || attachment.type === "audio" || busy) return;
    const current = attachment;
    const kind = current.type as "image" | "video";
    setBusy(true); setActivity("analyzing");
    try {
      const result = await api.generateMedia(token, message.trim(), current.uri, kind);
      setItems((old) => [...old, { id: `${Date.now()}g`, role: "assistant", text: "Готово.", mediaUri: `data:${result.media_type};base64,${result.data_base64}`, mediaMime: result.media_type, mediaFilename: result.filename }]);
      setMessage(""); setAttachment(null); autoScrollAfterUpdate.current = true;
    } catch (err) { setItems((old) => [...old, { id: `${Date.now()}e`, role: "assistant", text: userFacingError(err) }]); }
    finally { setBusy(false); setActivity(""); }
  };
  const openTelegramLink = async () => {
    setMenuError("");
    try { const result = await api.startTelegramLink(token); await Linking.openURL(result.url); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось открыть Telegram"); }
  };
  const openCalendarConnect = async () => {
    setMenuError("");
    try { const result = await api.calendarConnect(token); await Linking.openURL(result.authorization_url); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Google Calendar пока не настроен на сервере"); }
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
  const acceptLegal = async () => {
    if (!legalChecked || legalBusy) return;
    setLegalBusy(true); setMenuError("");
    try { await api.acceptLegal(token); setAccount((value) => value ? { ...value, legal_accepted: true } : value); setLegalVisible(false); showPermissionOfferIfNeeded(); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось сохранить согласие"); }
    finally { setLegalBusy(false); }
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
  const openMyDay = async () => {
    setMyDayVisible(true); setMyDayLoading(true); setMenuVisible(false);
    try { setMyDayData(await api.myDay(token)); } catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось собрать твой день"); }
    finally { setMyDayLoading(false); }
  };
  const forgetMemoryCategory = (category: string, title: string) => Alert.alert("Забыть категорию?", `Удалить из памяти «${title}»?`, [
    { text: "Отмена", style: "cancel" },
    { text: "Забыть", style: "destructive", onPress: async () => {
      try { await api.forgetMemoryCategory(token, category); setMemoryData((current) => current ? { sections: current.sections.filter((section) => section.category !== category) } : current); }
      catch (err) { setMemoryError(userFacingError(err)); }
    } },
  ]);
  const clearMemory = () => Alert.alert("Очистить память?", "Удалятся сохранённые факты, цели и предпочтения. История чатов останется.", [
    { text: "Отмена", style: "cancel" },
    { text: "Очистить", style: "destructive", onPress: async () => {
      try { await api.clearMemory(token); setMemoryData({ sections: [] }); }
      catch (err) { setMemoryError(userFacingError(err)); }
    } },
  ]);
  const clearContext = () => Alert.alert("Очистить контекст?", "Удалятся найденные фрагменты прошлых разговоров. Факты о тебе останутся.", [
    { text: "Отмена", style: "cancel" }, { text: "Очистить", style: "destructive", onPress: async () => {
      try { await api.clearContext(token); setMemoryData((current) => current ? { sections: current.sections.filter((section) => section.category !== "episodic_context") } : current); }
      catch (err) { setMemoryError(userFacingError(err)); }
    } },
  ]);
  const confirmMemoryFact = async (category: string, key: string) => {
    try {
      await api.confirmMemory(token, category, key);
      setMemoryData((current) => current ? { ...current, audit: (current.audit || []).map((item) => item.category === category && item.key === key ? { ...item, confirmed: true } : item) } : current);
    } catch (err) { setMemoryError(userFacingError(err)); }
  };
  const openReminders = async () => {
    setRemindersVisible(true); setMenuVisible(false);
    try { setReminders((await api.reminders(token)).reminders); } catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось загрузить напоминания"); }
  };
  const openFaq = () => { setFaqVisible(true); setMenuVisible(false); };
  const openScenarios = async () => { setMenuVisible(false); setScenariosVisible(true); try { setScenarios((await api.scenarios(token)).items); } catch { setScenarios([]); } };
  const openActionLog = async () => { setMenuVisible(false); setActionLogVisible(true); try { setActionLog((await api.actionLog(token)).items as ActionItem[]); } catch { setActionLog([]); } };
  const createQuickReminder = async () => {
    const text = reminderText.trim(); if (!text) return;
    try { const item = await api.createReminder(token, text, new Date(Date.now() + 60 * 60 * 1000).toISOString()); setReminders((old) => [...old, item]); setReminderText(""); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось создать напоминание"); }
  };
  const toggleCheckins = async () => {
    const next = !checkinsEnabled; setCheckinsEnabled(next);
    try { await api.setCheckins(token, next); } catch (err) { setCheckinsEnabled(!next); setMenuError(err instanceof Error ? err.message : "Не удалось изменить check-in"); }
  };
  const createVoice = async () => {
    const description = voiceDescription.trim();
    if (!description || busy) return;
    setBusy(true); setMenuError("");
    try {
      const result = await api.voiceGeneration(token, description);
      if (typeof result.voice_id !== "string" || !result.voice_id.trim()) throw new Error("Сервис не вернул идентификатор созданного голоса");
      setVoiceCreatorVisible(false); setVoiceDescription("");
      setItems((old) => [...old, { id: `${Date.now()}voice`, role: "assistant", text: "Голос создан и сохранён. Прикрепи голосовое и напиши: «измени мой голос на созданный»." }]);
    } catch (err) { setMenuError(userFacingError(err)); }
    finally { setBusy(false); }
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
    const answerIndex = items.findIndex((item) => item.id === id);
    const answer = items[answerIndex];
    const question = answerIndex > 0 ? [...items.slice(0, answerIndex)].reverse().find((item) => item.role === "user") : undefined;
    setItems((old) => old.map((item) => item.id === id ? { ...item, feedback } : item)); setFeedbackFor(null);
    try {
      const { settings } = await api.settings(token);
      const previous = Array.isArray(settings.reply_feedback) ? settings.reply_feedback : [];
      await api.updateSettings(token, { reply_feedback: [...previous, { rating: feedback, answer: answer?.text?.slice(0, 700), question: question?.text?.slice(0, 300), at: new Date().toISOString() }].slice(-100) });
    } catch { /* Rating is optional; keep the local acknowledgement. */ }
  };
  const startNewChat = async () => { if (busy || newChatLoading) return; setNewChatPromptVisible(false); setNewChatLoading(true); try { await api.newSession(token); setItems([]); setMessage(""); setAttachment(null); setMenuVisible(false); resetIdle(); } catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось начать новый чат"); } finally { setNewChatLoading(false); } };
  const memorySections = memoryData?.sections || [];
  const workflowStep = typeof workflowData?.current_step_title === "string" ? workflowData.current_step_title : "";
  const workflowGoal = typeof workflowData?.goal === "string" ? workflowData.goal : "";
  const workflowProgress = `${Number(workflowData?.completed_steps || 0)}/${Number(workflowData?.total_steps || 0)}`;
  const maskedEmail = account?.email ? account.email.replace(/^(.{2}).*(@.*)$/, "$1•••$2") : "Почта не указана";
  return <SafeAreaView style={[styles.container, { backgroundColor: "#000000" }]} onTouchStart={resetIdle}>{idle ? <><Animated.View pointerEvents="none" style={[idleStyles.shade, { opacity: idleShade }]} /><IdleAlterScreen opacity={idleShade} /></> : null}<Pressable style={historyStyles.handle} onPress={() => setHistoryVisible(true)} accessibilityLabel="Открыть историю переписки"><Text style={historyStyles.arrow}>›</Text></Pressable><KeyboardAvoidingView style={styles.chat} behavior={Platform.OS === "ios" ? "padding" : undefined}>
    <View style={styles.header}><Pressable style={premiumStyles.headerAction} onPress={() => { Keyboard.dismiss(); refreshAccount(); setMenuVisible(true); }} accessibilityLabel="Открыть боковую панель"><Text style={premiumStyles.headerActionText}>☰</Text></Pressable><Text style={styles.headerTitle}>ALTER</Text><Pressable style={premiumStyles.refreshAction} onPress={() => setNewChatPromptVisible((value) => !value)} accessibilityLabel="Новый чат"><Text style={premiumStyles.refreshIcon}>↻</Text></Pressable></View>
    {newChatPromptVisible ? <View style={premiumStyles.newChatPrompt}><Text style={premiumStyles.newChatPromptText}>Начать новый чат?</Text><View style={premiumStyles.newChatActions}><Pressable onPress={() => setNewChatPromptVisible(false)} accessibilityLabel="Отменить новый чат"><Text style={premiumStyles.newChatAction}>×</Text></Pressable><Pressable onPress={startNewChat} accessibilityLabel="Подтвердить новый чат"><Text style={premiumStyles.newChatAction}>✓</Text></Pressable></View></View> : null}
    {newChatLoading ? <View style={premiumStyles.newChatLoading} pointerEvents="none"><Animated.Text style={[premiumStyles.newChatLoadingLogo, { opacity: logoPulse }]}>ALTER</Animated.Text><Text style={premiumStyles.newChatLoadingText}>Начинаем новый чат</Text></View> : null}
    {items.length === 0 ? <EmptyChat onPrompt={(value) => { setMessage(value); resetIdle(); }} /> : null}
    <FlatList ref={listRef} data={items} keyExtractor={(item) => item.id} contentContainerStyle={styles.messages} keyboardShouldPersistTaps="handled" keyboardDismissMode="interactive" automaticallyAdjustKeyboardInsets onContentSizeChange={() => { if (autoScrollAfterUpdate.current) { autoScrollAfterUpdate.current = false; requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true })); } }} renderItem={({ item }) => <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.aiBubble]}>{item.role === "assistant" ? <>{item.text ? (item.streaming ? <Text style={styles.message}>{item.text}<Text style={styles.cursor}>▋</Text></Text> : <TypingText text={item.text} />) : <ThinkingDots />}{item.text && !item.streaming ? <View style={answerActionStyles.row}><Pressable onPress={() => { const prompt = promptFromHistory(item.id); if (prompt) send(prompt); }} style={({ pressed }) => [answerActionStyles.button, pressed && answerActionStyles.pressed]} accessibilityLabel="Повторить запрос"><Text style={answerActionStyles.icon}>↻</Text></Pressable><Pressable onPress={() => send("Продолжи последний ответ, добавив следующий практический шаг.")} style={({ pressed }) => [answerActionStyles.button, pressed && answerActionStyles.pressed]} accessibilityLabel="Продолжить ответ"><Text style={answerActionStyles.icon}>→</Text></Pressable><Pressable onPress={async () => { await Clipboard.setStringAsync(item.text); setCopiedId(item.id); setTimeout(() => setCopiedId(null), 1600); }} style={({ pressed }) => [answerActionStyles.button, pressed && answerActionStyles.pressed]} accessibilityLabel="Скопировать ответ"><Text style={answerActionStyles.icon}>{copiedId === item.id ? "✓" : "⧉"}</Text>{copiedId === item.id ? <Text style={answerActionStyles.hint}>Скопировано</Text> : null}</Pressable><Pressable onPress={() => playVoiceReply(item.text, item.id)} disabled={playingVoiceId !== null} style={({ pressed }) => [answerActionStyles.voiceButton, pressed && answerActionStyles.pressed, playingVoiceId === item.id && answerActionStyles.active]} accessibilityLabel="Озвучить ответ"><Text style={answerActionStyles.icon}>{playingVoiceId === item.id ? "◼" : "◖))"}</Text></Pressable><Pressable onPress={() => setFeedbackFor(item.id)} style={({ pressed }) => [answerActionStyles.button, pressed && answerActionStyles.pressed]} accessibilityLabel="Оценить ответ"><Text style={[answerActionStyles.icon, item.feedback ? answerActionStyles.selected : null]}>{item.feedback === "positive" ? "👍" : item.feedback === "negative" ? "👎" : "♡"}</Text></Pressable></View> : null}</> : <Text style={[styles.message, styles.userMessage, { color: "#050505" }]}>{item.text}</Text>}{item.mediaUri && item.mediaMime?.startsWith("image/") ? <Image source={{ uri: item.mediaUri }} style={{ width: 240, height: 240, borderRadius: 12, marginTop: 8 }} /> : null}{item.mediaUri && !item.mediaMime?.startsWith("image/") ? <Pressable onPress={() => downloadMedia(item)} style={({ pressed }) => [mediaDownloadStyles.button, pressed && mediaDownloadStyles.pressed]} accessibilityLabel="Скачать файл"><Text style={mediaDownloadStyles.arrow}>↓</Text><View><Text style={mediaDownloadStyles.title}>Скачать файл</Text><Text style={mediaDownloadStyles.name}>{item.mediaFilename || item.mediaMime || "Медиафайл"}</Text></View></Pressable> : null}{item.audioUri ? <Pressable onPress={() => downloadMedia(item, "audio")} style={({ pressed }) => [mediaDownloadStyles.button, pressed && mediaDownloadStyles.pressed]} accessibilityLabel="Скачать аудио"><Text style={mediaDownloadStyles.arrow}>↓</Text><View><Text style={mediaDownloadStyles.title}>Скачать аудио</Text><Text style={mediaDownloadStyles.name}>{item.audioFilename || item.audioMime || "Аудиофайл"}</Text></View></Pressable> : null}</View>} />
    {memoryNotice ? <Pressable style={styles.memoryNotice} onPress={openMemory}><Text style={styles.memoryNoticeText}>✓ Запомнил важное. Управлять памятью →</Text></Pressable> : null}
    {workflowData?.status === "active" || workflowData?.status === "ready_for_review" ? <View style={styles.workflowCard}><Text style={styles.workflowKicker}>АКТИВНАЯ ЗАДАЧА · {workflowProgress}</Text><Text style={styles.workflowGoal}>{workflowGoal}</Text><Text style={styles.workflowStep}>Сейчас: {workflowStep}</Text><View style={styles.workflowActions}><Pressable onPress={() => send(`Помоги мне выполнить текущий шаг: ${workflowStep}`)}><Text style={styles.workflowAction}>Обсудить шаг</Text></Pressable><Pressable onPress={async () => { const result = await api.nextWorkflowStep(token); setWorkflowData(result.workflow); }}><Text style={styles.workflowAction}>Следующий шаг</Text></Pressable><Pressable onPress={async () => { const result = await api.nextWorkflowStep(token, true); setWorkflowData(result.workflow); }}><Text style={styles.workflowAction}>Готово</Text></Pressable></View></View> : null}
    {items.length > 0 && !message && !busy ? <View style={styles.quickActionRow}><Pressable onPress={() => send("Сделай последний ответ короче и конкретнее.")} style={styles.quickAction}><Text style={styles.quickActionText}>Короче</Text></Pressable><Pressable onPress={() => send("Какой следующий практический шаг?")} style={styles.quickAction}><Text style={styles.quickActionText}>Следующий шаг</Text></Pressable><Pressable onPress={() => send("Составь из этого короткий план действий.")} style={styles.quickAction}><Text style={styles.quickActionText}>План</Text></Pressable><Pressable onPress={openMemory} style={styles.quickAction}><Text style={styles.quickActionText}>Память</Text></Pressable></View> : null}
    {activity ? <View style={activityStyles.activityPill}><ActivityPulse /><Text style={activityStyles.activityText}>{activity === "recording" ? "Записываю голосовое…" : activity === "searching" ? "Ищу актуальные данные…" : activity === "planning" ? "Планирую шаги…" : activity === "analyzing" ? "Анализирую…" : "Генерирую ответ…"}</Text></View> : null}
    {!attachment ? (() => { const latestImage = [...items].reverse().find((item) => item.mediaUri && item.mediaMime?.startsWith("image/")); return latestImage ? <Pressable onPress={() => editMediaNow(latestImage)} disabled={busy} accessibilityLabel="Редактировать последнее изображение"><Text style={mediaStyles.generateAction}>✏️ Редактировать последнее изображение</Text></Pressable> : null; })() : null}
    {playingVoiceId ? <Pressable onPress={stopVoicePlayback} style={({ pressed }) => [mediaStyles.stopAudioButton, pressed && mediaDownloadStyles.pressed]} accessibilityLabel="Остановить озвучку"><Text style={mediaStyles.generateAction}>■ Остановить озвучку</Text></Pressable> : null}
    {attachment ? <View style={mediaStyles.attachmentChip}><Text style={mediaStyles.attachmentText}>{attachment.type === "audio" ? "Голосовое сообщение" : attachment.type === "video" ? "Видео прикреплено" : "Фото прикреплено"}</Text>{attachment.type !== "audio" ? <Pressable onPress={generateAttachment} disabled={busy} accessibilityLabel="Изменить вложение"><Text style={mediaStyles.generateAction}>✦ Изменить</Text></Pressable> : null}<Pressable onPress={() => setAttachment(null)} accessibilityLabel="Удалить вложение"><Text style={mediaStyles.removeAttachment}>×</Text></Pressable></View> : null}
    <View style={styles.composer}><Pressable style={mediaStyles.attachButton} onPress={() => { resetIdle(); pickMedia(); }} accessibilityLabel="Прикрепить фото или видео"><Text style={mediaStyles.attachIcon}>＋</Text></Pressable><TextInput style={[styles.input, styles.composerInput]} placeholder="Напиши ALTER..." placeholderTextColor="#78809a" value={message} onChangeText={(value) => { resetIdle(); setMessage(value); }} onSubmitEditing={() => send()} /><VoiceButton onRecorded={keepVoice} onRecordingChange={(active) => { resetIdle(); setActivity(active ? "recording" : ""); }} /><Pressable style={mediaStyles.sendButton} onPress={() => send()} disabled={busy} accessibilityLabel="Отправить сообщение"><Text style={mediaStyles.sendIcon}>{busy ? "…" : "↑"}</Text></Pressable></View>
    {busy && !attachment ? <Pressable style={styles.stopResponseButton} onPress={stopRequest} accessibilityLabel="Остановить ответ"><Text style={styles.stopResponseText}>■ Остановить ответ</Text></Pressable> : null}
    {!busy && items.some((item) => item.role === "user") ? <Pressable style={styles.editLastButton} onPress={() => { const last = [...items].reverse().find((item) => item.role === "user"); if (last) { setMessage(last.text); resetIdle(); } }} accessibilityLabel="Редактировать последнее сообщение"><Text style={styles.editLastText}>Изменить последнее сообщение</Text></Pressable> : null}
    {!message ? <View pointerEvents="none" style={mediaStyles.inputMask}><View style={mediaStyles.inputGlow} /></View> : null}
  </KeyboardAvoidingView>
  <Modal visible={historyVisible} transparent animationType="fade" onRequestClose={() => setHistoryVisible(false)}><Pressable style={historyStyles.backdrop} onPress={() => setHistoryVisible(false)}><Pressable style={historyStyles.panel} onPress={(event) => event.stopPropagation()}><Pressable onPress={() => setHistoryVisible(false)} accessibilityLabel="Закрыть историю"><Text style={historyStyles.panelClose}>‹</Text></Pressable><Text style={historyStyles.title}>История</Text><FlatList data={archivedItems} keyExtractor={(item) => item.id} renderItem={({ item }) => <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.aiBubble]}><Text style={styles.message}>{item.text}</Text></View>} ListEmptyComponent={<Text style={historyStyles.empty}>Здесь появятся старые сообщения</Text>} /></Pressable></Pressable></Modal>
  <Modal visible={legalVisible} transparent animationType="fade" onRequestClose={() => undefined}>
    <View style={permissionStyles.backdrop}><View style={permissionStyles.card}><Text style={permissionStyles.kicker}>ALTER · ДО НАЧАЛА РАБОТЫ</Text><Text style={permissionStyles.title}>Документы и согласие</Text><Text style={permissionStyles.body}>Перед началом работы ознакомься с политикой конфиденциальности, публичной офертой и согласием на обработку данных. Без подтверждения ALTER не запрашивает push и геолокацию и не запускает рабочий чат.</Text><View style={{ gap: 8, marginBottom: 18 }}><Pressable onPress={() => Linking.openURL("https://alterai.ru/legal/privacy.html")}><Text style={linkStyles.link}>Политика конфиденциальности →</Text></Pressable><Pressable onPress={() => Linking.openURL("https://alterai.ru/legal/consent.html")}><Text style={linkStyles.link}>Согласие на обработку данных →</Text></Pressable><Pressable onPress={() => Linking.openURL("https://alterai.ru/legal/offer.html")}><Text style={linkStyles.link}>Публичная оферта →</Text></Pressable><Pressable onPress={() => Linking.openURL("https://alterai.ru/legal/refund.html")}><Text style={linkStyles.link}>Оплата и возврат →</Text></Pressable></View><Pressable style={authStyles.legalRow} onPress={() => setLegalChecked((value) => !value)}><Text style={authStyles.check}>{legalChecked ? "✓" : "○"}</Text><Text style={authStyles.legalText}>Я ознакомился с документами и согласен на обработку данных</Text></Pressable><Pressable style={[permissionStyles.primary, { opacity: legalChecked && !legalBusy ? 1 : 0.45, marginTop: 18 }]} onPress={acceptLegal} disabled={!legalChecked || legalBusy}><Text style={permissionStyles.primaryText}>{legalBusy ? "Сохраняем…" : "Принять и продолжить"}</Text></Pressable></View></View>
  </Modal>
  <Modal visible={permissionOfferVisible && !legalVisible} transparent animationType="fade" onRequestClose={() => setPermissionOfferVisible(false)}>
    <View style={permissionStyles.backdrop}><View style={permissionStyles.card}><Text style={permissionStyles.kicker}>ЛИЧНЫЙ РЕЖИМ</Text><Text style={permissionStyles.title}>Понимать тебя точнее</Text><Text style={permissionStyles.body}>Разреши уведомления и примерную геолокацию — тогда ALTER сможет мягко напоминать о важном, ориентировать по погоде и лучше чувствовать контекст твоего дня.</Text><Pressable style={permissionStyles.primary} onPress={acceptPermissionOffer} disabled={permissionBusy}><Text style={permissionStyles.primaryText}>{permissionBusy ? "Настраиваем…" : "Разрешить для лучшего опыта"}</Text></Pressable><Pressable onPress={() => setPermissionOfferVisible(false)}><Text style={permissionStyles.later}>Позже</Text></Pressable></View></View>
  </Modal>
  <Modal visible={menuVisible && !memoryVisible && !remindersVisible && !faqVisible && !plansVisible} transparent animationType="none" onRequestClose={() => setMenuVisible(false)}>
    <Pressable style={premiumStyles.drawerBackdrop} onPress={() => setMenuVisible(false)}>
      <Animated.View testID="drawer-card" style={[premiumStyles.menuCard, { transform: [{ translateX: drawerX }] }]}>{/* drawer */}
      <Pressable style={premiumStyles.drawerContent} onPress={(event) => event.stopPropagation()}>
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={premiumStyles.drawerScroll}>
        <Animated.Text style={[premiumStyles.drawerLogo, { opacity: logoPulse }]}>ALTER</Animated.Text>
        <Pressable style={premiumStyles.sectionHeader} onPress={() => setOpenSection((value) => value === "profile" ? null : "profile")}><Text style={premiumStyles.sectionLabel}>ПРОФИЛЬ</Text><Text style={premiumStyles.sectionChevron}>{openSection === "profile" ? "⌃" : "⌄"}</Text></Pressable>
        {openSection === "profile" ? <View style={premiumStyles.sectionBody}>
        <Pressable style={premiumStyles.accountRow} onPress={() => setEmailVisible((value) => !value)}><Text style={premiumStyles.menuEmail}>{emailVisible ? (account?.email || "Почта не указана") : maskedEmail}</Text><Text style={premiumStyles.menuActionArrow}>{emailVisible ? "⌃" : "⌄"}</Text></Pressable>
        {account?.owner ? <Text style={premiumStyles.ownerBadge}>ПОЛНЫЙ ДОСТУП</Text> : <Text style={premiumStyles.menuStatus}>ТАРИФ · {account?.subscription_plan === "ego" ? "ALTER EGO" : "ALTER PERSONAL"}</Text>}
        <View style={premiumStyles.usageRow}><Text style={premiumStyles.menuActionText}>Лимиты</Text><Text style={premiumStyles.usageText}>{usage ? `${usage.remaining} из ${usage.limit}` : "…"}</Text></View>
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
        {!account?.telegram_linked ? <Pressable style={premiumStyles.menuAction} onPress={openTelegramLink}><Text style={premiumStyles.menuActionText}>Подключить Telegram</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable> : null}
        <Pressable style={premiumStyles.menuAction} onPress={openCalendarConnect}><Text style={premiumStyles.menuActionText}>Подключить Google Calendar</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        {menuError ? <Text style={styles.error}>{menuError}</Text> : null}
        </View> : null}
        <Pressable style={premiumStyles.sectionHeader} onPress={() => setOpenSection((value) => value === "tools" ? null : "tools")}><Text style={premiumStyles.sectionLabel}>ИНСТРУМЕНТЫ</Text><Text style={premiumStyles.sectionChevron}>{openSection === "tools" ? "⌃" : "⌄"}</Text></Pressable>
        {openSection === "tools" ? <View style={premiumStyles.sectionBody}>
        <Pressable style={premiumStyles.menuAction} onPress={openMyDay}><Text style={premiumStyles.menuActionText}>Мой день</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={openScenarios}><Text style={premiumStyles.menuActionText}>Фирменные сценарии</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={openMemory}><Text style={premiumStyles.menuActionText}>Память</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={openActionLog}><Text style={premiumStyles.menuActionText}>Журнал действий</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={() => { setMenuVisible(false); setHistoryVisible(true); }}><Text style={premiumStyles.menuActionText}>История чата</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={openFaq}><Text style={premiumStyles.menuActionText}>FAQ · как пользоваться</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={openReminders}><Text style={premiumStyles.menuActionText}>Напоминания</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        </View> : null}
        <Pressable style={premiumStyles.sectionHeader} onPress={() => setOpenSection((value) => value === "settings" ? null : "settings")}><Text style={premiumStyles.sectionLabel}>НАСТРОЙКИ</Text><Text style={premiumStyles.sectionChevron}>{openSection === "settings" ? "⌃" : "⌄"}</Text></Pressable>
        {openSection === "settings" ? <View style={premiumStyles.sectionBody}>
        <Pressable style={premiumStyles.menuAction} onPress={toggleCheckins}><View style={{ flex: 1 }}><Text style={premiumStyles.menuActionText}>Забота · {checkinsEnabled ? "включена" : "выключена"}</Text><Text style={{ color: "#777", fontSize: 12, marginTop: 3 }}>ALTER возвращается к важным темам и задаёт контекстный вопрос</Text></View><Text style={premiumStyles.menuActionArrow}>{checkinsEnabled ? "✓" : "○"}</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={chooseLocationMode}><Text style={premiumStyles.menuActionText}>{location?.city ? `Геолокация · ${location.city}` : "Разрешить геолокацию"}</Text><Text style={premiumStyles.menuActionArrow}>⌖</Text></Pressable>
        <View style={premiumStyles.menuAction}><Pressable style={{ flex: 1 }} onPress={async () => { const next = !voiceReplies; setVoiceReplies(next); try { await api.updateSettings(token, { voice_replies: next }); } catch (err) { setVoiceReplies(!next); setMenuError(err instanceof Error ? err.message : "Не удалось сохранить настройку"); } }}><Text style={premiumStyles.menuActionText}>Голосовые ответы · {voiceReplies ? "включены" : "выключены"}</Text></Pressable><Pressable onPress={() => voiceReplies && setVoiceMenuOpen((value) => !value)} accessibilityLabel="Настроить голосовые ответы"><Text style={premiumStyles.menuActionArrow}>{voiceReplies ? (voiceMenuOpen ? "⌃" : "⌄") : "○"}</Text></Pressable></View>
        {voiceReplies && voiceMenuOpen ? <View style={premiumStyles.submenu}><Pressable style={premiumStyles.submenuAction} onPress={async () => { const next = !autoVoiceReplies; setAutoVoiceReplies(next); try { await api.updateSettings(token, { voice_auto_replies: next }); } catch (err) { setAutoVoiceReplies(!next); setMenuError(err instanceof Error ? err.message : "Не удалось сохранить настройку"); } }}><Text style={premiumStyles.menuActionText}>Озвучивать автоматически</Text><Text style={premiumStyles.menuActionArrow}>{autoVoiceReplies ? "✓" : "○"}</Text></Pressable><Pressable style={premiumStyles.submenuAction} onPress={async () => { const voices = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse", "elevenlabs"]; const next = voices[(voices.indexOf(ttsVoice) + 1) % voices.length]; const preview = "Привет, я ALTER, твой персональный ассистент."; setTtsVoice(next); try { await api.updateSettings(token, { tts_voice: next }); await playVoiceReply(preview, "voice-preview"); } catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось выбрать голос"); } }}><Text style={premiumStyles.menuActionText}>Голос · {ttsVoice === "elevenlabs" ? "ElevenLabs Premium" : ttsVoice}</Text><Text style={premiumStyles.menuActionArrow}>›</Text></Pressable></View> : null}
        <Pressable style={premiumStyles.menuAction} onPress={() => setVoiceCreatorVisible(true)}><Text style={premiumStyles.menuActionText}>Создать голос</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={premiumStyles.menuAction} onPress={async () => { const next = !privateMode; setPrivateMode(next); try { await api.updateSettings(token, { private_mode: next }); } catch (err) { setPrivateMode(!next); setMenuError(err instanceof Error ? err.message : "Не удалось сохранить приватный режим"); } }}><View style={{ flex: 1 }}><Text style={premiumStyles.menuActionText}>Приватный режим · {privateMode ? "включён" : "выключен"}</Text><Text style={{ color: "#777", fontSize: 12, marginTop: 3 }}>Не сохранять сообщения, память и действия</Text></View><Text style={premiumStyles.menuActionArrow}>{privateMode ? "✓" : "○"}</Text></Pressable>
        </View> : null}
        <Pressable style={[premiumStyles.menuAction, premiumStyles.menuLogout]} onPress={() => { setMenuVisible(false); onLogout(); }}><Text style={premiumStyles.menuActionText}>Выйти</Text><Text style={premiumStyles.menuActionArrow}>↗</Text></Pressable>
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
  <Modal visible={voiceCreatorVisible} transparent animationType="fade" onRequestClose={() => setVoiceCreatorVisible(false)}>
    <View style={permissionStyles.backdrop}><View style={permissionStyles.card}><Text style={permissionStyles.kicker}>ELEVENLABS</Text><Text style={permissionStyles.title}>Создать голос</Text><Text style={permissionStyles.body}>Опиши голос обычными словами. Например: спокойный низкий голос для подкаста.</Text><TextInput value={voiceDescription} onChangeText={setVoiceDescription} placeholder="Описание голоса" placeholderTextColor="#777" multiline style={styles.voiceDescriptionInput} /><Pressable style={[permissionStyles.primary, { opacity: voiceDescription.trim() && !busy ? 1 : 0.45 }]} onPress={createVoice} disabled={!voiceDescription.trim() || busy}><Text style={permissionStyles.primaryText}>{busy ? "Создаём…" : "Создать голос"}</Text></Pressable><Pressable onPress={() => setVoiceCreatorVisible(false)}><Text style={permissionStyles.later}>Отмена</Text></Pressable></View></View>
  </Modal>
  <Modal visible={remindersVisible} animationType="slide" onRequestClose={() => { setRemindersVisible(false); setMenuVisible(true); }}>
    <SafeAreaView style={styles.memoryScreen}><View style={styles.memoryHeader}><Text style={styles.memoryTitle}>Напоминания</Text><Pressable style={premiumStyles.menuAction} onPress={() => { setRemindersVisible(false); setMenuVisible(true); }}><Text style={premiumStyles.menuActionText}>Назад</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable></View>
      <Text style={{ color: "#999", paddingHorizontal: 20, paddingBottom: 8, lineHeight: 21 }}>Скажи ALTER в основном чате, о чём и к какому времени напомнить. Можно голосом.</Text>
      {reminders.length === 0 ? <Text style={styles.emptyMemory}>Активных напоминаний пока нет.</Text> : <FlatList data={reminders} keyExtractor={(item) => String(item.id)} contentContainerStyle={styles.memoryList} renderItem={({ item }) => <View style={styles.memoryRow}><Text style={styles.memoryValue}>{item.text}</Text><Text style={styles.memoryKey}>{new Date(item.remind_at).toLocaleString()}</Text><Pressable style={premiumStyles.menuAction} onPress={async () => { await api.deleteReminder(token, item.id); setReminders((old) => old.filter((entry) => entry.id !== item.id)); }}><Text style={premiumStyles.menuActionText}>Удалить</Text><Text style={premiumStyles.menuActionArrow}>×</Text></Pressable></View>} />}
    </SafeAreaView>
  </Modal>
  <Modal visible={myDayVisible} animationType="slide" onRequestClose={() => setMyDayVisible(false)}>
    <SafeAreaView style={styles.memoryScreen}>
      <View style={styles.memoryHeader}><Text style={styles.memoryTitle}>Мой день</Text><Pressable style={premiumStyles.menuAction} onPress={() => setMyDayVisible(false)}><Text style={premiumStyles.menuActionText}>Назад</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable></View>
      <Text style={styles.myDayIntro}>ALTER собрал важное из памяти, целей и напоминаний. Не всё сразу — только то, к чему стоит вернуться.</Text>
      {myDayLoading ? <ActivityIndicator color="#fff" /> : <ScrollView contentContainerStyle={styles.memoryList}>
        <Pressable style={styles.nextStepCard} onPress={() => { setMyDayVisible(false); send(myDayData?.next_step.prompt || "Помоги мне выбрать одно главное дело на сегодня"); }}><Text style={styles.nextStepKicker}>ЛУЧШИЙ СЛЕДУЮЩИЙ ШАГ</Text><Text style={styles.nextStepTitle}>{myDayData?.next_step.title || "Выбрать главное на сегодня"}</Text><Text style={styles.nextStepAction}>Открыть в чате →</Text></Pressable>
        {myDayData?.focus.length ? myDayData.focus.map((item, index) => <View key={`${item.kind}-${item.title}-${index}`} style={styles.dayItem}><View style={styles.dayItemDot} /><View style={{ flex: 1 }}><Text style={styles.memoryValue}>{item.title}</Text><Text style={styles.memoryKey}>{item.detail}{item.at ? ` · ${new Date(item.at).toLocaleString()}` : ""}</Text>{item.kind === "open_loop" && item.loop_index !== undefined ? <Pressable onPress={async () => { await api.updateLoop(token, item.loop_index!, "done"); setMyDayData(await api.myDay(token)); }}><Text style={styles.loopDone}>✓ Закрыть тему</Text></Pressable> : null}</View></View>) : <Text style={styles.emptyMemory}>Пока ничего не нужно удерживать в фокусе. Напиши ALTER, что для тебя важно.</Text>}
      </ScrollView>}
    </SafeAreaView>
  </Modal>
  <Modal visible={scenariosVisible} animationType="slide" onRequestClose={() => setScenariosVisible(false)}>
    <SafeAreaView style={styles.memoryScreen}><View style={styles.memoryHeader}><Text style={styles.memoryTitle}>Сценарии ALTER</Text><Pressable style={premiumStyles.menuAction} onPress={() => setScenariosVisible(false)}><Text style={premiumStyles.menuActionText}>Назад</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable></View><Text style={styles.myDayIntro}>Готовые способы начать с результата, а не с пустого чата.</Text><ScrollView contentContainerStyle={styles.memoryList}>{scenarios.map((item) => <Pressable key={item.id} style={styles.nextStepCard} onPress={async () => { setScenariosVisible(false); try { const result = await api.startWorkflow(token, item.id, item.title); setWorkflowData(result.workflow); } catch { /* Private mode and network errors still allow a normal chat. */ } send(item.prompt); }}><Text style={styles.nextStepKicker}>{item.mode.toUpperCase()}</Text><Text style={styles.nextStepTitle}>{item.title}</Text><Text style={styles.nextStepAction}>Запустить →</Text></Pressable>)}</ScrollView></SafeAreaView>
  </Modal>
  <Modal visible={actionLogVisible} animationType="slide" onRequestClose={() => setActionLogVisible(false)}>
    <SafeAreaView style={styles.memoryScreen}><View style={styles.memoryHeader}><Text style={styles.memoryTitle}>История действий</Text><Pressable style={premiumStyles.menuAction} onPress={() => setActionLogVisible(false)}><Text style={premiumStyles.menuActionText}>Назад</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable></View><Text style={styles.myDayIntro}>Здесь видно, что ALTER сделала по твоим запросам.</Text>{privateMode ? <Text style={styles.emptyMemory}>Приватный режим включён — действия не сохраняются.</Text> : actionLog.length === 0 ? <Text style={styles.emptyMemory}>Пока действий нет.</Text> : <FlatList data={actionLog} keyExtractor={(item, index) => `${item.at}-${index}`} contentContainerStyle={styles.memoryList} renderItem={({ item }) => <View style={styles.memoryRow}><Text style={styles.memoryValue}>{actionLabel(item)} · {actionStatusLabel(item.status)}</Text><Text style={styles.memoryKey}>{new Date(item.at).toLocaleString()}</Text></View>} />}</SafeAreaView>
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
      <View style={styles.permanentMemoryCard}><Text style={styles.permanentMemoryTitle}>Память ALTER · бессрочно</Text><Text style={styles.permanentMemoryText}>{memoryData?.description || "ALTER хранит важные факты, цели и стиль общения, пока ты сам не попросишь их удалить."}</Text></View>
      {memoryData?.audit?.some((item) => !item.confirmed) ? <View style={styles.memoryAuditCard}><Text style={styles.memoryAuditTitle}>Проверь, что это всё ещё верно</Text>{memoryData.audit.filter((item) => !item.confirmed).slice(0, 5).map((item) => <Pressable key={item.category + item.key} onPress={() => confirmMemoryFact(item.category, item.key)}><Text style={styles.memoryAuditItem}>{memoryAuditLabel(item.category)} · Подтвердить ✓</Text></Pressable>)}</View> : null}
      <Text style={{ color: "#888", paddingHorizontal: 20, paddingBottom: 8, lineHeight: 20 }}>ALTER сама запоминает важные факты. Скажи в чате «запомни…», если хочешь сохранить что-то точно.</Text>
       {memoryLoading ? <ActivityIndicator color="#fff" /> : memoryError ? <Text style={styles.error}>{memoryError}</Text> : memorySections.length === 0 ? <Text style={styles.emptyMemory}>Пока здесь пусто. ALTER заполнит память по мере ваших разговоров.</Text> : <><FlatList data={memorySections} keyExtractor={(item) => item.category} contentContainerStyle={styles.memoryList} renderItem={({ item }) => <View style={styles.memoryRow}><View style={styles.memorySectionHeader}><Text style={styles.memoryKey}>{item.title}</Text><Pressable onPress={() => forgetMemoryCategory(item.category, item.title)} accessibilityLabel={`Забыть категорию ${item.title}`}><Text style={styles.memoryForget}>Забыть</Text></Pressable></View>{item.items.map((fact, index) => <Text key={item.title + index} style={styles.memoryValue}>{fact.label ? fact.label + ": " + fact.value : fact.value}</Text>)}</View>} /><Pressable style={styles.clearMemoryButton} onPress={clearContext} accessibilityLabel="Очистить контекст прошлых разговоров"><Text style={styles.clearMemoryText}>Очистить контекст</Text></Pressable><Pressable style={styles.clearMemoryButton} onPress={clearMemory} accessibilityLabel="Очистить всю память"><Text style={styles.clearMemoryText}>Очистить всю память</Text></Pressable><Pressable style={[styles.clearMemoryButton, styles.dangerButton]} onPress={() => Alert.alert("Удалить все данные?", "Удалятся память, история, workflow, напоминания и журнал действий. Аккаунт и подписка останутся.", [{ text: "Отмена", style: "cancel" }, { text: "Удалить", style: "destructive", onPress: async () => { try { await api.clearAllPersonalData(token); setItems([]); setArchivedItems([]); setMemoryData(null); setWorkflowData(null); } catch (err) { setMemoryError(err instanceof Error ? err.message : "Не удалось удалить данные"); } } }])} accessibilityLabel="Удалить все персональные данные"><Text style={styles.clearMemoryText}>Удалить все данные ALTER</Text></Pressable></>}
    </SafeAreaView>
  </Modal>
  <Modal visible={faqVisible} animationType="slide" onRequestClose={() => setFaqVisible(false)}>
    <SafeAreaView style={styles.faqScreen}><View style={styles.memoryHeader}><Text style={styles.memoryTitle}>FAQ</Text><Pressable style={premiumStyles.menuAction} onPress={() => setFaqVisible(false)}><Text style={premiumStyles.menuActionText}>Назад</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable></View><ScrollView contentContainerStyle={styles.faqContent}><Text style={styles.faqText}>{FAQ_TEXT}</Text></ScrollView></SafeAreaView>
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

const styles: any = StyleSheet.create({
  intro: { flex: 1, backgroundColor: "#050505", alignItems: "center", justifyContent: "center" }, introLogo: { color: "#fff", fontSize: 54, fontWeight: "800", letterSpacing: 8, textAlign: "center" }, introCaption: { color: "#666", fontSize: 9, letterSpacing: 3, textAlign: "center", marginTop: 12 }, introLine: { height: 1, backgroundColor: "#fff", opacity: 0.8, marginTop: 38 }, container: { flex: 1, backgroundColor: "#050505", justifyContent: "center" }, card: { margin: 24, gap: 14 }, title: { color: "#fff", fontSize: 42, fontWeight: "800", textAlign: "center", letterSpacing: 2 }, subtitle: { color: "#999", textAlign: "center", marginBottom: 18 }, input: { backgroundColor: "#151515", color: "#fff", borderRadius: 12, padding: 14, fontSize: 16, borderWidth: 1, borderColor: "#292929" }, error: { color: "#ff9d9d" }, chat: { flex: 1 }, header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 16 }, headerTitle: { color: "#fff", fontSize: 24, fontWeight: "800", letterSpacing: 2 }, menuButton: { padding: 8 }, menuIcon: { color: "#fff", fontSize: 20, letterSpacing: 3 }, modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.72)", alignItems: "flex-end", paddingTop: 56, paddingRight: 12 }, menuCard: { width: 290, backgroundColor: "#111", borderRadius: 18, padding: 20, gap: 12, borderWidth: 1, borderColor: "#2b2b2b" }, menuTitle: { color: "#fff", fontSize: 22, fontWeight: "700" }, menuEmail: { color: "#999" }, menuStatus: { color: "#ddd", fontSize: 14 }, menuDivider: { height: 1, backgroundColor: "#292929" }, messages: { padding: 16, gap: 10 }, bubble: { maxWidth: "86%", padding: 12, borderRadius: 16 }, userBubble: { alignSelf: "flex-end", backgroundColor: "#fff" }, userMessage: { color: "#050505" }, aiBubble: { alignSelf: "flex-start", backgroundColor: "#151515", borderWidth: 1, borderColor: "#292929" }, message: { color: "#fff", fontSize: 16, lineHeight: 23 }, cursor: { color: "#fff" }, composer: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12 }, composerInput: { flex: 1 }, memoryScreen: { flex: 1, backgroundColor: "#050505" }, memoryHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 20 }, memoryTitle: { color: "#fff", fontSize: 30, fontWeight: "700" }, memoryList: { padding: 20, gap: 14 }, memoryRow: { borderBottomWidth: 1, borderBottomColor: "#292929", paddingBottom: 14, gap: 6 }, memoryKey: { color: "#888", fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }, memoryValue: { color: "#eee", fontSize: 16, lineHeight: 23 }, emptyMemory: { color: "#999", padding: 24, fontSize: 16, lineHeight: 24 }, faqScreen: { flex: 1, backgroundColor: "#050505" }, faqContent: { padding: 20, paddingBottom: 60 }, faqText: { color: "#f4f4f4", fontSize: 13, lineHeight: 20, letterSpacing: 0.2 },
});

// Keep the composer surface pure black while retaining the native field size.
(styles as Record<string, unknown>).input = { ...StyleSheet.flatten(styles.input), backgroundColor: "#000000", borderColor: "#ffffff", borderWidth: StyleSheet.hairlineWidth };
(styles as Record<string, unknown>).aiBubble = { ...StyleSheet.flatten(styles.aiBubble), backgroundColor: "#000000", borderWidth: 0, borderColor: "transparent" };
(styles as Record<string, unknown>).messages = { ...StyleSheet.flatten(styles.messages), padding: 10, gap: 3 };
(styles as Record<string, unknown>).bubble = { ...StyleSheet.flatten(styles.bubble), padding: 8, maxWidth: "92%" };
(styles as Record<string, unknown>).intro = { ...StyleSheet.flatten(styles.intro), backgroundColor: "#050505" };
(styles as Record<string, unknown>).memorySectionHeader = { flexDirection: "row", alignItems: "center", justifyContent: "space-between" };
(styles as Record<string, unknown>).memoryForget = { color: "#aaa", fontSize: 12 };
(styles as Record<string, unknown>).clearMemoryButton = { marginHorizontal: 20, marginBottom: 30, borderWidth: 1, borderColor: "#5b3042", borderRadius: 12, paddingVertical: 13, alignItems: "center" };
(styles as Record<string, unknown>).clearMemoryText = { color: "#ffb4c8", fontWeight: "700" };
(styles as Record<string, unknown>).voiceDescriptionInput = { minHeight: 90, maxHeight: 150, backgroundColor: "#181818", borderRadius: 12, color: "#fff", padding: 14, textAlignVertical: "top", marginBottom: 14 };
(styles as Record<string, unknown>).thinkingDots = { color: "#ffffff", fontSize: 22, letterSpacing: 4, minWidth: 52 };
(styles as Record<string, unknown>).emptyChat = { alignItems: "center", justifyContent: "center", paddingHorizontal: 24, paddingVertical: 18, gap: 10 };
(styles as Record<string, unknown>).emptyLogo = { color: "#ffffff", fontSize: 38, fontWeight: "900", letterSpacing: 7, marginBottom: 4 };
(styles as Record<string, unknown>).emptyTitle = { color: "#ffffff", fontSize: 22, fontWeight: "800", textAlign: "center" };
(styles as Record<string, unknown>).emptySubtitle = { color: "#999999", fontSize: 14, lineHeight: 21, textAlign: "center", maxWidth: 360 };
(styles as Record<string, unknown>).quickPromptGrid = { width: "100%", flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 };
(styles as Record<string, unknown>).quickPrompt = { width: "48%", minHeight: 74, padding: 12, borderRadius: 14, backgroundColor: "#111111", borderWidth: 1, borderColor: "#333333" };
(styles as Record<string, unknown>).quickPromptPressed = { backgroundColor: "#242424", borderColor: "#ffffff", transform: [{ scale: 0.98 }] };
(styles as Record<string, unknown>).quickPromptTitle = { color: "#ffffff", fontSize: 13, fontWeight: "800", marginBottom: 5 };
(styles as Record<string, unknown>).quickPromptText = { color: "#999999", fontSize: 11, lineHeight: 15 };
(styles as Record<string, unknown>).emptyHint = { color: "#666666", fontSize: 11, letterSpacing: 0.6, textAlign: "center", marginTop: 4 };
(styles as Record<string, unknown>).memoryNotice = { marginHorizontal: 12, marginBottom: 3, paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10, backgroundColor: "#151515", borderWidth: 1, borderColor: "#4a4a4a" };
(styles as Record<string, unknown>).memoryNoticeText = { color: "#ffffff", fontSize: 12, textAlign: "center" };
(styles as Record<string, unknown>).workflowCard = { marginHorizontal: 12, marginBottom: 6, padding: 12, borderRadius: 12, backgroundColor: "#15131e", borderWidth: 1, borderColor: "#514575" };
(styles as Record<string, unknown>).workflowKicker = { color: "#b8a6ff", fontSize: 10, letterSpacing: 1, fontWeight: "700" };
(styles as Record<string, unknown>).workflowGoal = { color: "#fff", fontSize: 15, fontWeight: "700", marginTop: 4 };
(styles as Record<string, unknown>).workflowStep = { color: "#bbb", fontSize: 13, marginTop: 5 };
(styles as Record<string, unknown>).workflowActions = { flexDirection: "row", justifyContent: "space-between", marginTop: 10 };
(styles as Record<string, unknown>).workflowAction = { color: "#d4c9ff", fontSize: 12, fontWeight: "700" };
(styles as Record<string, unknown>).alterLoopCard = { marginHorizontal: 16, marginBottom: 14, padding: 16, borderRadius: 16, backgroundColor: "#171717", borderWidth: 1, borderColor: "#555" };
(styles as Record<string, unknown>).alterLoopKicker = { color: "#9f9f9f", fontSize: 10, letterSpacing: 2, marginBottom: 8 };
(styles as Record<string, unknown>).alterLoopTitle = { color: "#fff", fontSize: 17, fontWeight: "700", marginBottom: 6 };
(styles as Record<string, unknown>).alterLoopText = { color: "#bdbdbd", fontSize: 13, lineHeight: 19 };
(styles as Record<string, unknown>).stopResponseButton = { alignSelf: "center", marginBottom: 4, paddingHorizontal: 14, paddingVertical: 7, borderRadius: 14, backgroundColor: "#242424", borderWidth: 1, borderColor: "#555" };
(styles as Record<string, unknown>).stopResponseText = { color: "#fff", fontSize: 12 };
(styles as Record<string, unknown>).editLastButton = { alignSelf: "flex-end", marginRight: 16, marginBottom: 4, paddingHorizontal: 10, paddingVertical: 4 };
(styles as Record<string, unknown>).editLastText = { color: "#888", fontSize: 11 };
(styles as Record<string, unknown>).permanentMemoryCard = { marginHorizontal: 20, marginBottom: 4, padding: 14, borderRadius: 14, backgroundColor: "#171717", borderWidth: 1, borderColor: "#4a4a4a" };
(styles as Record<string, unknown>).permanentMemoryTitle = { color: "#fff", fontSize: 13, fontWeight: "700", marginBottom: 5 };
(styles as Record<string, unknown>).permanentMemoryText = { color: "#aaa", fontSize: 12, lineHeight: 18 };
(styles as Record<string, unknown>).memoryAuditCard = { marginHorizontal: 20, marginTop: 8, marginBottom: 4, padding: 12, borderRadius: 12, backgroundColor: "#211f18", borderWidth: 1, borderColor: "#695d35" };
(styles as Record<string, unknown>).memoryAuditTitle = { color: "#f0df9a", fontSize: 12, fontWeight: "700", marginBottom: 6 };
(styles as Record<string, unknown>).memoryAuditItem = { color: "#d8cfaa", fontSize: 12, paddingVertical: 6 };
(styles as Record<string, unknown>).myDayIntro = { color: "#aaa", paddingHorizontal: 20, paddingBottom: 8, fontSize: 14, lineHeight: 21 };
(styles as Record<string, unknown>).nextStepCard = { marginHorizontal: 20, marginBottom: 8, padding: 16, borderRadius: 16, backgroundColor: "#f4f4f4" };
(styles as Record<string, unknown>).nextStepKicker = { color: "#777", fontSize: 10, letterSpacing: 1.5, marginBottom: 8 };
(styles as Record<string, unknown>).nextStepTitle = { color: "#080808", fontSize: 18, fontWeight: "700", lineHeight: 23 };
(styles as Record<string, unknown>).nextStepAction = { color: "#555", marginTop: 12, fontSize: 12, fontWeight: "700" };
(styles as Record<string, unknown>).dayItem = { flexDirection: "row", gap: 10, paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: "#292929" };
(styles as Record<string, unknown>).dayItemDot = { width: 7, height: 7, borderRadius: 4, backgroundColor: "#fff", marginTop: 7 };
(styles as Record<string, unknown>).loopDone = { color: "#aaa", fontSize: 11, marginTop: 7 };
(styles as Record<string, unknown>).quickActionRow = { flexDirection: "row", gap: 7, paddingHorizontal: 12, paddingBottom: 5, overflow: "hidden" };
(styles as Record<string, unknown>).quickAction = { paddingVertical: 7, paddingHorizontal: 11, borderRadius: 14, backgroundColor: "#111111", borderWidth: 1, borderColor: "#333333" };
(styles as Record<string, unknown>).quickActionText = { color: "#cccccc", fontSize: 11, fontWeight: "700" };
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

const mediaDownloadStyles = StyleSheet.create({
  button: { flexDirection: "row", alignItems: "center", gap: 12, marginTop: 10, paddingVertical: 12, paddingHorizontal: 14, borderRadius: 12, backgroundColor: "#151515", borderWidth: 1, borderColor: "#3a3a3a" },
  pressed: { backgroundColor: "#262626", transform: [{ scale: 0.98 }] },
  arrow: { color: "#ffffff", fontSize: 28, fontWeight: "300" },
  title: { color: "#ffffff", fontSize: 14, fontWeight: "700" },
  name: { color: "#888888", fontSize: 11, marginTop: 2 },
});

const idleStyles = StyleSheet.create({ shade: { ...StyleSheet.absoluteFillObject, backgroundColor: "#000", zIndex: 5 }, overlay: { ...StyleSheet.absoluteFillObject, zIndex: 6, backgroundColor: "#050505", alignItems: "center", justifyContent: "center", overflow: "hidden" }, logo: { fontSize: 52, letterSpacing: 8 }, line: { marginTop: 28 }, capabilityViewport: { width: "100%", overflow: "hidden", marginTop: 34, height: 190, justifyContent: "center" }, capabilities: { color: "#f4f4f4", fontSize: 13, lineHeight: 25, letterSpacing: 1.2, width: "100%", textAlign: "center" }, capabilityFade: { position: "absolute", left: 0, right: 0, height: 55, backgroundColor: "#050505" }, capabilityFadeTop: { top: 0 }, capabilityFadeBottom: { bottom: 0 }, cleanOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: "#0b0b0b", alignItems: "center", justifyContent: "center", overflow: "hidden" }, cleanLogo: { fontSize: 52, letterSpacing: 8 }, cleanLine: { marginTop: 28 }, cleanMeta: { width: "88%", marginTop: 18, alignItems: "center", justifyContent: "center" }, cleanMetaText: { color: "#777777", fontSize: 9, letterSpacing: 1.5, textAlign: "center" }, cleanCapabilityViewport: { width: "88%", height: 78, marginTop: 24, overflow: "hidden", alignItems: "center", justifyContent: "center" }, cleanCapabilities: { color: "#f4f4f4", fontSize: 12, lineHeight: 24, letterSpacing: 0.8, textAlign: "center" } });

// The idle scene uses a soft matte black instead of absolute OLED black.
(idleStyles as Record<string, unknown>).overlay = { ...StyleSheet.flatten(idleStyles.overlay), backgroundColor: "#0b0b0b" };
(idleStyles as Record<string, unknown>).capabilityFade = { ...StyleSheet.flatten(idleStyles.capabilityFade), backgroundColor: "#0b0b0b" };
(idleStyles as Record<string, unknown>).cleanOverlay = { ...StyleSheet.flatten(idleStyles.overlay), backgroundColor: "#0b0b0b", alignItems: "center", justifyContent: "center", overflow: "hidden" };
(idleStyles as Record<string, unknown>).cleanLogo = { fontSize: 52, letterSpacing: 8 };
(idleStyles as Record<string, unknown>).cleanLine = { marginTop: 28 };
(idleStyles as Record<string, unknown>).cleanMeta = { width: "88%", marginTop: 18, alignItems: "center", justifyContent: "center" };
(idleStyles as Record<string, unknown>).cleanMetaText = { color: "#777777", fontSize: 9, letterSpacing: 1.5, textAlign: "center" };
(idleStyles as Record<string, unknown>).cleanCapabilityViewport = { width: "88%", height: 78, marginTop: 24, overflow: "hidden", alignItems: "center", justifyContent: "center" };
(idleStyles as Record<string, unknown>).cleanCapabilities = { color: "#f4f4f4", fontSize: 12, lineHeight: 24, letterSpacing: 0.8, textAlign: "center" };
const historyStyles = StyleSheet.create({ handle: { display: "none" }, arrow: { color: "#ffffff", fontSize: 36, fontWeight: "300" }, backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.72)", justifyContent: "flex-start" }, panel: { width: "86%", height: "72%", marginTop: 92, backgroundColor: "#000000", padding: 22, paddingTop: 24, borderTopRightRadius: 18, borderBottomRightRadius: 18 }, panelClose: { color: "#ffffff", fontSize: 32, fontWeight: "300", paddingVertical: 2 }, title: { color: "#ffffff", fontSize: 24, fontWeight: "700", marginBottom: 18 }, empty: { color: "#ffffff", opacity: 0.6, fontSize: 14 } });
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
  sendButton: { width: 34, height: 38, alignItems: "center", justifyContent: "center" }, stopAudioButton: { marginHorizontal: 12, marginBottom: 4, paddingVertical: 8, alignItems: "center", borderRadius: 10, backgroundColor: "#1d1d1d" }, sendIcon: { color: "#ffffff", fontSize: 21, fontWeight: "700" }, inputMask: { display: "none" }, inputGlow: { height: 0.5, backgroundColor: "#ffffff", opacity: 0.72, shadowColor: "#ffffff", shadowOpacity: 0.45, shadowRadius: 4, elevation: 2 },
});
