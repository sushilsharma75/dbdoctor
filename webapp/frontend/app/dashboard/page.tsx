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

const STATUS_BADGES: Record<Job['status'], string> = {
  uploaded: 'badge-neutral',
  processing: 'badge-info',
  review: 'badge-warning',
  approved: 'badge-ok',
  failed: 'badge-critical',
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

  const stats = {
    total: jobs?.length ?? 0,
    review: jobs?.filter((j) => j.status === 'review').length ?? 0,
    ready: jobs?.filter((j) => j.status === 'approved').length ?? 0,
    avg: (() => {
      const scored = (jobs ?? []).filter((j) => j.score);
      if (!scored.length) return '—';
      return Math.round(
        scored.reduce((acc, j) => acc + Number(j.score), 0) / scored.length,
      ).toString();
    })(),
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="label">audits</p>
          <h1 className="mt-1 text-2xl font-light tracking-tight text-bone-100">Your audits</h1>
        </div>
        <Link href="/new-audit" className="btn btn-primary">
          + New audit
        </Link>
      </div>

      {/* stat row */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {(
          [
            ['total audits', stats.total],
            ['in review', stats.review],
            ['ready', stats.ready],
            ['avg health score', stats.avg],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="panel p-4">
            <p className="label">{label}</p>
            <p className="stat-num mt-1">{value}</p>
          </div>
        ))}
      </div>

      {error && <p className="text-sm text-flag-critical">{error}</p>}

      {jobs && jobs.length === 0 && (
        <div className="panel-inset p-6 text-center">
          <p className="text-sm text-bone-400" data-testid="empty">
            No audits yet — start one and upload your first snapshot.
          </p>
        </div>
      )}

      <div className="space-y-2">
        {jobs?.map((job) => (
          <div
            key={job.id}
            className="panel flex items-center justify-between px-4 py-3"
            data-testid="job-row"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-bone-100">{job.client_alias}</p>
              <p className="mt-0.5 font-mono text-[11px] text-bone-500">
                {job.engine}
                {job.score && <> · score {job.score}/100</>}
              </p>
              {job.error && <p className="mt-1 text-xs text-flag-critical">{job.error}</p>}
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className={`badge ${STATUS_BADGES[job.status]}`} data-testid="job-status">
                {STATUS_LABELS[job.status]}
              </span>
              {job.status === 'approved' && (
                <>
                  <button
                    onClick={() => downloadReport(job.id, 'pdf')}
                    className="font-mono text-[11px] uppercase text-flag-info hover:underline"
                  >
                    pdf
                  </button>
                  <button
                    onClick={() => downloadReport(job.id, 'tasks')}
                    className="font-mono text-[11px] uppercase text-flag-info hover:underline"
                  >
                    tasks.md
                  </button>
                </>
              )}
              {admin && job.status === 'review' && (
                <>
                  <a
                    href={api.reportUrl(job.id, 'html')}
                    className="font-mono text-[11px] uppercase text-flag-info hover:underline"
                  >
                    inspect
                  </a>
                  <button
                    onClick={() => approve(job.id)}
                    className="btn !py-1 border-flag-ok/30 bg-flag-ok/10 text-flag-ok hover:bg-flag-ok/20"
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

      <p className="label">
        Every report is reviewed by a human before it becomes available — usually within one
        business day.
      </p>
    </div>
  );
}
