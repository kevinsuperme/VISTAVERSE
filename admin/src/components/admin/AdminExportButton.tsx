import { useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { downloadAdminCsv } from "@/lib/downloadAdminCsv";

export function AdminExportButton({ path, filename, label = "导出 CSV", disabled = false }: {
  path: string; filename: string; label?: string; disabled?: boolean;
}) {
  const [pending, setPending] = useState(false);
  const locked = useRef(false);
  async function download() {
    if (locked.current) return;
    locked.current = true; setPending(true);
    try { await downloadAdminCsv(path, filename); toast.success("导出完成"); }
    catch (error) { toast.error(error instanceof Error ? error.message : "导出失败，请重试"); }
    finally { locked.current = false; setPending(false); }
  }
  return <Button variant="outline" size="sm" disabled={disabled || pending} onClick={() => void download()}>
    {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
    {pending ? "正在导出…" : label}
  </Button>;
}
