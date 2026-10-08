/* Deterministic gallery presentation rules, independent of the DOM. */
const names = new Intl.Collator(undefined, {numeric: true, sensitivity: 'base'});
export function sortGalleryFiles(files) {
  return [...files].sort((left, right) => names.compare(left.name, right.name));
}
export function initialGallerySlots(limit, count) {
  return Math.max(count, Math.min(limit, limit <= 5 ? limit : 10));
}
export function nextGallerySlots(limit, visible, count) {
  return Math.max(count, Math.min(limit, visible + 1));
}
