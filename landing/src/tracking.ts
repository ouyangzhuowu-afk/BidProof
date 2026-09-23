/** Optional local event hook: no network requests, identifiers, notes, or document text. */
export const PLACEMENTS = ['header', 'mobile_menu', 'hero', 'preview', 'workflow', 'pricing_personal', 'pricing_team', 'pricing_enterprise', 'final', 'footer', 'demo'] as const;
export const ACTIONS = ['workspace', 'demo', 'select', 'confirm', 'reject', 'note', 'reset'] as const;
export type Placement = typeof PLACEMENTS[number];
export type MarketingAction = typeof ACTIONS[number];
export function emitMarketing(document: Document, placement: Placement, action: MarketingAction): void {
  const view = document.defaultView;
  if (!view) return;
  view.dispatchEvent(new view.CustomEvent('bidproof:marketing', { detail: Object.freeze({ placement, action }) }));
}
export function mountTracking(document: Document): () => void {
  const handleClick = (event: Event): void => {
    const node = event.target;
    if (!(node instanceof (document.defaultView?.Element ?? Element))) return;
    const value = node.closest<HTMLElement>('[data-track]')?.dataset.track;
    if (!value) return;
    const [placement, action, extra] = value.split(':');
    if (extra !== undefined || !PLACEMENTS.some((item) => item === placement) || !ACTIONS.some((item) => item === action)) return;
    emitMarketing(document, placement as Placement, action as MarketingAction);
  };
  document.addEventListener('click', handleClick);
  return () => document.removeEventListener('click', handleClick);
}
