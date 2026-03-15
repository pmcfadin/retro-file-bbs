import { useState, useCallback } from "react";

export interface Toast {
  msg: string;
  error?: boolean;
}

export function useToast() {
  const [toast, setToast] = useState<Toast | null>(null);

  const showToast = useCallback((msg: string, error = false) => {
    setToast({ msg, error });
    setTimeout(() => setToast(null), 3000);
  }, []);

  return { toast, showToast };
}
