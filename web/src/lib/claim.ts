// Claim links carry the bearer secret in the URL fragment, which browsers never send to
// the server. Nothing here persists or logs the secret.

export interface ClaimRef {
  id: number;
  secret: string;
}

const CLAIM_RE = /^#?\/?claim\/(\d+)\/([0-9a-fA-F]{64})$/;

/** Parse either a full claim URL or a `#/claim/<id>/<secret>` fragment. */
export function parseClaim(input: string): ClaimRef | null {
  const hash = input.includes("#") ? input.slice(input.indexOf("#")) : input.trim();
  const match = CLAIM_RE.exec(hash);
  if (!match || !match[1] || !match[2]) return null;
  const id = Number.parseInt(match[1], 10);
  if (!Number.isSafeInteger(id) || id < 0) return null;
  return { id, secret: match[2].toLowerCase() };
}

/** Build the fragment for a claim link. The secret stays in the fragment. */
export function claimFragment(id: number, secret: string): string {
  return `#/claim/${id}/${secret}`;
}

/** A full link for copying. */
export function claimLink(baseUrl: string, id: number, secret: string): string {
  return `${baseUrl.replace(/\/$/, "")}/${claimFragment(id, secret)}`;
}
