/**
 * Pure predicate for the BI admin login submit button's `disabled` state.
 *
 * Kept as its own module (no React imports) so it can be unit-tested with
 * `node --test` against Node 24's native TS type stripping, without pulling
 * `.tsx` files through the loader.
 *
 * Empty / whitespace-only credentials must keep the button disabled so the
 * user cannot trigger an empty submit. The submit handler in
 * RequireBiAdmin still keeps a defensive `if (!trimmedUsername || !trimmedPassword)`
 * guard for cases where the user agent autocomplete injects values outside
 * React's state.
 */
export type AdminLoginSubmitState = {
  submitting: boolean;
  username: string;
  password: string;
};

export function isAdminLoginSubmitDisabled(state: AdminLoginSubmitState): boolean {
  if (state.submitting) {
    return true;
  }
  if (!state.username.trim()) {
    return true;
  }
  if (!state.password.trim()) {
    return true;
  }
  return false;
}
