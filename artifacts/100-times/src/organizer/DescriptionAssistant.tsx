import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { customFetch } from '@workspace/api-client-react';
import { Check, Loader2, Send, Sparkles, Wand2 } from 'lucide-react';

// Description assistant on the create-event form. It drafts from the details the
// organiser has already filled in, and/or from what they type. The backend only
// lets the AI use those facts; nothing is put into the form until the organiser
// presses "Use this description".

export interface DescriptionFields {
  title?: string;
  eventType?: string;
  sector?: string;
  format?: string;
  startDate?: string;
  endDate?: string;
  startTime?: string;
  city?: string;
  country?: string;
  venue?: string;
  organizerName?: string;
  organizationName?: string;
  price?: string;
  targetAudience?: string;
}

interface DraftResponse {
  description: string;
  source: 'ai' | 'template';
}

type Turn = { role: 'user'; text: string } | { role: 'assistant'; text: string; source: DraftResponse['source'] };

function errText(error: unknown): string {
  const e = error as { data?: { detail?: unknown }; message?: string };
  if (e?.data && typeof e.data.detail === 'string') return e.data.detail;
  return (e?.message || 'Could not get a draft.').replace(/^HTTP\s+\d+\s+[^:]+:\s*/i, '');
}

export function DescriptionAssistant({
  fields,
  currentDescription,
  onUse,
}: {
  fields: DescriptionFields;
  currentDescription: string;
  onUse: (text: string) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [prompt, setPrompt] = useState('');
  const [usedIndex, setUsedIndex] = useState<number | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  const draft = useMutation({
    mutationFn: (message: string | null) =>
      customFetch<DraftResponse>('/api/organizer/events/describe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fields,
          prompt: message,
          currentDescription: currentDescription.trim() || null,
          history: turns.slice(-6).map((t) => ({ role: t.role, text: t.text })),
        }),
      }),
    onSuccess: (res) => setTurns((t) => [...t, { role: 'assistant', text: res.description, source: res.source }]),
  });

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns.length, draft.isPending]);

  const ask = (message: string | null) => {
    if (draft.isPending) return;
    if (message) setTurns((t) => [...t, { role: 'user', text: message }]);
    draft.mutate(message);
  };

  // Lives inside the event form, so it can't be a <form> itself: Enter is handled here.
  const send = () => {
    const text = prompt.trim();
    if (!text) return;
    setPrompt('');
    ask(text);
  };

  const hasTitle = Boolean(fields.title?.trim());

  return (
    <div className="mt-3 rounded-2xl border border-accent/30 bg-accent/5 p-4" data-testid="description-assistant">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-accent text-accent-foreground"><Sparkles size={15} /></span>
          <div>
            <p className="text-sm font-bold text-foreground">Description assistant</p>
            <p className="text-[11px] text-muted-foreground">Uses only your event details and what you tell it. You choose whether to use a draft.</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => ask(null)}
          disabled={!hasTitle || draft.isPending}
          title={hasTitle ? undefined : 'Add the event title first'}
          className="button-press inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-xs font-bold text-primary-foreground hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="button-write-description"
        >
          <Wand2 size={13} /> Write it for me
        </button>
      </div>

      {(turns.length > 0 || draft.isPending) && (
        <div ref={threadRef} className="mt-4 max-h-80 space-y-3 overflow-y-auto pr-1" data-testid="description-thread">
          {turns.map((t, i) =>
            t.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-xs text-primary-foreground">{t.text}</p>
              </div>
            ) : (
              <div key={i} className="rounded-2xl rounded-bl-sm border border-foreground/10 bg-background p-3.5">
                {t.source === 'template' && (
                  <p className="mb-2 text-[11px] font-semibold text-amber-700 dark:text-amber-400">
                    Basic description built from your details (AI writing isn't set up on this server).
                  </p>
                )}
                <p className="whitespace-pre-line text-sm leading-6 text-foreground" data-testid="text-description-draft">{t.text}</p>
                <div className="mt-2.5 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => { onUse(t.text); setUsedIndex(i); }}
                    className="inline-flex items-center gap-1 rounded-full border border-accent/40 px-3 py-1 text-[11px] font-bold text-accent hover:bg-accent hover:text-accent-foreground"
                    data-testid="button-use-description"
                  >
                    {usedIndex === i ? <><Check size={12} /> Added to the form</> : 'Use this description'}
                  </button>
                  <span className="text-[11px] text-muted-foreground">{t.text.trim().split(/\s+/).length} words</span>
                </div>
              </div>
            ),
          )}
          {draft.isPending && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 size={13} className="animate-spin" /> Writing…</p>
          )}
        </div>
      )}

      {draft.isError && <p className="mt-3 text-xs text-destructive" data-testid="text-description-error">{errText(draft.error)}</p>}

      <div className="mt-3 flex gap-2">
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); send(); } }}
          maxLength={1000}
          placeholder={turns.length ? 'Ask for changes, e.g. "shorter", "more formal", "mention the networking dinner"' : 'Or describe your event in your own words, e.g. "2-day AI summit for CIOs with hands-on labs"'}
          className="min-w-0 flex-1 rounded-full border border-foreground/15 bg-background px-4 py-2 text-xs outline-none focus:border-accent"
          data-testid="input-description-prompt"
        />
        <button
          type="button"
          onClick={send}
          disabled={!prompt.trim() || draft.isPending}
          className="button-press grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground disabled:opacity-50"
          aria-label="Send to description assistant"
          data-testid="button-send-description-prompt"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
