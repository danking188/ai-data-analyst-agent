import { BarChart3, LockKeyhole, LogIn, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toApiError } from "../../api/errors";
import { Button } from "../../components/ui/Button";

export function LoginPage({
  loginError,
  registerError,
  loading,
  registrationEnabled,
  onLogin,
  onRegister,
}: {
  loginError: Error | null;
  registerError: Error | null;
  loading: boolean;
  registrationEnabled: boolean;
  onLogin: (username: string, password: string) => void;
  onRegister: (username: string, password: string) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setValidationError(null);
    if (mode === "register") {
      if (password !== confirmation) {
        setValidationError("两次输入的密码不一致");
        return;
      }
      onRegister(username.trim(), password);
      return;
    }
    onLogin(username.trim(), password);
  };
  const switchMode = (nextMode: "login" | "register") => {
    setMode(nextMode);
    setPassword("");
    setConfirmation("");
    setValidationError(null);
  };
  const error = mode === "login" ? loginError : registerError;
  return (
    <main className="login-page">
      <form className="login-panel" onSubmit={submit}>
        <div className="login-brand"><span><BarChart3 size={23} /></span><strong>DataTrace</strong></div>
        <div className="auth-tabs" role="tablist" aria-label="账号操作">
          <button aria-selected={mode === "login"} onClick={() => switchMode("login")} role="tab" type="button"><LogIn size={16} />登录</button>
          {registrationEnabled ? <button aria-selected={mode === "register"} onClick={() => switchMode("register")} role="tab" type="button"><UserPlus size={16} />注册</button> : null}
        </div>
        <div className="login-heading">{mode === "login" ? <LockKeyhole size={22} /> : <UserPlus size={22} />}<div><h1>{mode === "login" ? "登录分析工作台" : "创建分析账号"}</h1><p>{mode === "login" ? "数据、分析结果和导出文件仅对授权用户开放。" : "每个账号拥有独立的项目和数据空间。"}</p></div></div>
        <label className="field"><span>用户名</span><input autoCapitalize="none" autoComplete="username" autoFocus pattern="[A-Za-z0-9][A-Za-z0-9_.-]{2,31}" required value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label className="field"><span>密码</span><input autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 12 : 1} required type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {mode === "register" ? <label className="field"><span>确认密码</span><input autoComplete="new-password" minLength={12} required type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label> : null}
        {validationError ? <p className="login-error" role="alert">{validationError}</p> : null}
        {error ? <p className="login-error" role="alert">{toApiError(error).message}</p> : null}
        <Button disabled={loading || !username.trim() || !password || (mode === "register" && !confirmation)} icon={mode === "login" ? <LogIn size={17} /> : <UserPlus size={17} />} type="submit" variant="primary">{loading ? "正在处理" : mode === "login" ? "登录" : "创建账号"}</Button>
      </form>
    </main>
  );
}
