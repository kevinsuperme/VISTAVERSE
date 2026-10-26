type PendingQuery = { params: URLSearchParams; replace: boolean };
const pendingQueries = new WeakMap<object, PendingQuery>();

/** React Router does not queue search-param setters like React state setters.
 * Batch controls from one event into one navigation, including data routers.
 */
export function updateAdminQuery(
  location: object,
  search: string,
  update: (params: URLSearchParams) => void,
  navigate: (params: URLSearchParams, options: { replace: boolean }) => void,
  replace = true,
) {
  let pending = pendingQueries.get(location);
  if (!pending) {
    pending = { params: new URLSearchParams(search), replace };
    pendingQueries.set(location, pending);
    const batch = pending;
    queueMicrotask(() => {
      pendingQueries.delete(location);
      navigate(batch.params, { replace: batch.replace });
    });
  }
  // Opening a detail intentionally creates a history entry, even if a filter
  // also changed in this event. Closing detail and changing filters replace it.
  pending.replace = pending.replace && replace;
  update(pending.params);
}
