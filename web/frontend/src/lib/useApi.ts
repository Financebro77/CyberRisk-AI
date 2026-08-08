import { useCallback, useRef, useState } from 'react';

/**
 * Small async-runner hook for the synchronous tool endpoints.
 * Heavy Monte Carlo sims run server-side (a few seconds), so each run shows
 * a loading spinner until the JSON arrives.  Errors are surfaced as a
 * friendly message rather than a crash.
 */
export function useApi<TArgs extends unknown[], TData>(fn: (...args: TArgs) => Promise<TData>) {
  const [data, setData] = useState<TData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const runRef = useRef(0);

  const run = useCallback(
    async (...args: TArgs) => {
      const id = ++runRef.current;
      setLoading(true);
      setError(null);
      try {
        const result = await fn(...args);
        if (id === runRef.current) setData(result);
        return result;
      } catch (err) {
        if (id === runRef.current) {
          setError(err instanceof Error ? err.message : 'Something went wrong');
          setData(null);
        }
        return undefined;
      } finally {
        if (id === runRef.current) setLoading(false);
      }
    },
    [fn],
  );

  const reset = useCallback(() => {
    runRef.current++;
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { data, loading, error, run, reset };
}
