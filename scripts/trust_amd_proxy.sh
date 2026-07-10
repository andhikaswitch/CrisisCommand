#!/usr/bin/env bash
# Trust the AMD Developer Cloud TLS proxy — safely.
#
# The ROCm notebook intercepts TLS to GitHub/Docker/HuggingFace with a
# self-signed certificate, so git/pip/curl fail with:
#   server certificate verification failed. CAfile: none
#
# The naive fix ("grab whatever cert github.com presents and install it as a
# system root CA") is a trust-on-first-use anti-pattern: on a hostile network
# it permanently trusts an attacker's CA for EVERY site. This script instead:
#
#   1. refuses to run unless the presented cert really is the AMD proxy
#      (self-signed AND its CN names the proxy) — a genuine public CA or an
#      unknown MITM makes it abort;
#   2. shows you the fingerprint and makes you confirm (skip with --yes);
#   3. scopes the trust to github.com ONLY, via git's per-host config, instead
#      of installing a system-wide root CA. Use --system if you also need
#      pip/curl/apt through the proxy.
#
# Run this ONLY inside the AMD notebook. Never on your laptop.
#
#   bash scripts/trust_amd_proxy.sh            # git-only, asks first
#   bash scripts/trust_amd_proxy.sh --yes      # no prompt
#   bash scripts/trust_amd_proxy.sh --system   # also trust for pip/curl/apt
set -euo pipefail

HOST="${HOST:-github.com}"
CERT="/tmp/amd-proxy-${HOST}.crt"
ASSUME_YES=0
SYSTEM=0
for a in "$@"; do
  case "$a" in
    --yes|-y) ASSUME_YES=1 ;;
    --system) SYSTEM=1 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

echo "==> fetching the certificate presented for ${HOST}:443"
openssl s_client -connect "${HOST}:443" -servername "$HOST" -showcerts </dev/null 2>/dev/null \
  | openssl x509 -outform PEM > "$CERT"
[ -s "$CERT" ] || { echo "no certificate returned; is the network up?" >&2; exit 1; }

subject=$(openssl x509 -in "$CERT" -noout -subject | sed 's/^subject=//')
issuer=$(openssl x509 -in "$CERT" -noout -issuer | sed 's/^issuer=//')
fp=$(openssl x509 -in "$CERT" -noout -fingerprint -sha256 | sed 's/^.*=//')

echo "    subject     : $subject"
echo "    issuer      : $issuer"
echo "    sha256      : $fp"

# Guard 1: a real GitHub cert is issued by a public CA, not by itself. If this
# is not self-signed, there is no proxy and nothing to trust — bail out.
if [ "$subject" != "$issuer" ]; then
  cat >&2 <<EOF

REFUSING: this certificate is NOT self-signed, so it is not the AMD proxy.
Either you are on a normal network (no fix needed — just run your git command),
or something else is intercepting TLS. Do not trust it.
EOF
  exit 1
fi

# Guard 2: the AMD proxy names itself. An unknown self-signed CA is a red flag.
if ! printf '%s' "$subject" | grep -qi "proxy certificate"; then
  cat >&2 <<EOF

REFUSING: self-signed, but the subject does not look like the AMD proxy
("Proxy Certificate for GitHub/Docker/HuggingFace"). This could be a
man-in-the-middle. Inspect it yourself before trusting anything.
EOF
  exit 1
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  echo
  read -r -p "Trust this certificate for ${HOST}? [y/N] " reply
  case "$reply" in [yY]*) ;; *) echo "aborted."; exit 1 ;; esac
fi

if [ "$SYSTEM" -eq 1 ]; then
  # Needed when pip/curl/apt must also traverse the proxy. Wider blast radius:
  # every TLS client on this container now trusts this CA. Ephemeral container
  # only — that is why this is opt-in, not the default.
  cp "$CERT" /usr/local/share/ca-certificates/amd-proxy.crt
  update-ca-certificates
  echo "==> installed system-wide (pip/curl/apt now work through the proxy)"
else
  # Least privilege: git trusts this CA for this host and nothing else.
  git config --global "http.https://${HOST}/.sslCAInfo" "$CERT"
  echo "==> scoped to git + https://${HOST}/ only"
  echo "    (rerun with --system if pip or curl also need the proxy)"
fi

echo "==> verifying"
git ls-remote "https://${HOST}/andhikaswitch/CrisisCommand.git" >/dev/null \
  && echo "CA OK — clone/pull will work" \
  || { echo "still failing; inspect $CERT" >&2; exit 1; }

cat <<'EOF'

REMINDER: the proxy can read the traffic it terminates. Never `git push` from
this notebook — that sends your GitHub token through it. Copy artifacts out
and commit them from your own machine.
EOF
