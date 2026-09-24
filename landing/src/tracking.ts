/** Optional same-page event hook. No network, document text, user identity, or storage. */
export const PLACEMENTS = ['header', 'hero', 'demo'] as const;
export const ACTIONS = ['workspace', 'play', 'complete'] as const;
export type Placement = typeof PLACEMENTS[number];
export type MarketingAction = typeof ACTIONS[number];
export function emitMarketing(document: Document, placement: Placement, action: MarketingAction): void {
  const view = document.defaultView;
  if (!view) return;
  view.dispatchEvent(new view.CustomEvent('bidproof:marketing', { detail: Object.freeze({ placement, action }) }));
}
export function mountTracking(document: Document): () => void {
  const view = document.defaultView;
  if (!view) return () => {};
  const handleClick = (event: Event): void => {
    if (!(event.target instanceof view.Element)) return;
    const value = event.target.closest<HTMLElement>('[data-track]')?.dataset.track;
    if (!value) return;
    const [placement, action, extra] = value.split(':');
    if (extra !== undefined || !PLACEMENTS.some((item) => item === placement) || !ACTIONS.some((item) => item === action)) return;
    emitMarketing(document, placement as Placement, action as MarketingAction);
  };
  document.addEventListener('click', handleClick);
  return () => document.removeEventListener('click', handleClick);
}
