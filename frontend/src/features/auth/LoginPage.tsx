import { BarChart3, LockKeyhole } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toApiError } from "../../api/errors";
import { Button } from "../../components/ui/Button";

export function LoginPage({
  error,
  loading,
  onSubmit,
}: {
  error: Error | null;
  loading: boolean;
  onSubmit: (username: string, password: string) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(username.trim(), password);
  };
  return (
    <main className="login-page">
      <form className="login-panel" onSubmit={submit}>
        <div className="login-brand"><span><BarChart3 size={23} /></span><strong>DataTrace</strong></div>
        <div className="login-heading"><LockKeyhole size={22} /><div><h1>登录分析工作台</h1><p>数据、分析结果和导出文件仅对授权用户开放。</p></div></div>
        <label className="field"><span>用户名</span><input autoComplete="username" autoFocus required value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label className="field"><span>密码</span><input autoComplete="current-password" required type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {error ? <p className="login-error" role="alert">{toApiError(error).message}</p> : null}
        <Button disabled={loading || !username.trim() || !password} type="submit" variant="primary">{loading ? "正在登录" : "登录"}</Button>
      </form>
    </main>
  );
}
