'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { downloadReport, fetchReportObjectUrl, fetchReportText, getToken } from '@/lib/api';

// In-app report viewer. The report endpoint is bearer-protected and serves the
// bundle as an attachment, so we fetch it here with the token and render it
// inline: the self-contained HTML via srcDoc, or the PDF via an object URL.
export default function ReportViewer() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [view, setView] = useState<'html' | 'pdf'>('html');
  const [html, setHtml] = useState<string | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const pdfUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = '/login';
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    (async () => {
      try {
        if (view === 'html') {
          const body = await fetchReportText(id, 'html');
          if (!cancelled) setHtml(body);
        } else {
          const url = await fetchReportObjectUrl(id, 'pdf');
          if (cancelled) {
            URL.revokeObjectURL(url);
            return;
          }
          if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current);
          pdfUrlRef.current = url;
          setPdfUrl(url);
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, view]);

  // Revoke the object URL only on unmount — swapping views handles its own.
  useEffect(() => {
    return () => {
      if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current);
    };
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard"
            className="font-mono text-[11px] uppercase text-bone-400 hover:text-bone-200"
          >
            ← back
          </Link>
          <p className="label">audit report</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex overflow-hidden rounded-sm border border-ink-600/40">
            {(['html', 'pdf'] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1 font-mono text-[11px] uppercase ${
                  view === v ? 'bg-flag-info/15 text-flag-info' : 'text-bone-500 hover:text-bone-300'
                }`}
                data-testid={`view-${v}`}
              >
                {v}
              </button>
            ))}
          </div>
          <button
            onClick={() => downloadReport(id, view)}
            className="btn btn-secondary !py-1"
            data-testid="download"
          >
            Download {view}
          </button>
          <button
            onClick={() => downloadReport(id, 'tasks')}
            className="font-mono text-[11px] uppercase text-flag-info hover:underline"
          >
            tasks.md
          </button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-flag-critical" data-testid="report-error">
          {error}
        </p>
      )}
      {loading && <p className="text-sm text-bone-500">Loading report…</p>}

      {!error && view === 'html' && html !== null && (
        <iframe
          title="Audit report"
          srcDoc={html}
          // sandbox="" gives the frame an opaque origin with scripts disabled, so
          // even if the report ever carried injected markup it cannot run JS or
          // reach this app's origin/localStorage (where the JWT lives). The report
          // is static HTML + inline CSS, so nothing is lost. Do NOT add
          // allow-scripts here.
          sandbox=""
          className="h-[80vh] w-full rounded-sm border border-ink-600/40 bg-white"
          data-testid="report-frame"
        />
      )}
      {!error && view === 'pdf' && pdfUrl && (
        <iframe
          title="Audit report (PDF)"
          src={pdfUrl}
          // allow-same-origin (WITHOUT allow-scripts) is required so the origin-
          // scoped blob: URL can load; scripts stay disabled so a malicious PDF
          // cannot execute against this app.
          sandbox="allow-same-origin"
          className="h-[80vh] w-full rounded-sm border border-ink-600/40 bg-white"
          data-testid="report-frame-pdf"
        />
      )}
    </div>
  );
}
