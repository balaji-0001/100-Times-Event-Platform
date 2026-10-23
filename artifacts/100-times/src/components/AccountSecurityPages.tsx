import { type FormEvent, useState } from 'react';
import { Link, useLocation } from 'wouter';
import { customFetch } from '@workspace/api-client-react';
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  KeyRound,
  Lock,
  Mail,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';

/* -------------------------------------------------------------------------- */
/* 1. Privacy Policy Page                                                     */
/* -------------------------------------------------------------------------- */

export function PrivacyPolicyPage() {
  return (
    <div className="mx-auto max-w-4xl px-5 py-16 lg:px-10">
      <Link href="/" className="inline-flex items-center gap-2 text-xs font-semibold text-muted-foreground hover:text-accent mb-6">
        <ArrowLeft size={14} /> Back to 100 TIMES
      </Link>
      <span className="font-mono-face text-xs uppercase tracking-widest text-accent">Legal & Transparency</span>
      <h1 className="mt-2 font-display text-4xl font-extrabold tracking-tight">Privacy Policy</h1>
      <p className="mt-2 text-sm text-muted-foreground">Effective Date: October 2026 · Version 2.0</p>

      <div className="mt-10 space-y-8 text-sm leading-7 text-foreground/90">
        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">1. Introduction</h2>
          <p>
            At 100 TIMES, we value your privacy and believe in complete transparency about how your data is collected, processed, and secured.
            This Privacy Policy applies to our website, APIs, AI concierge tools, and event discovery services.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">2. Information We Collect</h2>
          <ul className="list-disc pl-5 space-y-1.5">
            <li><strong>Account & Profile Information:</strong> Name, email address, password hash, country, job title, company name, and bio.</li>
            <li><strong>Event Participation:</strong> Ticket registrations, saved events, reviews, and custom calendar items.</li>
            <li><strong>Organiser Submissions:</strong> Event titles, descriptions, venue details, schedules, speaker bios, and social links.</li>
            <li><strong>Technical & Usage Data:</strong> IP addresses (anonymized for rate limiting), user-agent strings, session cookies, and API request durations.</li>
          </ul>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">3. How We Use Your Information</h2>
          <p>
            We use collected information to provide personalized event discovery, process attendee bookings, verify organiser authenticity via our automated Trust Agent,
            prevent fraudulent listings, and deliver notifications regarding your registered events.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">4. AI Processing & Guardrails</h2>
          <p>
            Our discovery and matchmaking agents process publicly available event details to assist attendees. We enforce centralized backend guardrails
            preventing prompt injection, filtering unsafe URLs, and ensuring that no private attendee information is shared with external model vendors.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">5. Data Retention & Account Deletion</h2>
          <p>
            You have the right to request deletion of your account at any time via your Profile Settings. When you delete your account, your personal profile,
            saved events, notifications, and credentials are permanently purged. Event registration records are anonymized to protect ticketing audit integrity.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">6. Security Hardening</h2>
          <p>
            All passwords are encrypted with bcrypt using salted rounds. Session authentication tokens are stored in HTTP-only, SameSite cookies.
            All communications are secured with TLS encryption, and strict rate limiting protects accounts from brute-force attempts.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">7. Contact Us</h2>
          <p>
            If you have questions about this policy or your data rights, please contact our Data Protection team at{' '}
            <a href="mailto:privacy@100times.in" className="text-accent underline font-semibold">privacy@100times.in</a>.
          </p>
        </section>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 2. Terms of Service Page                                                   */
/* -------------------------------------------------------------------------- */

export function TermsOfServicePage() {
  return (
    <div className="mx-auto max-w-4xl px-5 py-16 lg:px-10">
      <Link href="/" className="inline-flex items-center gap-2 text-xs font-semibold text-muted-foreground hover:text-accent mb-6">
        <ArrowLeft size={14} /> Back to 100 TIMES
      </Link>
      <span className="font-mono-face text-xs uppercase tracking-widest text-accent">Platform Governance</span>
      <h1 className="mt-2 font-display text-4xl font-extrabold tracking-tight">Terms of Service</h1>
      <p className="mt-2 text-sm text-muted-foreground">Effective Date: October 2026 · Version 2.0</p>

      <div className="mt-10 space-y-8 text-sm leading-7 text-foreground/90">
        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">1. Acceptance of Terms</h2>
          <p>
            By accessing or using the 100 TIMES platform, whether as an attendee, organiser, or visitor, you agree to be bound by these Terms of Service.
            If you do not agree to these terms, please do not use our services.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">2. Account Responsibility</h2>
          <p>
            You are responsible for safeguarding your login credentials. You agree to provide true, accurate, and complete registration information.
            Creating fake accounts, impersonating others, or attempting unauthorized access to administrator or organiser tools is strictly prohibited.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">3. Organiser Responsibilities & Verification</h2>
          <p>
            Organisers must ensure that event details (dates, venues, agendas, ticket pricing) are accurate and that all listed events are genuine.
            All submitted events are subject to automated Trust Agent evaluation and administrative review. 100 TIMES reserves the right to reject or
            unpublish any event that fails trust and safety criteria.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">4. Ticket Reservations & Cancellations</h2>
          <p>
            Registration on 100 TIMES creates a confirmed pass between the attendee and the event organiser. In the event of rescheduling or cancellation,
            organisers must provide prompt notice through the platform to all registered participants.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">5. Prohibited Activities</h2>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>Submitting scam, fraudulent, or deceptive event listings.</li>
            <li>Attempting prompt injection, model jailbreaks, or SSRF attacks against our AI and scraping agents.</li>
            <li>Automated scraping or denial-of-service attempts that violate platform rate limits.</li>
            <li>Distributing malicious links or malware through event agendas or profile links.</li>
          </ul>
        </section>

        <section className="space-y-3">
          <h2 className="font-display text-xl font-bold text-foreground">6. Limitation of Liability</h2>
          <p>
            100 TIMES facilitates discovery and ticketing but does not operate physical event venues or host external gatherings.
            To the maximum extent permitted by law, 100 TIMES shall not be liable for any dispute, injury, or damages arising from physical event participation.
          </p>
        </section>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 3. Email Verification Page (/verify-email?token=...)                       */
/* -------------------------------------------------------------------------- */

export function VerifyEmailPage() {
  const [, setLocation] = useLocation();
  const searchParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : new URLSearchParams();
  const token = searchParams.get('token') || '';

  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(token ? '' : 'Missing verification token.');

  const handleVerify = async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      await customFetch('/api/auth/verify-email', {
        method: 'POST',
        body: JSON.stringify({ token }),
      });
      setSuccess(true);
      window.dispatchEvent(new Event('auth-change'));
    } catch (err: any) {
      setError(err?.message || 'Invalid or expired email verification link.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-160px)] items-center justify-center px-5 py-16">
      <div className="w-full max-w-md rounded-2xl border border-foreground/10 bg-card p-8 text-center space-y-6 shadow-xl">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent/15 text-accent">
          {success ? <CheckCircle2 size={32} className="text-emerald-500" /> : <Mail size={28} />}
        </div>

        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">
            {success ? 'Email Verified!' : 'Verify Your Email Address'}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {success
              ? 'Your email address has been confirmed. You now have full access to all 100 TIMES attendee and organizer features.'
              : 'Click the button below to confirm your account email address.'}
          </p>
        </div>

        {error && (
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-xs text-rose-400">
            {error}
          </div>
        )}

        {success ? (
          <button
            onClick={() => setLocation('/dashboard')}
            className="w-full rounded-full bg-primary px-5 py-3 text-sm font-bold text-primary-foreground hover:bg-accent"
          >
            Go to Attendee Dashboard
          </button>
        ) : (
          <button
            onClick={handleVerify}
            disabled={loading || !token}
            className="w-full rounded-full bg-primary px-5 py-3 text-sm font-bold text-primary-foreground hover:bg-accent disabled:opacity-50"
          >
            {loading ? 'Verifying...' : 'Confirm Verification'}
          </button>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 4. Reset Password Page (/reset-password?token=...)                         */
/* -------------------------------------------------------------------------- */

export function ResetPasswordPage() {
  const [, setLocation] = useLocation();
  const searchParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : new URLSearchParams();
  const token = searchParams.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(token ? '' : 'Missing or invalid password reset token.');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) {
      setError('Missing password reset token in link.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      await customFetch('/api/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ token, newPassword: password }),
      });
      setSuccess(true);
    } catch (err: any) {
      setError(err?.message || 'Password reset failed. The link may have expired.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-160px)] items-center justify-center px-5 py-16">
      <div className="w-full max-w-md rounded-2xl border border-foreground/10 bg-card p-8 space-y-6 shadow-xl">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent/15 text-accent">
          {success ? <CheckCircle2 size={32} className="text-emerald-500" /> : <KeyRound size={28} />}
        </div>

        <div className="text-center">
          <h1 className="font-display text-2xl font-bold text-foreground">
            {success ? 'Password Reset Complete' : 'Set a New Password'}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {success
              ? 'Your password has been securely updated. You can now log in with your new credentials.'
              : 'Choose a strong password containing at least 8 characters.'}
          </p>
        </div>

        {error && (
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-xs text-rose-400">
            {error}
          </div>
        )}

        {success ? (
          <button
            onClick={() => setLocation('/login')}
            className="w-full rounded-full bg-primary px-5 py-3 text-sm font-bold text-primary-foreground hover:bg-accent"
          >
            Sign in with New Password
          </button>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-foreground/80 mb-1.5">New Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                className="w-full rounded-xl border border-foreground/15 bg-background px-4 py-2.5 text-sm outline-none focus:border-accent"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-foreground/80 mb-1.5">Confirm New Password</label>
              <input
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your password"
                className="w-full rounded-xl border border-foreground/15 bg-background px-4 py-2.5 text-sm outline-none focus:border-accent"
              />
            </div>
            <button
              type="submit"
              disabled={loading || !token}
              className="w-full rounded-full bg-primary px-5 py-3 text-sm font-bold text-primary-foreground hover:bg-accent disabled:opacity-50"
            >
              {loading ? 'Resetting Password...' : 'Save New Password'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 5. Delete Account Modal                                                    */
/* -------------------------------------------------------------------------- */

export function DeleteAccountModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const [, setLocation] = useLocation();
  const [password, setPassword] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleDelete = async (e: FormEvent) => {
    e.preventDefault();
    if (confirmText.trim().toUpperCase() !== 'DELETE') {
      setError('Please type DELETE exactly to confirm.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await customFetch('/api/auth/delete-account', {
        method: 'POST',
        body: JSON.stringify({ confirmation: 'DELETE', password }),
      });
      localStorage.removeItem('100-times-auth-token');
      window.dispatchEvent(new Event('auth-change'));
      onClose();
      setLocation('/');
    } catch (err: any) {
      setError(err?.message || 'Incorrect password or account removal failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-in fade-in">
      <div className="w-full max-w-md rounded-2xl border border-rose-500/20 bg-card p-6 shadow-2xl space-y-5">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-500/10 text-rose-500">
              <Trash2 size={20} />
            </div>
            <div>
              <h2 className="font-display text-lg font-bold text-foreground">Delete Account</h2>
              <p className="text-xs text-muted-foreground">Permanent and irreversible</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-full p-1.5 hover:bg-muted text-muted-foreground">
            <X size={16} />
          </button>
        </div>

        <p className="text-xs leading-5 text-muted-foreground">
          This action will permanently delete your personal profile, credentials, saved events, reviews, and notifications.
          Your ticket registration records will be anonymized to maintain event capacity integrity.
        </p>

        {error && (
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-xs text-rose-400">
            {error}
          </div>
        )}

        <form onSubmit={handleDelete} className="space-y-4 text-xs">
          <div>
            <label className="block font-semibold text-foreground/80 mb-1">
              Confirm by typing <strong className="text-rose-500">DELETE</strong>:
            </label>
            <input
              type="text"
              required
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="DELETE"
              className="w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 outline-none focus:border-rose-500"
            />
          </div>

          <div>
            <label className="block font-semibold text-foreground/80 mb-1">Your Password:</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter current password"
              className="w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 outline-none focus:border-rose-500"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-foreground/15 px-4 py-2 font-semibold hover:bg-muted"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || confirmText.trim().toUpperCase() !== 'DELETE' || !password}
              className="rounded-full bg-rose-600 px-5 py-2 font-bold text-white hover:bg-rose-700 disabled:opacity-50"
            >
              {loading ? 'Deleting...' : 'Delete My Account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 6. Email Verification Banner                                               */
/* -------------------------------------------------------------------------- */

export function EmailVerificationBanner({ userEmail }: { userEmail?: string }) {
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleResend = async () => {
    setLoading(true);
    try {
      await customFetch('/api/auth/send-verification-email', { method: 'POST' });
      setSent(true);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-300">
      <div className="flex items-center gap-3">
        <AlertTriangle size={18} className="text-amber-400 shrink-0" />
        <span>
          Your email address ({userEmail}) is unverified. Please check your inbox or request a new verification link.
        </span>
      </div>
      <button
        onClick={handleResend}
        disabled={loading || sent}
        className="rounded-full border border-amber-500/40 bg-amber-500/20 px-3.5 py-1.5 font-semibold text-amber-200 hover:bg-amber-500/30 disabled:opacity-50 shrink-0 self-start sm:self-auto"
      >
        {sent ? 'Verification Link Sent!' : loading ? 'Sending...' : 'Resend Verification Email'}
      </button>
    </div>
  );
}

