import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type AdminModelSettings } from "@/api/client";
import { hasPermission } from "@/lib/permissions";

// 加载 / 保存管理端 flat 配置（DB 覆盖 env）
export function useAdminModelSettings() {
  const [form, setForm] = useState<AdminModelSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [baseline, setBaseline] = useState("");
  const [saveFeedback, setSaveFeedback] = useState("");
  const dirty = form !== null && JSON.stringify(form) !== baseline;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await api<AdminModelSettings>("/api/admin/settings/models");
      setForm(next);
      setBaseline(JSON.stringify(next));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载配置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function patchField<K extends keyof AdminModelSettings>(key: K, value: AdminModelSettings[K]) {
    setSaveFeedback("");
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  async function save(body: Record<string, unknown>, successMessage = "配置已保存") {
    if (saving || !hasPermission("settings:write")) return false;
    if (Object.values(body).some((value) => typeof value === "number" && !Number.isFinite(value))) {
      setSaveFeedback("保存失败：请填写有效数字");
      return false;
    }
    setSaving(true);
    setSaveFeedback("");
    try {
      const response = await api<{ settings: AdminModelSettings }>("/api/admin/settings/models", { method: "PATCH", body: JSON.stringify(body) });
      setForm(response.settings);
      setBaseline(JSON.stringify(response.settings));
      setSaveFeedback(`${successMessage} · ${new Date().toLocaleTimeString()}`);
      toast.success(successMessage);
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存失败";
      setSaveFeedback(`保存失败：${message}，修改已保留`);
      toast.error(message);
      return false;
    } finally {
      setSaving(false);
    }
  }

  return { form, loading, saving, error, dirty, saveFeedback, load, patchField, save };
}
