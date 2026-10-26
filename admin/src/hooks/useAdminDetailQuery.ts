import { useCallback, useMemo } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { updateAdminQuery } from "@/lib/adminQueryState";

/** 通过 URL query 打开/关闭详情弹层（可刷新恢复） */
export function useAdminDetailQuery(paramKey: string) {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();

  const id = useMemo(() => {
    const raw = searchParams.get(paramKey);
    if (!raw) return null;
    const n = Number(raw);
    return Number.isSafeInteger(n) && n > 0 ? n : null;
  }, [paramKey, searchParams]);

  const open = useCallback(
    (nextId: number) => {
      if (!Number.isSafeInteger(nextId) || nextId <= 0) return;
      updateAdminQuery(location, location.search, (params) => { params.set(paramKey, String(nextId)); }, setSearchParams, false);
    },
    [paramKey, location, setSearchParams],
  );

  const close = useCallback(() => {
    updateAdminQuery(location, location.search, (params) => { params.delete(paramKey); }, setSearchParams);
  }, [paramKey, location, setSearchParams]);

  return { id, open, close, isOpen: id != null };
}
