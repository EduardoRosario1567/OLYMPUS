#!/usr/bin/env bash
set -euo pipefail
: "${1:?Usage: smoke_two_containers.sh <CI-image>}"
IMAGE="$1"
A="olympus-p3-a-$$"
B="olympus-p3-b-$$"
cleanup() {
  docker rm -f "$A" "$B" >/dev/null 2>&1 || true
}
trap cleanup EXIT

for id in "$A" "$B"; do
  docker run -d --name "$id" --pull=never --network=none \
    --read-only --tmpfs /tmp:rw,nosuid,nodev,size=67108864,mode=1777 \
    --cap-drop=ALL --security-opt=no-new-privileges \
    --memory=768m --memory-swap=768m --cpus=1 --pids-limit=128 \
    --user=1000:1000 \
    --env "OLYMPUS_INSTANCE_ID=${id}" \
    "$IMAGE" >/dev/null
done

for id in "$A" "$B"; do
  test "$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$id")" = none
  test "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$id")" = true
  test "$(docker inspect --format '{{.HostConfig.Privileged}}' "$id")" = false
  test "$(docker inspect --format '{{len .Mounts}}' "$id")" = 0
  test -z "$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$id" | grep -E '127\.0\.0\.1|0\.0\.0\.0' || true)"
  healthy=0
  for try in $(seq 1 45); do
    if docker exec "$id" node -e '
(async () => {
  const base = "http://127.0.0.1:3000";
  const home = await fetch(base + "/");
  if (!home.ok) process.exit(21);
  const proof = await fetch(base + "/api/olympus-p3-proof");
  if (!proof.ok || (await proof.json()).instanceId !== process.env.OLYMPUS_INSTANCE_ID) process.exit(22);
  for (const [route, method] of [
    ["/api/sandbox-status", "GET"],
    ["/api/generate-ai-code-stream", "POST"],
    ["/api/create-ai-sandbox-v2", "POST"],
    ["/api/run-command-v2", "POST"],
    ["/api/create-zip", "POST"]
  ]) {
    const denied = await fetch(base + route, {method});
    if (denied.status !== 503 || (await denied.json()).reason !== "OLYMPUS_P3_NO_API_NO_INFERENCE") process.exit(23);
  }
})().catch(() => process.exit(25));' >/dev/null 2>&1; then
      healthy=1
      break
    fi
    sleep 2
  done
  if [ "$healthy" != 1 ]; then
    echo "BLOCKED: instance $id not healthy or route guard failed"
    docker logs --tail=100 "$id" 2>&1 || true
    exit 2
  fi
done
PIDA="$(docker inspect --format '{{.State.Pid}}' "$A")"
PIDB="$(docker inspect --format '{{.State.Pid}}' "$B")"
test "$PIDA" -gt 1 && test "$PIDB" -gt 1 && test "$PIDA" != "$PIDB"
echo "PASS: distinct PIDs and instance identities; original APIs denied; no network, privileged access, or host mounts"
echo "NOT VERIFIED: real sandbox/provider, multiuser auth, paid/free inference, generated Rosales Cafe, browser or export"
