'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, setSession } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const fn = mode === 'login' ? api.login : api.register;
      setSession(await fn(email, password));
      router.push('/dashboard');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm pt-8">
      <div className="panel p-6">
        <p className="label">{mode === 'login' ? 'authenticate' : 'create account'}</p>
        <h1 className="mt-2 text-xl font-light tracking-tight text-bone-100">
          {mode === 'login' ? 'Sign in' : 'Create your account'}
        </h1>
        <form onSubmit={submit} className="mt-6 space-y-3">
          <div>
            <label className="label mb-1.5 block">email</label>
            <input
              type="email"
              required
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="field"
              data-testid="email"
            />
          </div>
          <div>
            <label className="label mb-1.5 block">password</label>
            <input
              type="password"
              required
              minLength={8}
              placeholder="8+ characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field"
              data-testid="password"
            />
          </div>
          {error && (
            <p className="text-xs text-flag-critical" data-testid="auth-error">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="btn btn-primary w-full"
            data-testid="submit"
          >
            {busy ? '…' : mode === 'login' ? 'Sign in' : 'Sign up'}
          </button>
        </form>
        <button
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          className="mt-4 font-mono text-[11px] text-bone-500 hover:text-bone-300"
          data-testid="toggle-mode"
        >
          {mode === 'login' ? '→ New here? Create an account' : '→ Already registered? Sign in'}
        </button>
      </div>
    </div>
  );
}
