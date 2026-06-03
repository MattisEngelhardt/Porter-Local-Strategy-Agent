# SearXNG Local CA Mount

Place local proxy/VPN/antivirus root CA certificates here as `.crt` files.
Docker Compose mounts this directory into `/usr/local/share/ca-certificates`
inside the SearXNG container, where the image entrypoint merges them into
`/etc/ssl/certs/ca-certificates.crt`.

Do not commit machine-specific root CA files.
