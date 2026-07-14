'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { clearSession, getToken, isAdmin } from '@/lib/api';

// Auth-aware navigation cluster. Lives in a client component so it can read the
// session from localStorage and reflect signed-in state — the surrounding
// layout is a server component and cannot. Re-reads on every navigation
// (usePathname) so it updates right after login redirects and sign-out.
export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [admin, setAdmin] = useState(false);

  useEffect(() => {
    const authed = getToken() !== null;
    setEmail(authed ? window.localStorage.getItem('dbdoctor_email') : null);
    setAdmin(authed && isAdmin());
  }, [pathname]);

  const authed = email !== null;

  function signOut() {
    clearSession();
    setEmail(null);
    setAdmin(false);
    router.push('/');
  }

  return (
    <div className="flex items-center gap-x-6 font-mono text-[11px] uppercase tracking-wider">
      <a href="/kb/index.html" className="text-bone-400 hover:text-bone-200">
        Docs
      </a>
      <Link href="/new-audit" className="text-bone-400 hover:text-bone-200">
        New audit
      </Link>
      {authed ? (
        <>
          <Link href="/dashboard" className="text-bone-400 hover:text-bone-200" data-testid="nav-dashboard">
            Dashboard
          </Link>
          {admin && (
            <span className="badge badge-warning !text-[10px]" data-testid="nav-admin">
              reviewer
            </span>
          )}
          <span className="hidden truncate text-bone-500 sm:inline" data-testid="nav-email">
            {email}
          </span>
          <button
            onClick={signOut}
            className="btn btn-secondary !py-1.5"
            data-testid="nav-signout"
          >
            Sign out
          </button>
        </>
      ) : (
        <Link href="/login" className="btn btn-secondary !py-1.5" data-testid="nav-signin">
          Sign in
        </Link>
      )}
    </div>
  );
}
