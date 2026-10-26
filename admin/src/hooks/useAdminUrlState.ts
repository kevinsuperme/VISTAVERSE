import { useCallback, type Dispatch, type SetStateAction } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { updateAdminQuery } from "@/lib/adminQueryState";

type UrlValue = string | number | null;

function readValue<T extends UrlValue>(raw: string | null, fallback: T): T {
  if (raw === null || raw === "") return fallback;
  if (typeof fallback === "string") return raw as T;
  const value = Number(raw);
  return (Number.isSafeInteger(value) && value > 0 ? value : fallback) as T;
}

/** Persist list context while preserving independent detail and tab query keys. */
export function useAdminUrlState<T extends UrlValue>(key: string, fallback: T): [T, Dispatch<SetStateAction<T>>] {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const value = readValue(params.get(key), fallback);
  const setValue = useCallback<Dispatch<SetStateAction<T>>>((next) => {
    updateAdminQuery(location, location.search, (current) => {
      const previous = readValue(current.get(key), fallback);
      const resolved = typeof next === "function" ? next(previous) : next;
      if (resolved === fallback || resolved === null || resolved === "") current.delete(key);
      else current.set(key, String(resolved));
    }, setParams);
  }, [key, fallback, location, setParams]);
  return [value, setValue];
}
