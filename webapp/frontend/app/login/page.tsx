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
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl">{mode === 'login' ? 'Sign in' : 'Create your account'}</h1>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <input
          type="email"
          required
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full border border-ink/30 bg-white px-3 py-2"
          data-testid="email"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="password (8+ characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border border-ink/30 bg-white px-3 py-2"
          data-testid="password"
        />
        {error && (
          <p className="text-sm text-rust" data-testid="auth-error">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full bg-ink py-2 text-cream hover:bg-rust disabled:opacity-50"
          data-testid="submit"
        >
          {busy ? '…' : mode === 'login' ? 'Sign in' : 'Sign up'}
        </button>
      </form>
      <button
        onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
        className="mt-4 text-sm text-ink/60 underline hover:text-rust"
        data-testid="toggle-mode"
      >
        {mode === 'login' ? 'New here? Create an account' : 'Already registered? Sign in'}
      </button>
    </div>
  );
}
