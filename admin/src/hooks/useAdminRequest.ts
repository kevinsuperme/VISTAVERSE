import { useCallback, useEffect, useRef, useState } from "react";

/** Ignore stale responses so rapid pagination cannot replace the latest result. */
export function useAdminRequest<T>() {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);

  useEffect(() => () => { sequence.current += 1; }, []);

  const run = useCallback(async (request: () => Promise<T>) => {
    const current = ++sequence.current;
    setLoading(true);
    setError(null);
    try {
      const result = await request();
      if (current === sequence.current) setData(result);
    } catch (cause) {
      if (current === sequence.current) setError(cause instanceof Error ? cause.message : "请求失败，请重试");
    } finally {
      if (current === sequence.current) setLoading(false);
    }
  }, []);

  const cancel = useCallback(() => { sequence.current += 1; }, []);
  const reset = useCallback(() => {
    sequence.current += 1;
    setData(null);
    setError(null);
    setLoading(true);
  }, []);

  return { data, loading, error, run, cancel, reset };
}
