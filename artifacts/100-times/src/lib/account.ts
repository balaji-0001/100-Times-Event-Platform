import { useEffect, useState } from 'react';
import { useMe, type Me } from '@/ops/api';

// Attendee and organiser accounts are separate (decided at sign-up). The server
// enforces it on every endpoint; this module makes the interface match it.

export type AccountType = 'attendee' | 'organiser' | 'admin';

const TOKEN_KEY = '100-times-auth-token';

export function accountTypeOf(me: Pick<Me, 'role' | 'accountType'> | null | undefined): AccountType | null {
  if (!me) return null;
  if (me.accountType) return me.accountType;
  return me.role === 'ADMIN' ? 'admin' : me.role === 'ORGANIZER' ? 'organiser' : 'attendee';
}

/** Where each account lands after signing in. */
export function homePathFor(type: AccountType | null): string {
  if (type === 'admin') return '/admin';
  if (type === 'organiser') return '/organizer';
  return '/dashboard';
}

/** Whether an account may open a path; public pages are open to everyone. */
export function canOpenPath(type: AccountType | null, path: string): boolean {
  const p = path.split(/[?#]/)[0];
  const under = (prefix: string) => p === prefix || p.startsWith(`${prefix}/`);
  if (under('/admin')) return type === 'admin';
  if (under('/organizer')) return type === 'organiser' || type === 'admin';
  if (under('/dashboard') || /^\/events\/[^/]+\/register$/.test(p)) return type === 'attendee' || type === 'admin';
  return true;
}

function readToken(): boolean {
  try {
    return typeof window !== 'undefined' && Boolean(localStorage.getItem(TOKEN_KEY));
  } catch {
    return false;
  }
}

/** The signed-in account, kept in sync with sign-in/sign-out in any tab. */
export function useAccount() {
  const [hasToken, setHasToken] = useState(readToken);
  useEffect(() => {
    const sync = () => setHasToken(readToken());
    window.addEventListener('auth-change', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('auth-change', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);
  const me = useMe(hasToken);
  const signedIn = hasToken && Boolean(me.data) && !me.isError;
  return {
    hasToken,
    me,
    signedIn,
    type: signedIn ? accountTypeOf(me.data) : null,
    resolving: hasToken && me.isLoading,
  };
}
