# API contract — device ⇄ backend

Base URL: `BACKEND_BASE_URL` (device config, no trailing slash).
Implemented in [`src/api/iot.py`](../../src/api/iot.py).

## Authentication

Every device request carries:

```
X-Device-Key: <key issued for this device>
```

Keys are configured on the backend as `device_id:key` pairs:

```
IOT_DEVICE_KEYS=GBIN-001:key-one,GBIN-002:key-two
```

The key is bound to a device id, so a leaked key cannot be used to post as a
different bin. Comparison uses `secrets.compare_digest`. Failures return `401`
with an identical message whether the device is unknown or the key is wrong —
distinguishing them would tell an attacker which half they got right.

**The device holds no Vision provider credentials of any kind.** It knows a Wi-Fi
password, a backend URL, its own id and its own key. Nothing else.

---

## `POST /api/v1/iot/captures`

Upload a JPEG captured after a confirmed waste event, receive a classification.

**Request** — `multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `image` | file | yes | JPEG binary. Max 8 MB |
| `device_id` | string | yes | Must match the authenticated device |
| `bin_code` | string | yes | e.g. `BIN-001` |
| `event_type` | string | no | Defaults to `waste_detected` |
| `uptime_s` | int | no | Device uptime in seconds |
| `fill_percent` | float | no | **Omitted entirely** if the ultrasonic reading was invalid — never sent as 0 |

**Response `200`**

```json
{
  "status": "ok",
  "label": "plastic",
  "confidence": 0.91,
  "requires_review": false,
  "message": "Classified",
  "capture_id": "0f3c…",
  "phash": "f8c0e0c0f0e0c080",
  "image_bytes": 48213,
  "faces_blurred": 0,
  "exif_stripped": true
}
```

The device consumes `status`, `label` and `confidence`. The rest is evidence that
the privacy pipeline ran, for operators and tests.

`faces_blurred` is deliberately three-valued: `0` means detection ran and found
none, a positive integer means faces were blurred, and `null` means detection
**could not run** — never conflate the last two.

### Status values

| `status` | Meaning | Device LED |
|---|---|---|
| `ok` | Confident classification | Green, ~3 s |
| `warning` | Below the confidence threshold; flagged for review | Red, 2 fast blinks |
| `hazard` | Hazardous material; flagged for review | Red, blinking ~5 s |
| `refused` | System declines to answer (e.g. no label produced) | Warning pattern — **not** green |
| `error` | Backend or provider failure | Orange, ~2 s |

A device that receives `refused` or `error` must not present a label. The firmware
enforces this in `isConclusive()`; the backend enforces it by never emitting a
label alongside those statuses.

### Errors

| Code | When |
|---|---|
| `401` | Missing/invalid `X-Device-Key`, or `device_id` mismatch |
| `422` | Not a decodable image, unsupported format, too large, too small |

---

## `POST /api/v1/bins/{code}/readings`

Report a fill-level change. Sent **only on transition** between normal and full,
never as a repeating stream (spec §14).

**Request** — `application/json`

```json
{
  "device_id": "GBIN-001",
  "fill_percent": 84.5,
  "is_full": true,
  "uptime_s": 900
}
```

`fill_percent` must be within `0..100`; anything else is `422` at the schema layer
and again in the service, so an out-of-range value cannot reach storage.

**Response `201`**

```json
{
  "reading_id": "9c1a…",
  "bin_code": "BIN-001",
  "device_id": "GBIN-001",
  "fill_percent": 84.5,
  "is_full": true,
  "uptime_s": 900,
  "recorded_at": "2026-08-11T10:30:00Z"
}
```

## `GET /api/v1/bins/{code}/readings?limit=50`

Recent readings, oldest first. Unauthenticated — it is an operator/read view, not
a device endpoint.

---

## Backend processing order

Fixed, and not bypassable from the router (spec §10, §26):

```
upload
  → validate (format, dimensions, size)
  → strip EXIF
  → blur detected faces
  → resize (max edge 1024) + JPEG re-encode
  → perceptual hash
  → ProcessedImage
      → LangGraph classify graph → Vision provider
      → safety / HITL rules
  → response
```

`classify_processed_image()` accepts a `ProcessedImage`, not `bytes`. Handing raw
device data to a model provider is a type error, not a review comment.
