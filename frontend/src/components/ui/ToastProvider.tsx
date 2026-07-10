import { CheckCircle2, CircleAlert, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type ToastTone = "success" | "error";

interface ToastItem {
  id: string;
  message: string;
  tone: ToastTone;
}

interface ToastContextValue {
  pushToast: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const remove = useCallback((id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);
  const pushToast = useCallback((message: string, tone: ToastTone = "success") => {
    const id = crypto.randomUUID();
    setItems((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => remove(id), 4_000);
  }, [remove]);
  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="toast-region">
        {items.map((item) => {
          const Icon = item.tone === "success" ? CheckCircle2 : CircleAlert;
          return (
            <div className={`toast toast--${item.tone}`} key={item.id} role="status">
              <Icon aria-hidden="true" size={17} />
              <span>{item.message}</span>
              <button aria-label="关闭通知" className="icon-button" onClick={() => remove(item.id)}>
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside ToastProvider");
  return value;
}
