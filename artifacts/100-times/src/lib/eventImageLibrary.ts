/**
 * Ready-made event pictures, 5 per sector, for organisers who have no picture
 * of their own. Files live in public/event-images/<sector slug>/<1-5>.jpg —
 * free-licence Unsplash photos (Unsplash License: commercial use allowed, no
 * attribution required); public/event-images/SOURCES.json lists each original.
 */

const SECTOR_SLUGS = [
  'construction',
  'energy-and-power-generation',
  'finance',
  'healthcare',
  'manufacturing',
  'mining',
  'oil-and-gas',
  'other',
  'packaging',
  'pharmaceuticals',
  'technology',
  'telecommunications',
  'textiles',
  'transport-and-logistics',
] as const;

const PICTURES_PER_SECTOR = 5;

/** The 5 pictures for a sector (by category slug); a sector without its own set gets the general ones. */
export function sectorPictures(sectorSlug: string | null | undefined): string[] {
  const slug = (SECTOR_SLUGS as readonly string[]).includes(sectorSlug ?? '') ? (sectorSlug as string) : 'other';
  return Array.from({ length: PICTURES_PER_SECTOR }, (_, i) => `/event-images/${slug}/${i + 1}.jpg`);
}

export function isLibraryPicture(url: string | null | undefined): boolean {
  return !!url && url.startsWith('/event-images/');
}
