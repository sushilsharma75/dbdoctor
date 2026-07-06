'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, getToken } from '@/lib/api';

type Engine = 'postgres' | 'mysql';

const RUN_COMMANDS: Record<Engine, string> = {
  postgres:
    'python pg_collect.py --dsn "postgresql://readonly_user:PASS@host:5432/yourdb" --out snapshot.json',
  mysql:
    'python mysql_collect.py --dsn "mysql://readonly_user:PASS@host:3306/yourdb" --out snapshot.json',
};

export default function NewAudit() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [engine, setEngine] = useState<Engine | null>(null);
  const [alias, setAlias] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function upload() {
    if (!file) return;
    if (!getToken()) {
      router.push('/login');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api.uploadSnapshot(file, alias || 'my database');
      router.push('/dashboard');
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl">New audit</h1>

      {/* step 1: engine */}
      <section className="mt-8">
        <h2 className="font-bold">1 · Which engine?</h2>
        <div className="mt-3 flex gap-4">
          {(['postgres', 'mysql'] as Engine[]).map((e) => (
            <button
              key={e}
              onClick={() => {
                setEngine(e);
                setStep(2);
              }}
              className={`border px-6 py-3 ${engine === e ? 'border-rust bg-white text-rust' : 'border-ink/30 bg-white hover:border-rust'}`}
              data-testid={`engine-${e}`}
            >
              {e === 'postgres' ? 'PostgreSQL' : 'MySQL / MariaDB'}
            </button>
          ))}
        </div>
      </section>

      {/* step 2: run the collector */}
      {step >= 2 && engine && (
        <section className="mt-8" data-testid="step-collector">
          <h2 className="font-bold">2 · Run the collector (read-only, on your machine)</h2>
          <p className="mt-2 text-sm text-ink/80">
            <a href={api.collectorUrl(engine)} className="underline hover:text-rust">
              Download {engine === 'postgres' ? 'pg_collect.py' : 'mysql_collect.py'}
            </a>{' '}
            — a single Python file you can read before running. It opens a read-only session and
            strips every literal before writing the snapshot. Then run:
          </p>
          <pre className="mt-3 overflow-x-auto bg-ink p-4 text-xs text-cream">
            {RUN_COMMANDS[engine]}
          </pre>
          <p className="mt-2 text-xs text-ink/60">
            Requires Python 3.10+ and{' '}
            {engine === 'postgres' ? 'pip install "psycopg[binary]"' : 'pip install pymysql'}. The
            script prints its own SHA256 so you can verify it.
          </p>
          <button
            onClick={() => setStep(3)}
            className="mt-4 bg-ink px-5 py-2 text-cream hover:bg-rust"
            data-testid="collector-done"
          >
            I have my snapshot.json
          </button>
        </section>
      )}

      {/* step 3: upload */}
      {step >= 3 && (
        <section className="mt-8" data-testid="step-upload">
          <h2 className="font-bold">3 · Upload the snapshot</h2>
          <input
            type="text"
            placeholder="a name for this database (shown on the report)"
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
            className="mt-3 w-full border border-ink/30 bg-white px-3 py-2"
            data-testid="alias"
          />
          <input
            type="file"
            accept=".json,application/json"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="mt-3 w-full border border-ink/30 bg-white px-3 py-2"
            data-testid="snapshot-file"
          />
          {error && (
            <p className="mt-3 text-sm text-rust" data-testid="upload-error">
              {error}
            </p>
          )}
          <button
            onClick={upload}
            disabled={!file || busy}
            className="mt-4 bg-ink px-5 py-2 text-cream hover:bg-rust disabled:opacity-50"
            data-testid="upload"
          >
            {busy ? 'Uploading…' : 'Upload & start analysis'}
          </button>
          <p className="mt-3 text-xs text-ink/60">
            You can open snapshot.json in any editor first — everything we receive is in that file.
          </p>
        </section>
      )}
    </div>
  );
}
