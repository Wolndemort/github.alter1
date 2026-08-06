import AsyncStorage from "@react-native-async-storage/async-storage";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import { Audio } from "expo-av";
import * as ImagePicker from "expo-image-picker";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Animated, Button, Easing, FlatList, KeyboardAvoidingView, Linking, Modal, Platform, Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from "react-native";
import { AccountResponse, MemoryResponse, api } from "./src/api/client";

const Stack = createNativeStackNavigator();
type AuthProps = { onAuthenticated: (token: string) => void };

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

  return <View style={styles.intro}><Animated.View style={{ opacity, transform: [{ scale }] }}><Text style={styles.introLogo}>ALTER</Text><Text style={styles.introCaption}>PERSONAL INTELLIGENCE</Text></Animated.View><Animated.View style={[styles.introLine, { width: line.interpolate({ inputRange: [0, 1], outputRange: [0, 150] }) }]} /><StatusBar style="light" /></View>;
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
    }, 24);
    return () => clearInterval(timer);
  }, [text]);
  return <Text style={styles.message}>{visible}{visible.length < text.length ? <Text style={styles.cursor}>▋</Text> : null}</Text>;
}

export function VoiceButton({ onRecorded }: { onRecorded: (uri: string) => void }) {
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const pulse = React.useRef(new Animated.Value(1)).current;
  const pulseLoop = React.useRef<Animated.CompositeAnimation | null>(null);
  const start = async () => {
    const permission = await Audio.requestPermissionsAsync();
    if (!permission.granted) return;
    await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
    const result = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
    setRecording(result.recording);
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
    if (uri) onRecorded(uri);
  };
  return <Pressable onPressIn={start} onPressOut={stop} accessibilityLabel="Записать голосовое сообщение"><Animated.View style={[mediaStyles.voiceHalo, { transform: [{ scale: pulse }] }, recording ? mediaStyles.voiceHaloActive : null]}><Animated.View style={[mediaStyles.voiceButton, recording ? mediaStyles.voiceButtonActive : null]}><Text style={mediaStyles.voiceIcon}>MIC</Text></Animated.View></Animated.View></Pressable>;
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

  const submit = async () => {
    if (registerMode && !email.trim()) { setError("Введите email"); return; }
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
    {busy ? <ActivityIndicator color="#9b8cff" /> : <Button title="Подтвердить email" onPress={verify} />}
    <Button title={resending ? "Отправляем..." : "Отправить код ещё раз"} onPress={resend} disabled={busy || resending} />
  </View><StatusBar style="light" /></SafeAreaView>;

  return <SafeAreaView style={styles.container}><View style={styles.card}>
    <Text style={styles.title}>ALTER</Text><Text style={styles.subtitle}>Твоё личное AI-пространство</Text>
    <TextInput autoCapitalize="none" keyboardType="email-address" placeholder="Email" placeholderTextColor="#78809a" style={styles.input} value={email} onChangeText={setEmail} />
    <TextInput secureTextEntry placeholder="Пароль" placeholderTextColor="#78809a" style={styles.input} value={password} onChangeText={setPassword} />
    {error ? <Text style={styles.error}>{error}</Text> : null}
    {busy ? <ActivityIndicator color="#9b8cff" /> : <Button title={registerMode ? "Создать аккаунт" : "Войти"} onPress={submit} />}
    <Button title={registerMode ? "У меня уже есть аккаунт" : "Создать аккаунт"} onPress={() => setRegisterMode(!registerMode)} />
  </View><StatusBar style="light" /></SafeAreaView>;
}

export function ChatScreen({ token, onLogout }: { token: string; onLogout: () => void }) {
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<{ id: string; role: string; text: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [memoryData, setMemoryData] = useState<MemoryResponse | null>(null);
  const [memoryVisible, setMemoryVisible] = useState(false);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);
  const [menuError, setMenuError] = useState("");
  const [attachment, setAttachment] = useState<{ uri: string; type: "image" | "video" | "audio" } | null>(null);
  useEffect(() => { api.account(token).then(setAccount).catch(() => undefined); }, [token]);
  const send = async () => {
    const text = message.trim(); if ((!text && !attachment) || busy) return;
    const currentAttachment = attachment;
    setMessage(""); setAttachment(null); setItems((old) => [...old, { id: `${Date.now()}u`, role: "user", text: currentAttachment ? `${text || "Вложение"} · ${currentAttachment.type}` : text }]); setBusy(true);
    try { const result = currentAttachment ? await api.sendMedia(token, text, currentAttachment.uri, currentAttachment.type) : await api.sendMessage(token, text); setItems((old) => [...old, { id: `${Date.now()}a`, role: "assistant", text: result.reply }]); }
    catch (err) { setItems((old) => [...old, { id: `${Date.now()}e`, role: "assistant", text: err instanceof Error ? err.message : "Ошибка запроса" }]); }
    finally { setBusy(false); }
  };
  const openTelegramLink = async () => {
    setMenuError("");
    try { const result = await api.startTelegramLink(token); await Linking.openURL(result.url); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось открыть Telegram"); }
  };
  const buySubscription = async () => {
    setMenuError("");
    try { const result = await api.createPayment(token); await Linking.openURL(result.payment_url); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Оплата пока недоступна"); }
  };
  const openMemory = async () => {
    setMemoryVisible(true); setMemoryLoading(true); setMenuVisible(false);
    try { setMemoryData(await api.memory(token)); }
    catch (err) { setMenuError(err instanceof Error ? err.message : "Не удалось загрузить память"); }
    finally { setMemoryLoading(false); }
  };
  const pickMedia = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) { setMenuError("Разреши доступ к медиатеке"); return; }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.All, quality: 0.85 });
    if (!result.canceled && result.assets[0]) {
      const asset = result.assets[0];
      setAttachment({ uri: asset.uri, type: asset.type === "video" ? "video" : "image" });
    }
  };
  const keepVoice = (uri: string) => setAttachment({ uri, type: "audio" });
  const memoryEntries = Object.entries(memoryData?.memory || {}).filter(([, value]) => value);
  return <SafeAreaView style={styles.container}><KeyboardAvoidingView style={styles.chat} behavior={Platform.OS === "ios" ? "padding" : undefined}>
    <View style={styles.header}><Text style={styles.headerTitle}>ALTER</Text><Pressable style={[styles.menuButton, premiumStyles.menuButton]} onPress={() => setMenuVisible(true)}><Text style={styles.menuIcon}>•••</Text></Pressable></View>
    <FlatList data={items} keyExtractor={(item) => item.id} contentContainerStyle={styles.messages} renderItem={({ item }) => <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.aiBubble]}>{item.role === "assistant" ? <TypingText text={item.text} /> : <Text style={[styles.message, styles.userMessage]}>{item.text}</Text>}</View>} />
    {attachment ? <View style={mediaStyles.attachmentChip}><Text style={mediaStyles.attachmentText}>{attachment.type === "audio" ? "Голосовое сообщение" : attachment.type === "video" ? "Видео прикреплено" : "Фото прикреплено"}</Text><Pressable onPress={() => setAttachment(null)}><Text style={mediaStyles.removeAttachment}>×</Text></Pressable></View> : null}
    <View style={styles.composer}><Pressable style={mediaStyles.attachButton} onPress={pickMedia} accessibilityLabel="Прикрепить фото или видео"><Text style={mediaStyles.attachIcon}>＋</Text></Pressable><TextInput style={[styles.input, styles.composerInput]} placeholder="Напиши ALTER..." placeholderTextColor="#78809a" value={message} onChangeText={setMessage} onSubmitEditing={send} /><VoiceButton onRecorded={keepVoice} /><Pressable style={mediaStyles.sendButton} onPress={send} accessibilityLabel="Отправить сообщение"><Text style={mediaStyles.sendIcon}>{busy ? "…" : "↑"}</Text></Pressable></View>
  </KeyboardAvoidingView>
  <Modal visible={menuVisible} transparent animationType="fade" onRequestClose={() => setMenuVisible(false)}>
    <Pressable style={styles.modalBackdrop} onPress={() => setMenuVisible(false)}>
      <Pressable style={[styles.menuCard, premiumStyles.menuCard]} onPress={(event) => event.stopPropagation()}>
        <Text style={[styles.menuTitle, premiumStyles.menuTitle]}>{account?.name || "Кабинет"}</Text>
        <Text style={[styles.menuEmail, premiumStyles.menuEmail]}>{account?.email || ""}</Text>
        <View style={styles.menuDivider} />
        <Text style={[styles.menuStatus, premiumStyles.menuStatus]}>{account?.telegram_linked ? "Telegram подключён" : "Telegram не подключён"}</Text>
        {account?.subscription_expires_at ? <Text style={[styles.menuStatus, premiumStyles.menuStatus]}>Подписка до {new Date(account.subscription_expires_at).toLocaleDateString()}</Text> : <Text style={[styles.menuStatus, premiumStyles.menuStatus]}>Подписка не активна</Text>}
        {menuError ? <Text style={styles.error}>{menuError}</Text> : null}
        <Pressable style={premiumStyles.menuAction} onPress={openMemory}><Text style={premiumStyles.menuActionText}>Память</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        {!account?.telegram_linked ? <Pressable style={premiumStyles.menuAction} onPress={openTelegramLink}><Text style={premiumStyles.menuActionText}>Синхронизировать память</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable> : null}
        <Pressable style={premiumStyles.menuAction} onPress={buySubscription}><Text style={premiumStyles.menuActionText}>Подписка</Text><Text style={premiumStyles.menuActionArrow}>→</Text></Pressable>
        <Pressable style={[premiumStyles.menuAction, premiumStyles.menuLogout]} onPress={() => { setMenuVisible(false); onLogout(); }}><Text style={premiumStyles.menuActionText}>Выйти</Text><Text style={premiumStyles.menuActionArrow}>↗</Text></Pressable>
      </Pressable>
    </Pressable>
  </Modal>
  <Modal visible={memoryVisible} animationType="slide" onRequestClose={() => setMemoryVisible(false)}>
    <SafeAreaView style={styles.memoryScreen}>
      <View style={styles.memoryHeader}><Text style={styles.memoryTitle}>Память</Text><Button title="Закрыть" onPress={() => setMemoryVisible(false)} /></View>
      {memoryLoading ? <ActivityIndicator color="#fff" /> : memoryEntries.length === 0 ? <Text style={styles.emptyMemory}>Пока здесь пусто. ALTER заполнит память по мере ваших разговоров.</Text> : <FlatList data={memoryEntries} keyExtractor={([key]) => key} contentContainerStyle={styles.memoryList} renderItem={({ item: [key, value] }) => <View style={styles.memoryRow}><Text style={styles.memoryKey}>{key.replace(/_/g, " ")}</Text><Text style={styles.memoryValue}>{Array.isArray(value) ? value.join("\n") : typeof value === "object" ? JSON.stringify(value, null, 2) : String(value)}</Text></View>} />}
    </SafeAreaView>
  </Modal>
  <StatusBar style="light" /></SafeAreaView>;
}

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [introDone, setIntroDone] = useState(false);
  useEffect(() => { AsyncStorage.getItem("alter_access_token").then((value) => { setToken(value); setLoading(false); }); }, []);
  if (!introDone) return <IntroScreen onFinished={() => setIntroDone(true)} />;
  if (loading) return <SafeAreaView style={styles.container}><ActivityIndicator color="#9b8cff" /></SafeAreaView>;
  return <NavigationContainer><Stack.Navigator screenOptions={{ headerShown: false }}>{token ? <Stack.Screen name="Chat">{() => <ChatScreen token={token} onLogout={() => { AsyncStorage.removeItem("alter_access_token"); setToken(null); }} />}</Stack.Screen> : <Stack.Screen name="Auth">{() => <AuthScreen onAuthenticated={setToken} />}</Stack.Screen>}</Stack.Navigator></NavigationContainer>;
}

const styles = StyleSheet.create({
  intro: { flex: 1, backgroundColor: "#050505", alignItems: "center", justifyContent: "center" }, introLogo: { color: "#fff", fontSize: 54, fontWeight: "800", letterSpacing: 8, textAlign: "center" }, introCaption: { color: "#666", fontSize: 9, letterSpacing: 3, textAlign: "center", marginTop: 12 }, introLine: { height: 1, backgroundColor: "#fff", opacity: 0.8, marginTop: 38 }, container: { flex: 1, backgroundColor: "#050505", justifyContent: "center" }, card: { margin: 24, gap: 14 }, title: { color: "#fff", fontSize: 42, fontWeight: "800", textAlign: "center", letterSpacing: 2 }, subtitle: { color: "#999", textAlign: "center", marginBottom: 18 }, input: { backgroundColor: "#151515", color: "#fff", borderRadius: 12, padding: 14, fontSize: 16, borderWidth: 1, borderColor: "#292929" }, error: { color: "#ff9d9d" }, chat: { flex: 1 }, header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 16 }, headerTitle: { color: "#fff", fontSize: 24, fontWeight: "800", letterSpacing: 2 }, menuButton: { padding: 8 }, menuIcon: { color: "#fff", fontSize: 20, letterSpacing: 3 }, modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.72)", alignItems: "flex-end", paddingTop: 56, paddingRight: 12 }, menuCard: { width: 290, backgroundColor: "#111", borderRadius: 18, padding: 20, gap: 12, borderWidth: 1, borderColor: "#2b2b2b" }, menuTitle: { color: "#fff", fontSize: 22, fontWeight: "700" }, menuEmail: { color: "#999" }, menuStatus: { color: "#ddd", fontSize: 14 }, menuDivider: { height: 1, backgroundColor: "#292929" }, messages: { padding: 16, gap: 10 }, bubble: { maxWidth: "86%", padding: 12, borderRadius: 16 }, userBubble: { alignSelf: "flex-end", backgroundColor: "#fff" }, userMessage: { color: "#050505" }, aiBubble: { alignSelf: "flex-start", backgroundColor: "#151515", borderWidth: 1, borderColor: "#292929" }, message: { color: "#fff", fontSize: 16, lineHeight: 23 }, cursor: { color: "#fff" }, composer: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12 }, composerInput: { flex: 1 }, memoryScreen: { flex: 1, backgroundColor: "#050505" }, memoryHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 20 }, memoryTitle: { color: "#fff", fontSize: 30, fontWeight: "700" }, memoryList: { padding: 20, gap: 14 }, memoryRow: { borderBottomWidth: 1, borderBottomColor: "#292929", paddingBottom: 14, gap: 6 }, memoryKey: { color: "#888", fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }, memoryValue: { color: "#eee", fontSize: 16, lineHeight: 23 }, emptyMemory: { color: "#999", padding: 24, fontSize: 16, lineHeight: 24 },
});

const premiumStyles = StyleSheet.create({
  menuButton: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#111", borderWidth: 1, borderColor: "#302950", alignItems: "center", justifyContent: "center" },
  menuCard: { width: 310, backgroundColor: "#101016", borderRadius: 24, padding: 22, borderColor: "#3b315f", shadowColor: "#7d5cff", shadowOpacity: 0.22, shadowRadius: 24, shadowOffset: { width: 0, height: 10 }, elevation: 12 },
  menuAction: { minHeight: 48, borderRadius: 14, backgroundColor: "#17151e", borderWidth: 1, borderColor: "#282333", paddingHorizontal: 15, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  menuActionText: { color: "#fff", fontSize: 15, fontWeight: "600", letterSpacing: 0.5 },
  menuActionArrow: { color: "#fff", fontSize: 20 },
  menuTitle: { color: "#fff", fontSize: 24, fontWeight: "800", letterSpacing: 2 },
  menuEmail: { color: "#fff", fontSize: 13, letterSpacing: 0.4 },
  menuStatus: { color: "#fff", fontSize: 14, letterSpacing: 0.2 },
  menuLogout: { backgroundColor: "transparent", borderColor: "#292632" },
});

const mediaStyles = StyleSheet.create({
  attachmentChip: { marginHorizontal: 12, marginBottom: 2, padding: 9, borderRadius: 10, backgroundColor: "#1d1d1d", flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  attachmentText: { color: "#ddd", fontSize: 13 }, removeAttachment: { color: "#fff", fontSize: 20, paddingLeft: 12 },
  attachButton: { width: 38, height: 38, borderRadius: 19, borderWidth: 1, borderColor: "#4b416d", backgroundColor: "#15121f", alignItems: "center", justifyContent: "center" }, attachIcon: { color: "#d8ceff", fontSize: 23, lineHeight: 24, includeFontPadding: false, textAlign: "center" },
  voiceHalo: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(145, 110, 255, 0.16)", borderWidth: 1, borderColor: "rgba(161, 132, 255, 0.55)" }, voiceHaloActive: { backgroundColor: "rgba(145, 110, 255, 0.32)", borderColor: "#a990ff", shadowColor: "#956dff", shadowOpacity: 0.9, shadowRadius: 12, shadowOffset: { width: 0, height: 0 }, elevation: 10 }, voiceButton: { width: 36, height: 36, borderRadius: 18, backgroundColor: "#f7f4ff", alignItems: "center", justifyContent: "center" }, voiceButtonActive: { backgroundColor: "#b9a4ff" }, voiceIcon: { color: "#24163f", fontSize: 8, fontWeight: "800", letterSpacing: 0.8 },
  sendButton: { width: 34, height: 34, borderRadius: 17, backgroundColor: "#fff", alignItems: "center", justifyContent: "center" }, sendIcon: { color: "#050505", fontSize: 21, fontWeight: "700" },
});
