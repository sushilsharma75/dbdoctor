import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'dbdoctor — PostgreSQL & MySQL performance audits',
  description:
    'Evidence-backed database performance audits. You run a read-only script; we never get credentials.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="sticky top-0 z-30 border-b border-ink-600/40 bg-ink-950/70 backdrop-blur-md">
          <nav className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 md:px-8">
            <Link href="/" className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-sm border border-flag-warning/40 bg-flag-warning/10 font-mono text-[11px] font-medium text-flag-warning">
                db
              </span>
              <span className="font-mono text-xs uppercase tracking-wider text-bone-200">
                dbdoctor
              </span>
            </Link>
            <div className="flex items-center gap-x-6 font-mono text-[11px] uppercase tracking-wider">
              <Link href="/new-audit" className="text-bone-400 hover:text-bone-200">
                New audit
              </Link>
              <Link href="/dashboard" className="text-bone-400 hover:text-bone-200">
                Dashboard
              </Link>
              <Link href="/login" className="btn btn-secondary !py-1.5">
                Sign in
              </Link>
            </div>
          </nav>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-10 md:px-8">{children}</main>
        <footer className="mx-auto max-w-6xl border-t border-ink-600/40 px-4 py-8 md:px-8">
          <p className="label">
            dbdoctor · your credentials never leave your machine · reports reviewed by a human
            before delivery
          </p>
        </footer>
      </body>
    </html>
  );
}
