// Claim links carry the bearer secret in the URL fragment, which browsers never send to
// the server. Nothing here persists or logs the secret.

export interface ClaimRef {
  uri: string;
  secret: string;
}

const CLAIM_RE = /^#?\/?claim\/(rho:id:[a-z0-9]+)\/([0-9a-fA-F]{64})$/;

/** Parse either a full claim URL or a `#/claim/<uri>/<secret>` fragment. */
export function parseClaim(input: string): ClaimRef | null {
  const hash = input.includes("#") ? input.slice(input.indexOf("#")) : input.trim();
  const match = CLAIM_RE.exec(hash);
  if (!match || !match[1] || !match[2]) return null;
  return { uri: match[1], secret: match[2].toLowerCase() };
}

/** Build the fragment for a claim link. The secret stays in the fragment. */
export function claimFragment(uri: string, secret: string): string {
  return `#/claim/${uri}/${secret}`;
}

/** A full link for copying. */
export function claimLink(baseUrl: string, uri: string, secret: string): string {
  return `${baseUrl.replace(/\/$/, "")}/${claimFragment(uri, secret)}`;
}
