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
        <header className="border-b border-ink/15">
          <nav className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg tracking-[0.25em] uppercase">
              dbdoctor
            </Link>
            <div className="flex gap-6 text-sm">
              <Link href="/new-audit" className="hover:text-rust">
                New audit
              </Link>
              <Link href="/dashboard" className="hover:text-rust">
                Dashboard
              </Link>
              <Link href="/login" className="hover:text-rust">
                Sign in
              </Link>
            </div>
          </nav>
        </header>
        <main className="mx-auto max-w-4xl px-6 py-10">{children}</main>
        <footer className="mx-auto max-w-4xl border-t border-ink/15 px-6 py-8 text-sm text-ink/60">
          dbdoctor · your credentials never leave your machine · reports reviewed by a human before
          delivery
        </footer>
      </body>
    </html>
  );
}
