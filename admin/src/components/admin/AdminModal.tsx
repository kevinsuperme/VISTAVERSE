import { useRef, type ReactNode } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type AdminModalSize = "md" | "lg" | "xl" | "full";

type AdminModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: AdminModalSize;
  className?: string;
  bodyClassName?: string;
  presentation?: "dialog" | "drawer";
  busy?: boolean;
};

const SIZE_CLASS: Record<AdminModalSize, string> = {
  md: "admin-modal--md",
  lg: "admin-modal--lg",
  xl: "admin-modal--xl",
  full: "admin-modal--full",
};

// 管理端统一弹窗壳（标题 / 内容 / 底栏）
export function AdminModal({
  open,
  onOpenChange,
  title,
  subtitle,
  children,
  footer,
  size = "lg",
  className,
  bodyClassName,
  presentation = "dialog",
  busy = false,
}: AdminModalProps) {
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <DialogContent aria-busy={busy}
        onOpenAutoFocus={() => { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          const target = returnFocus.current;
          if (target?.isConnected && target !== document.body) target.focus();
          else document.getElementById("admin-main-content")?.focus();
        }}
        onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }}
        onPointerDownOutside={(event) => { if (busy) event.preventDefault(); }}
        className={cn("admin-modal", SIZE_CLASS[size], presentation === "drawer" && "admin-drawer", busy && "admin-modal--busy", className)}>
        <DialogHeader className="admin-modal-header">
          <DialogTitle className="admin-modal-title">{title}</DialogTitle>
          <DialogDescription className={cn("admin-modal-subtitle", !subtitle && "sr-only")}>{subtitle || "查看详情或完成当前操作"}</DialogDescription>
        </DialogHeader>
        {children ? <div className={cn("admin-modal-body", bodyClassName)}>{children}</div> : null}
        {footer ? <div className="admin-modal-footer">{footer}</div> : null}
      </DialogContent>
    </Dialog>
  );
}
