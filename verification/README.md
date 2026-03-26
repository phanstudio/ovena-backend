# Dojah Verification — Django Integration

A plug-and-play Django app that wraps every Dojah API endpoint you need for driver and business verification.

---

## Setup

### 1. Install dependencies

```bash
pip install django djangorestframework requests
```

### 2. Add credentials to `settings.py`

```python
DOJAH_APP_ID    = "your_app_id_here"
DOJAH_SECRET_KEY = "your_secret_key_here"
```

Get these from your [Dojah dashboard](https://app.dojah.io).

### 3. Register the app

```python
# settings.py
INSTALLED_APPS = [
    ...
    "rest_framework",
    "dojah_verification",
]
```

### 4. Wire up URLs

```python
# project/urls.py
from django.urls import path, include

urlpatterns = [
    ...
    path("api/verify/", include("dojah_verification.urls")),
]
```

---

## Endpoints

### Driver Verifications

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/api/verify/driver/nin/` | Lookup NIN |
| POST | `/api/verify/driver/bvn/` | Lookup BVN (full data) |
| POST | `/api/verify/driver/bvn/validate/` | Validate BVN against name/DOB |
| POST | `/api/verify/driver/account/` | Verify bank account number |
| POST | `/api/verify/driver/face-match/` | Match face photo to BVN/NIN |
| POST | `/api/verify/driver/plate/` | Verify vehicle plate number |

### Business Verifications

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/api/verify/business/tin/` | Verify FIRS TIN |
| POST | `/api/verify/business/rc/` | Verify CAC RC Number |
| POST | `/api/verify/business/bvn/` | Verify director/owner BVN |

---

## Example Requests

### NIN Lookup
```json
POST /api/verify/driver/nin/
{
  "nin": "70123456789"
}
```

### BVN Lookup
```json
POST /api/verify/driver/bvn/
{
  "bvn": "22222222222"
}
```

### BVN Validation (match name + DOB)
```json
POST /api/verify/driver/bvn/validate/
{
  "bvn": "22222222222",
  "first_name": "Adeola",
  "last_name": "Semiu",
  "dob": "1993-06-10"
}
```

### Account Number
```json
POST /api/verify/driver/account/
{
  "account_number": "3046507407",
  "bank_code": "011"
}
```

### Face Match
```json
POST /api/verify/driver/face-match/
{
  "image": "<base64-encoded-jpeg>",
  "first_name": "Adeola",
  "last_name": "Semiu",
  "bvn": "22222222222"
}
```

### Plate Number
```json
POST /api/verify/driver/plate/
{
  "plate_number": "ABC123XY"
}
```

### TIN
```json
POST /api/verify/business/tin/
{
  "tin": "18609323-0001"
}
```

### RC Number (CAC)
```json
POST /api/verify/business/rc/
{
  "rc_number": "1261103"
}
```

### Business BVN (director)
```json
POST /api/verify/business/bvn/
{
  "bvn": "22222222222"
}
```

---

## Response Format

All endpoints return a consistent envelope:

```json
// Success
{
  "success": true,
  "data": { ...dojah_response }
}

// Error
{
  "success": false,
  "error": { ...dojah_error_or_message }
}
```

---

## Sandbox Testing

Use these test values from Dojah's sandbox:

| Field | Value |
|-------|-------|
| BVN | `22222222222` |
| NIN | `70123456789` |
| Account Number | `3046507407` (bank code: `011`) |
| Driver's License | `FKJ494A2133` |
| RC Number | `1261103` |
| TIN | `18609323-0001` |

Switch between sandbox and live by using your sandbox vs live API keys from the dashboard.
