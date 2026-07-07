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
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <p className="label">new audit</p>
        <h1 className="mt-1 text-2xl font-light tracking-tight text-bone-100">New audit</h1>
      </div>

      {/* step 1: engine */}
      <section className="panel p-5">
        <p className="font-mono text-[11px] text-flag-warning">01</p>
        <h2 className="mt-1 text-sm font-medium text-bone-100">Which engine?</h2>
        <div className="mt-3 flex gap-3">
          {(['postgres', 'mysql'] as Engine[]).map((e) => (
            <button
              key={e}
              onClick={() => {
                setEngine(e);
                setStep(2);
              }}
              className={`btn ${engine === e ? 'btn-primary' : 'btn-secondary'}`}
              data-testid={`engine-${e}`}
            >
              {e === 'postgres' ? 'PostgreSQL' : 'MySQL / MariaDB'}
            </button>
          ))}
        </div>
      </section>

      {/* step 2: run the collector */}
      {step >= 2 && engine && (
        <section className="panel p-5" data-testid="step-collector">
          <p className="font-mono text-[11px] text-flag-warning">02</p>
          <h2 className="mt-1 text-sm font-medium text-bone-100">
            Run the collector (read-only, on your machine)
          </h2>
          <p className="mt-2 text-[13px] leading-relaxed text-bone-400">
            <a href={api.collectorUrl(engine)} className="text-flag-info hover:underline">
              Download {engine === 'postgres' ? 'pg_collect.py' : 'mysql_collect.py'}
            </a>{' '}
            — a single Python file you can read before running. It opens a read-only session and
            strips every literal before writing the snapshot. Then run:
          </p>
          <pre className="panel-inset mt-3 overflow-x-auto p-4 font-mono text-[11px] leading-relaxed text-bone-300">
            {RUN_COMMANDS[engine]}
          </pre>
          <p className="mt-2 font-mono text-[11px] text-bone-500">
            requires python 3.10+ ·{' '}
            {engine === 'postgres' ? 'pip install "psycopg[binary]"' : 'pip install pymysql'} · the
            script prints its own sha256
          </p>
          <button onClick={() => setStep(3)} className="btn btn-primary mt-4" data-testid="collector-done">
            I have my snapshot.json
          </button>
        </section>
      )}

      {/* step 3: upload */}
      {step >= 3 && (
        <section className="panel p-5" data-testid="step-upload">
          <p className="font-mono text-[11px] text-flag-warning">03</p>
          <h2 className="mt-1 text-sm font-medium text-bone-100">Upload the snapshot</h2>
          <div className="mt-3 space-y-3">
            <div>
              <label className="label mb-1.5 block">database name (shown on the report)</label>
              <input
                type="text"
                placeholder="e.g. acme production"
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
                className="field"
                data-testid="alias"
              />
            </div>
            <div>
              <label className="label mb-1.5 block">snapshot.json</label>
              <input
                type="file"
                accept=".json,application/json"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="field cursor-pointer"
                data-testid="snapshot-file"
              />
            </div>
          </div>
          {error && (
            <p className="mt-3 text-xs text-flag-critical" data-testid="upload-error">
              {error}
            </p>
          )}
          <button
            onClick={upload}
            disabled={!file || busy}
            className="btn btn-primary mt-4"
            data-testid="upload"
          >
            {busy ? 'Uploading…' : 'Upload & start analysis'}
          </button>
          <p className="mt-3 font-mono text-[11px] text-bone-500">
            you can open snapshot.json in any editor first — everything we receive is in that file
          </p>
        </section>
      )}
    </div>
  );
}
