export type AuthResponse = { access_token: string; token_type: string };
export type Account = {
  id: number; name: string; email: string; telegram_linked: boolean; owner?: boolean;
  payment_method_saved?: boolean; subscription_expires_at: string | null; auto_renew: boolean;
  subscription_plan?: string; legal_accepted?: boolean; trial_active?: boolean; trial_days?: number;
};
export type ChatItem = { id: string; role: "user" | "assistant"; text: string; createdAt: number; mediaUrl?: string; mediaMime?: string; filename?: string; artifactId?: string; streaming?: boolean };
export type MemorySection = { category: string; title: string; items: { label: string; value: string }[] };
export type MemoryAudit = { category: string; key: string; confirmed: boolean; first_seen?: string; last_seen?: string; replacements: number };
export type MemoryResponse = { sections: MemorySection[]; permanent?: boolean; description?: string; audit?: MemoryAudit[] };
export type Reminder = { id: number; text: string; kind?: string; remind_at: string };
export type Subscription = { active: boolean; trial_active?: boolean; trial_days?: number; plan: string; plans: { id: string; name: string; price: string; credits: number }[]; price_rub: string; days: number; expires_at: string | null; auto_renew: boolean };
export type Agent = { status?: string; goal?: string; horizon_minutes?: number; tasks?: { id: string; title: string; status: string; depends_on?: string[]; result?: string }[]; current_task?: string; completed_steps?: number; total_steps?: number } | null;
export type Workflow = Record<string, unknown> | null;
export type MediaJob = { id: string; kind: "image" | "video"; status: "queued" | "running" | "completed" | "failed" | "cancelled"; progress: number; filename?: string; media_type?: string; data_base64?: string; error?: string };
export type MyDay = { date: string; focus: { kind: string; title: string; detail: string; at: string | null; priority: string; loop_index?: number }[]; next_step: { title: string; prompt: string }; counts: { reminders: number; open_loops: number; goals: number }; memory_permanent: boolean };
export type Scenario = { id: string; title: string; prompt: string; mode: string };
export type ApiErrorShape = { detail?: string; message?: string; error?: string };
