import { ChangeEvent, useRef, useState } from 'react';
import { Check, ImagePlus, Loader2, X } from 'lucide-react';
import { customFetch } from '@workspace/api-client-react';
import { isLibraryPicture, sectorPictures } from '@/lib/eventImageLibrary';

const MAX_BYTES = 5 * 1024 * 1024;
const TYPES = ['image/jpeg', 'image/png', 'image/webp'];

/**
 * The event's picture: upload your own, or pick one of the 5 ready-made
 * pictures of the chosen sector. Optional — `value` is '' for none.
 */
export function EventPictureField({
  sectorSlug,
  sectorName,
  value,
  onChange,
}: {
  sectorSlug: string;
  sectorName?: string;
  value: string;
  onChange: (url: string) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const library = sectorPictures(sectorSlug);

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // picking the same file again should still trigger an upload
    if (!file) return;
    setError('');
    if (!TYPES.includes(file.type)) {
      setError('Choose a JPG, PNG or WebP picture.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setError('The picture is larger than 5 MB. Choose a smaller one.');
      return;
    }
    setUploading(true);
    try {
      const res = await customFetch<{ url: string }>('/api/organizer/event-images', {
        method: 'POST',
        body: file,
        headers: { 'Content-Type': file.type },
      });
      onChange(res.url);
    } catch (err) {
      setError((err as { message?: string })?.message || 'Could not upload the picture.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="event-picture-field">
      <div>
        <p className="text-xs font-semibold text-muted-foreground">Event Picture</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Optional. Shown on your event page and in listings. Upload your own, or pick a ready-made one.
        </p>
      </div>

      {value && (
        <div className="relative overflow-hidden rounded-2xl border border-foreground/10">
          <img src={value} alt="Selected event picture" className="aspect-video w-full object-cover" />
          <button
            type="button"
            onClick={() => onChange('')}
            className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-full bg-background/90 px-3 py-1 text-xs font-semibold shadow"
            data-testid="button-remove-event-picture"
          >
            <X size={13} /> Remove
          </button>
          <span className="absolute bottom-2 left-2 rounded-full bg-background/90 px-2.5 py-0.5 text-[11px] font-semibold">
            {isLibraryPicture(value) ? 'Ready-made picture' : 'Your picture'}
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input ref={fileInput} type="file" accept={TYPES.join(',')} onChange={upload} className="hidden" data-testid="input-event-picture-file" />
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          disabled={uploading}
          className="inline-flex items-center gap-2 rounded-xl border border-foreground/15 bg-background px-3.5 py-2 text-sm font-semibold hover:border-accent disabled:opacity-60"
          data-testid="button-upload-event-picture"
        >
          {uploading ? <Loader2 size={15} className="animate-spin" /> : <ImagePlus size={15} />}
          {uploading ? 'Uploading…' : 'Upload your picture'}
        </button>
        <span className="text-[11px] text-muted-foreground">JPG, PNG or WebP, up to 5 MB</span>
      </div>
      {error && <p className="text-xs text-red-500" role="alert">{error}</p>}

      <div>
        <p className="text-xs font-semibold text-muted-foreground">
          {sectorSlug ? `Or choose a ready-made picture${sectorName ? ` for ${sectorName}` : ''}` : 'Or choose a ready-made picture (pick a sector above to see pictures for it)'}
        </p>
        <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-5">
          {library.map((src, i) => {
            const selected = value === src;
            return (
              <button
                key={src}
                type="button"
                onClick={() => onChange(selected ? '' : src)}
                aria-pressed={selected}
                aria-label={`Ready-made picture ${i + 1}`}
                className={`relative overflow-hidden rounded-xl border-2 transition ${selected ? 'border-accent' : 'border-transparent hover:border-foreground/30'}`}
                data-testid={`event-picture-option-${i + 1}`}
              >
                <img src={src} alt="" loading="lazy" className="aspect-video w-full object-cover" />
                {selected && (
                  <span className="absolute right-1 top-1 rounded-full bg-accent p-0.5 text-accent-foreground">
                    <Check size={12} />
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
