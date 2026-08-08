#!/usr/bin/env python
"""One-off Etsy OAuth 2.0 (PKCE) helper — ENG-02.

Run once to turn your app's keystring into a long-lived refresh token:

    uv run python scripts/etsy_oauth.py

Etsy requires the redirect URI to be HTTPS, so rather than run a local TLS
server for a single use, this pastes the redirected URL back by hand. The
browser will show an error page at the redirect — that is expected and fine;
the authorization code is in the address bar.

Nothing here is committed: the script prints the tokens and you paste them into
.env yourself.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

AUTH_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

# Scopes cannot be changed without re-authorising, so transactions_r is included
# now even though Analytics is M7 — it saves doing this dance twice.
SCOPES = ["listings_r", "listings_w", "listings_d", "shops_r", "transactions_r"]


def pkce_pair() -> tuple[str, str]:
    """RFC 7636: verifier is 43-128 unreserved chars, challenge is its S256 hash."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def post_form(url: str, fields: dict[str, str]) -> dict[str, object]:
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"\nEtsy rejected the request ({exc.code}):\n{exc.read().decode()}")


def main() -> None:
    print("Etsy OAuth setup\n" + "=" * 60)
    keystring = input("App keystring (Developer Portal > Your Apps): ").strip()
    redirect_uri = input("Redirect URI registered on the app: ").strip()
    if not keystring or not redirect_uri:
        sys.exit("both values are required")

    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": keystring,
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )

    print("\n1. Open this URL, sign in, and approve:\n")
    print(f"   {AUTH_URL}?{query}\n")
    print("2. The browser will land on your redirect URI and probably show an")
    print("   error page. That is expected — copy the full URL from the address bar.\n")

    redirected = input("Paste the full redirected URL: ").strip()
    params = urllib.parse.parse_qs(urllib.parse.urlparse(redirected).query)
    if "code" not in params:
        sys.exit(f"no ?code= in that URL. Etsy said: {params.get('error', ['nothing'])[0]}")
    if params.get("state", [""])[0] != state:
        sys.exit("state mismatch — abort. This is the CSRF check; do not skip it.")

    tokens = post_form(
        TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "client_id": keystring,
            "redirect_uri": redirect_uri,
            "code": params["code"][0],
            "code_verifier": verifier,
        },
    )

    access_token = str(tokens["access_token"])
    print("\n" + "=" * 60)
    print("Success. Add these to backend/.env (never commit them):\n")
    print(f"KAIROS_ETSY_KEYSTRING={keystring}")
    print(f"KAIROS_ETSY_REFRESH_TOKEN={tokens['refresh_token']}")
    # The access token is prefixed with the numeric user id.
    print(f"KAIROS_ETSY_USER_ID={access_token.split('.')[0]}")
    print("\nThe access token expires in an hour and the app refreshes it itself.")
    print("The refresh token lasts 90 days — if the pipeline sits idle longer")
    print("than that, re-run this script.")


if __name__ == "__main__":
    main()
