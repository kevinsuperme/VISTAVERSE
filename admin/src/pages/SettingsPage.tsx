import { useEffect, useState } from "react";
import { useBlocker, useSearchParams } from "react-router-dom";
import { Loader2, Save } from "lucide-react";
import { OssSettingsPanel } from "@/components/settings/OssSettingsPanel";
import { PaymentSettingsPanel } from "@/components/settings/PaymentSettingsPanel";
import { RoutingSettingsPanel } from "@/components/settings/RoutingSettingsPanel";
import { RuntimeSettingsPanel } from "@/components/settings/RuntimeSettingsPanel";
import { SiteSettingsPanel } from "@/components/settings/SiteSettingsPanel";
import {
  SettingsSaveProvider,
  useSettingsSaveSlot,
} from "@/components/settings/SettingsSaveContext";
import { cn } from "@/lib/utils";
import { AdminConfirmDialog } from "@/components/admin/AdminConfirmDialog";
import { hasPermission } from "@/lib/permissions";

type SettingsTab = "routing" | "runtime" | "oss" | "payment" | "site";

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "routing", label: "模型" },
  { id: "runtime", label: "运行参数" },
  { id: "oss", label: "存储 OSS" },
  { id: "payment", label: "支付计费" },
  { id: "site", label: "站点工具" },
];

// 页头：标题 + 统一保存按钮
function SettingsPageHeader() {
  const { action } = useSettingsSaveSlot();
  return (
    <header className="settings-page-hero">
      <div className="min-w-0">
        <h2 className="settings-page-title">系统设置</h2>
        <p className="settings-head-desc">
          TokenFree API Key、运行参数、OSS / 易支付 / 计费与站点配置；密钥加密存库，留空保存不修改。
        </p>
      </div>
      {action ? <div role="status" aria-live="polite" className="text-xs text-[var(--admin-muted)]">{action.feedback || (action.dirty ? "有未保存的修改" : "配置已同步")}</div> : null}
      {action && hasPermission("settings:write") ? (
        <button
          type="button"
          className="admin-btn admin-btn-primary settings-save-btn"
          disabled={action.saving}
          onClick={() => void action.onSave()}
        >
          {action.saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          {action.label ?? "保存"}
        </button>
      ) : null}
    </header>
  );
}

// 系统设置内容区
function SettingsPageInner() {
  const [params, setParams] = useSearchParams();
  const requestedTab = TABS.find((item) => item.id === params.get("tab"))?.id ?? "routing";
  const [tab, setTab] = useState<SettingsTab>(requestedTab);
  const [pendingTab, setPendingTab] = useState<SettingsTab | null>(null);
  const { action } = useSettingsSaveSlot();
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    Boolean(action?.dirty || action?.saving) && currentLocation.pathname !== nextLocation.pathname,
  );

  function selectTab(next: SettingsTab) {
    setTab(next);
    setParams((prev) => { const updated = new URLSearchParams(prev); updated.set("tab", next); return updated; });
  }

  useEffect(() => {
    if (requestedTab === tab) return;
    if (action?.dirty || action?.saving) {
      if (!action.saving) setPendingTab(requestedTab);
      setParams((prev) => { const updated = new URLSearchParams(prev); updated.set("tab", tab); return updated; }, { replace: true });
    } else setTab(requestedTab);
  }, [requestedTab, tab, action?.dirty, action?.saving, setParams]);

  useEffect(() => {
    if (!action?.dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [action?.dirty]);

  return (
    <div className="settings-page admin-page">
      <SettingsPageHeader />

      <div className="settings-tabs" role="tablist" aria-label="系统设置分区">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={cn("settings-tab", tab === id && "is-active")}
            aria-controls={`settings-panel-${id}`}
            id={`settings-tab-${id}`}
            disabled={action?.saving}
            onClick={() => {
              if (id === tab) return;
              if (action?.dirty) setPendingTab(id);
              else selectTab(id);
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="settings-main" role="tabpanel" id={`settings-panel-${tab}`} aria-labelledby={`settings-tab-${tab}`}>
        {tab === "routing" ? <RoutingSettingsPanel /> : null}
        {tab === "runtime" ? <RuntimeSettingsPanel /> : null}
        {tab === "oss" ? <OssSettingsPanel /> : null}
        {tab === "payment" ? <PaymentSettingsPanel /> : null}
        {tab === "site" ? <SiteSettingsPanel /> : null}
      </div>
      <AdminConfirmDialog
        open={blocker.state === "blocked"}
        title={action?.saving ? "正在保存设置" : "离开并放弃未保存的修改？"}
        description={action?.saving ? "请等待保存完成后再离开页面。" : "当前修改尚未保存；留在页面可继续编辑或保存。"}
        confirmLabel="放弃修改并离开"
        loading={action?.saving}
        onOpenChange={(next) => { if (!next && blocker.state === "blocked") blocker.reset(); }}
        onConfirm={() => { if (blocker.state === "blocked" && !action?.saving) blocker.proceed(); }}
      />
      <AdminConfirmDialog
        open={pendingTab !== null}
        title="放弃未保存的修改？"
        description="切换分区会丢弃当前修改和未保存的密钥输入。"
        confirmLabel="放弃修改并切换"
        onOpenChange={(next) => { if (!next) setPendingTab(null); }}
        onConfirm={() => { if (pendingTab) selectTab(pendingTab); setPendingTab(null); }}
      />
    </div>
  );
}

export function SettingsPage() {
  return (
    <SettingsSaveProvider>
      <SettingsPageInner />
    </SettingsSaveProvider>
  );
}
