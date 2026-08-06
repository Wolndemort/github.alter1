import AsyncStorage from "@react-native-async-storage/async-storage";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Button, FlatList, KeyboardAvoidingView, Platform, SafeAreaView, StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "./src/api/client";

const Stack = createNativeStackNavigator();

function AuthScreen({ onAuthenticated }: { onAuthenticated: (token: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [registerMode, setRegisterMode] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true); setError("");
    try {
      const result = registerMode ? await api.register(email, password) : await api.login(email, password);
      await AsyncStorage.setItem("alter_access_token", result.access_token);
      onAuthenticated(result.access_token);
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось войти"); }
    finally { setBusy(false); }
  };

  return <SafeAreaView style={styles.container}><View style={styles.card}>
    <Text style={styles.title}>ALTER</Text><Text style={styles.subtitle}>Твой личный AI-пространство</Text>
    <TextInput autoCapitalize="none" keyboardType="email-address" placeholder="Email" placeholderTextColor="#78809a" style={styles.input} value={email} onChangeText={setEmail} />
    <TextInput secureTextEntry placeholder="Пароль" placeholderTextColor="#78809a" style={styles.input} value={password} onChangeText={setPassword} />
    {error ? <Text style={styles.error}>{error}</Text> : null}
    {busy ? <ActivityIndicator color="#9b8cff" /> : <Button title={registerMode ? "Создать аккаунт" : "Войти"} onPress={submit} />}
    <Button title={registerMode ? "У меня уже есть аккаунт" : "Создать аккаунт"} onPress={() => setRegisterMode(!registerMode)} />
  </View><StatusBar style="light" /></SafeAreaView>;
}

function ChatScreen({ token, onLogout }: { token: string; onLogout: () => void }) {
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<{ id: string; role: string; text: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const send = async () => {
    const text = message.trim(); if (!text || busy) return;
    setMessage(""); setItems((old) => [...old, { id: `${Date.now()}u`, role: "user", text }]); setBusy(true);
    try { const result = await api.sendMessage(token, text); setItems((old) => [...old, { id: `${Date.now()}a`, role: "assistant", text: result.reply }]); }
    catch (err) { setItems((old) => [...old, { id: `${Date.now()}e`, role: "assistant", text: err instanceof Error ? err.message : "Ошибка запроса" }]); }
    finally { setBusy(false); }
  };
  return <SafeAreaView style={styles.container}><KeyboardAvoidingView style={styles.chat} behavior={Platform.OS === "ios" ? "padding" : undefined}>
    <View style={styles.header}><Text style={styles.headerTitle}>ALTER</Text><Button title="Выйти" onPress={onLogout} /></View>
    <FlatList data={items} keyExtractor={(item) => item.id} contentContainerStyle={styles.messages} renderItem={({ item }) => <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.aiBubble]}><Text style={styles.message}>{item.text}</Text></View>} />
    <View style={styles.composer}><TextInput style={[styles.input, styles.composerInput]} placeholder="Напиши ALTER..." placeholderTextColor="#78809a" value={message} onChangeText={setMessage} onSubmitEditing={send} /><Button title={busy ? "..." : "➤"} onPress={send} /></View>
  </KeyboardAvoidingView><StatusBar style="light" /></SafeAreaView>;
}

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { AsyncStorage.getItem("alter_access_token").then((value) => { setToken(value); setLoading(false); }); }, []);
  if (loading) return <SafeAreaView style={styles.container}><ActivityIndicator color="#9b8cff" /></SafeAreaView>;
  return <NavigationContainer><Stack.Navigator screenOptions={{ headerShown: false }}>{token ? <Stack.Screen name="Chat">{() => <ChatScreen token={token} onLogout={() => { AsyncStorage.removeItem("alter_access_token"); setToken(null); }} />}</Stack.Screen> : <Stack.Screen name="Auth">{() => <AuthScreen onAuthenticated={setToken} />}</Stack.Screen>}</Stack.Navigator></NavigationContainer>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0e1020", justifyContent: "center" }, card: { margin: 24, gap: 14 }, title: { color: "#fff", fontSize: 42, fontWeight: "800", textAlign: "center" }, subtitle: { color: "#aeb4ca", textAlign: "center", marginBottom: 18 }, input: { backgroundColor: "#1b1f36", color: "#fff", borderRadius: 12, padding: 14, fontSize: 16 }, error: { color: "#ff8d9b" }, chat: { flex: 1 }, header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 16 }, headerTitle: { color: "#fff", fontSize: 24, fontWeight: "800" }, messages: { padding: 16, gap: 10 }, bubble: { maxWidth: "86%", padding: 12, borderRadius: 16 }, userBubble: { alignSelf: "flex-end", backgroundColor: "#6558c9" }, aiBubble: { alignSelf: "flex-start", backgroundColor: "#1b1f36" }, message: { color: "#fff", fontSize: 16 }, composer: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12 }, composerInput: { flex: 1 },
});
