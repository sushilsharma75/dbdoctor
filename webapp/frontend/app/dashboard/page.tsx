'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api, downloadReport, getToken, isAdmin, type Job } from '@/lib/api';

const STATUS_LABELS: Record<Job['status'], string> = {
  uploaded: 'queued',
  processing: 'analyzing…',
  review: 'expert review in progress',
  approved: 'ready',
  failed: 'failed',
};

const STATUS_STYLES: Record<Job['status'], string> = {
  uploaded: 'bg-ink/10',
  processing: 'bg-amber-100',
  review: 'bg-amber-100',
  approved: 'bg-green-100',
  failed: 'bg-red-100',
};

export default function Dashboard() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState('');
  const admin = isAdmin();

  const refresh = useCallback(async () => {
    try {
      setJobs(await api.listJobs());
      setError('');
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = '/login';
      return;
    }
    refresh();
    const timer = setInterval(refresh, 5000); // poll job status
    return () => clearInterval(timer);
  }, [refresh]);

  async function approve(id: string) {
    await api.approveJob(id);
    refresh();
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl">Your audits</h1>
        <Link href="/new-audit" className="bg-ink px-4 py-2 text-cream hover:bg-rust">
          New audit
        </Link>
      </div>
      {error && <p className="mt-4 text-rust">{error}</p>}
      {jobs && jobs.length === 0 && (
        <p className="mt-8 text-ink/60" data-testid="empty">
          No audits yet — start one and upload your first snapshot.
        </p>
      )}
      <div className="mt-6 space-y-3">
        {jobs?.map((job) => (
          <div
            key={job.id}
            className="flex items-center justify-between border border-ink/15 bg-white px-4 py-3"
            data-testid="job-row"
          >
            <div>
              <span className="font-bold">{job.client_alias}</span>{' '}
              <span className="text-sm text-ink/60">· {job.engine}</span>
              {job.score && <span className="text-sm text-ink/60"> · score {job.score}/100</span>}
              {job.error && <p className="text-sm text-rust">{job.error}</p>}
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`px-3 py-1 text-xs uppercase tracking-wide ${STATUS_STYLES[job.status]}`}
                data-testid="job-status"
              >
                {STATUS_LABELS[job.status]}
              </span>
              {job.status === 'approved' && (
                <>
                  <button onClick={() => downloadReport(job.id, 'pdf')} className="text-sm underline hover:text-rust">
                    PDF
                  </button>
                  <button onClick={() => downloadReport(job.id, 'tasks')} className="text-sm underline hover:text-rust">
                    tasks.md
                  </button>
                </>
              )}
              {admin && job.status === 'review' && (
                <>
                  <a
                    href={api.reportUrl(job.id, 'html')}
                    className="text-sm underline hover:text-rust"
                  >
                    inspect
                  </a>
                  <button
                    onClick={() => approve(job.id)}
                    className="bg-pine px-3 py-1 text-sm text-cream hover:opacity-80"
                    data-testid="approve"
                  >
                    approve
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-8 text-sm text-ink/50">
        Every report is reviewed by a human before it becomes available — usually within one
        business day.
      </p>
    </div>
  );
}
