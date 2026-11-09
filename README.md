# 🌱 FertiTracker — National Fertilizer Distribution Traceability System

**University Final Software Engineering Project**  
*Department of Interdisciplinary Studies, Faculty of Technological Studies, University of Vavuniya*  
*Course: TICT3153 — Software Engineering Project (ICT Expo 5.0)*  
*Author: Individual Project*

---

## 📌 Executive Summary & Problem Context

In Sri Lanka, Agrarian Service Centres (ASCs) historically record fertilizer dispatches and farmer quota distributions in handwritten paper registers. This causes major supply chain vulnerabilities:
- **Disconnected Traceability**: Warehouse dispatches, ASC physical stock, and farmer agrarian quotas operate in silos.
- **Quota Abuse & Duplicate Issues**: Paper tokens can be presented multiple times or forged, leading to double-allocation.
- **Stock Leakage & Unreconciled Discrepancies**: Damaged or missing bags in transit are difficult to detect and reconcile without digital custody logs.
- **Expiry Wastage (Lack of FEFO)**: Batches with near expiry dates sit in ASC storage while newer batches are issued, leading to expired stock.
- **Digital Divide Exclusion**: Traditional digital apps assume every farmer possesses a modern smartphone with continuous mobile data, unintentionally excluding elderly, disabled, or low-income farmers with basic keypad feature phones.

**FertiTracker** solves these challenges through an end-to-end tri-lingual (Sinhala, Tamil, English), web-based traceability system featuring:
1. **FEFO Inventory Allocation & Multi-Batch Splitting**: Earliest-expiring unexpired stock is automatically allocated first; issues split across multiple batches when necessary; expired batches are strictly skipped.
2. **Expired Stock Write-Off**: Strict append-only write-off workflow authorized by an ASC Head with a mandatory justification reason and immutable audit log.
3. **End-to-End Batch Traceability**: Complete lifecycle auditing from warehouse production and ASC dispatches to receiving, farmer distribution receipts, and write-offs.
4. **Browser-Based Dynamic QR Scanner**: 60-second single-use opaque tokens with zero app installation (html5-qrcode).
5. **Keypad Phone SMS Verification**: HMAC-SHA256 keyed 6-digit backup codes dispatched via a pluggable SMS gateway.
6. **Officer-Assisted Issue Workflow**: A strict **Two-Officer Rule** requiring ASC Head authorization for farmers without phones.
7. **PostgreSQL Concurrency & Security Hardening**: Row-level locking (`select_for_update()`), officer brute-force lockout, and data minimization (masked NICs).
8. **Role-Based Dashboards**: Tailored interfaces displaying only what each user role needs (ASC Officer, ASC Head, Warehouse Officer, Administrator, Auditor, Farmer).

---

## 🛠️ System Architecture & Technology Stack

| Layer | Technology | Rationale & Sri Lankan Context |
|---|---|---|
| **Backend Framework** | Python 3.12 / Django 6.1 | High-productivity, robust ORM, built-in security, role-based decorators. |
| **Relational Database** | PostgreSQL 16 | ACID-compliant, native support for row-level locking (`SELECT ... FOR UPDATE`). |
| **Frontend UI** | Django Templates, Tailwind CSS (Offline) | Large touch targets, high contrast, runs completely offline at university expo. |
| **Internationalization** | Django i18n (`gettext`, `.po` / `.mo`) | Trilingual support (සිංහල, தமிழ், English) compliant with the Official Languages Commission. |
| **QR Engine** | Local `html5-qrcode` & `qrcode.min.js` | Direct browser camera access (`getUserMedia`) without Google Play/App Store barrier. |
| **SMS Gateway** | Pluggable Backend Architecture | `SimulatedSMSBackend` for demo/expo; swappable to Mobitel m-Space / Dialog IdeaMart. |
| **Export Engine** | CSV with UTF-8 BOM (`\ufeff`) & `@media print` | Displays Sinhala/Tamil glyphs correctly in Excel on Windows; clean browser PDF printing. |

---

## ⚙️ Installation & Windows Setup Guide

### 1. Prerequisites
- Python 3.11+ installed and added to PATH.
- PostgreSQL 14+ installed and running locally on port `5432`.

### 2. Environment Configuration
Clone the repository, create and activate a virtual environment:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root (see `.env.example`):
```env
DEBUG=True
SECRET_KEY=django-insecure-fertitracker-secret-key-2026
DB_NAME=fertitracker_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
DEMO_MODE=True
OTP_SECRET_KEY=fertitracker-hmac-otp-secret-key-5153
SMS_BACKEND=distributions.sms.SimulatedSMSBackend
LOW_STOCK_THRESHOLD_BAGS=10
NEAR_EXPIRY_DAYS=60
```

### 3. Database Migration & Translation Catalog Compilation
```powershell
# Create PostgreSQL database (if not exists)
# psql -U postgres -c "CREATE DATABASE fertitracker_db;"

# Apply database migrations
.venv\Scripts\python manage.py migrate

# Compile Sinhala and Tamil translation catalogs
.venv\Scripts\python compile_po.py
```

### 4. Seeding Demo Data (One-Click Setup)
Initialize the complete demo dataset (warehouses, 5 Northern ASCs, diverse batches, dispatches, 30 farmers, and demo accounts). Note that `DEMO_MODE=True` must be set in your `.env` (or pass `--force`):
```powershell
# Seed demo dataset (Idempotent: safe to run multiple times)
.venv\Scripts\python manage.py seed_demo_data

# Or force execution if DEMO_MODE is False in production
.venv\Scripts\python manage.py seed_demo_data --force

# Optional: To completely purge and re-seed
.venv\Scripts\python manage.py seed_demo_data --reset
```

### 5. Running Automated Unit & Concurrency Tests on PostgreSQL
> [!IMPORTANT]
> **Why PostgreSQL is required for tests**:
> Django's test runner executes against the configured PostgreSQL database (`test_fertitracker_db`). SQLite ignores `select_for_update()` row-level locks, whereas PostgreSQL enforces true database-level lock isolation across multi-threaded transactions.

Execute the full suite of 60 tests:
```powershell
.venv\Scripts\python manage.py test
```
*For detailed breakdown and coverage instructions, see [docs/test_cases.md](file:///c:/Users/anupa/Documents/Code/fertitracker/docs/test_cases.md).*

### 6. Starting the Development Server
```powershell
.venv\Scripts\python manage.py runserver
```
Access the application locally at `http://127.0.0.1:8000/`.

### 7. Cloudflare Tunnel (Live Mobile Testing & Expo Camera Access)
Modern mobile browsers (iOS Safari, Android Chrome) strictly require a secure **HTTPS** context before granting access to camera hardware via `navigator.mediaDevices.getUserMedia()`. For university exhibition (ICT Expo 5.0) or live smartphone QR scanner testing:

1. Download and run Cloudflare Tunnel:
```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```
2. Cloudflare outputs a public HTTPS address (e.g. `https://xxxx-xxxx.trycloudflare.com`).
3. Scan or open this URL on any smartphone or tablet to demonstrate the trilingual interface and real-time QR scanning.

---

## 👥 Demo User Accounts (DEMO ONLY)

> [!NOTE]
> All accounts below are pre-configured strictly for demonstration and evaluation purposes. All demo passwords are `Password123!`.

| Role | Username | Password | ASC / Centre | Permissions & Responsibilities |
|---|---|---|---|---|
| **System Administrator** | `admin` | `Password123!` | System-wide | Master data, users, seasons toggle, full system audit |
| **Warehouse Officer** | `wh_officer` | `Password123!` | Northern Regional Hub | Creates batches, dispatches fertilizer to ASCs |
| **ASC Counter Officer** | `asc_officer` | `Password123!` | Vavuniya South ASC | Scans QR, sends SMS code, issues fertilizer |
| **ASC Head Officer** | `asc_head` | `Password123!` | Vavuniya South ASC | Holds `is_asc_head=True`; approves assisted requests & write-offs |
| **Auditor** | `auditor` | `Password123!` | Ministry / External | Read-only access to audit logs, discrepancy & exception reports |
| **Registered Farmer** | `farmer1` | `Password123!` | Vavuniya South ASC | Generates dynamic QR token, checks quota history |

---

## 🚀 Key Functional Features & Architecture

### 1. Expiry & Stock Alerts (FEFO)
- **First-Expired-First-Out (FEFO)**: When an issue is confirmed, `confirm_issue_distribution` locks unexpired candidate batches (`batch__expiry_date__gte=today`) using `select_for_update()` ordered by `expiry_date`.
- **Multi-Batch Splitting**: If the earliest-expiring batch only has 1 bag (50kg) and the farmer takes 100kg (2 bags), the system deducts 1 bag from the first batch and allocates the remaining 1 bag from the next unexpired batch. An outbound `StockMovement` is created for every allocated batch to maintain full traceability.
- **Skipping Expired Batches**: Batches past their expiry date are flagged `EXPIRED` and cannot be issued under any circumstances.
- **Expired Stock Write-Off**: ASC Heads (`is_asc_head=True`) can write off expired stock with a mandatory justification reason. This creates an append-only `StockMovement(movement_type='WRITE_OFF')` and an `AuditLog` entry (no destructive deletions).
- **Thresholds**: Default low-stock threshold is 10 bags (configurable per ASC via `StockThreshold`), and near-expiry warning window is 60 days.

### 2. Role-Based Dashboards
- **ASC Officer**: Today's issues (kg and farmer count), current stock balances with status badges (`HEALTHY`, `LOW STOCK`, `NEAR EXPIRY`, `EXPIRED`), incoming dispatches waiting to be received, and large touch-target buttons ("Scan QR", "SMS Backup Code", "Officer-Assisted").
- **ASC Head**: All ASC Officer features plus a pending assisted approvals review card and expired stock write-off controls.
- **Warehouse Officer**: Status counters (In Transit, Received, Discrepancies), "+ Create Dispatch" and "+ New Fertilizer Batch" buttons, dispatches table, and warehouse batch list.
- **Administrator**: Master system counters (Users, Farmers, ASCs, Warehouses), one-click Maha/Yala active season status toggle, and quick administrative shortcuts.
- **Auditor**: Discrepancy incidents count, assisted-issue rate (with exception threshold warning), expired stock count, and latest immutable audit log events.
- **Farmer**: Dedicated mobile dashboard for generating 60s dynamic QR codes, checking quota status, and viewing previous receipts.

### 3. Reports, Batch Traceability & Exports
- **Batch Traceability Lifecycle (`/distributions/reports/batch-trace/`)**: Enter or select any fertilizer batch code (e.g. `UREA-2026-B01`) to inspect its complete life journey: creation warehouse & expiry date, dispatches to ASCs, receiving/damaged/missing counts, current on-hand stock across ASCs, distributions to farmers (with masked NICs), and expired stock write-offs.
- **Reports & Multi-Parameter Filter (`/distributions/reports/`)**: Filter distributions, ASC stocks, and dispatches by season, ASC, product, issue method, status, and date range.
- **Discrepancy Report (`/inventory/discrepancies/`)**: Comprehensive log of damaged or missing bags recorded during ASC receiving.
- **Assisted Issues Report (`/distributions/reports/assisted-issues/`)**: Oversight tracking exception-based distributions, reason breakdown, and per-officer ratios.
- **Searchable Audit Logs (`/distributions/audit/logs/`)**: Search and filter append-only logs by user, action, and date range. Strictly read-only (no edit or delete).
- **CSV Export with UTF-8 BOM**: All CSV exports include the UTF-8 Byte Order Mark (`\ufeff`) so that Sinhala and Tamil Unicode text open cleanly in Microsoft Excel on Windows without mojibake.
- **Print / Save as PDF**: Every report features `@media print` CSS and a "Print / Save PDF" button.

---

## 🧪 Production Deployment Check Analysis

Running `python manage.py check --deploy` evaluates the application against production security standards:
- **`mail.E001`**: Currently uses `django.core.mail.backends.console.EmailBackend` for offline expo demonstration. In production, configure an SMTP backend (e.g., SendGrid, Amazon SES, or Gov SMS/Email gateway).
- **`security.W004`, `security.W008` (SSL/HSTS)**: `SECURE_SSL_REDIRECT = True` and `SECURE_HSTS_SECONDS = 31536000` must be enabled when deploying behind an HTTPS reverse proxy (Nginx / Cloudflare).
- **`security.W012`, `security.W016` (Secure Cookies)**: `SESSION_COOKIE_SECURE = True` and `CSRF_COOKIE_SECURE = True` ensure cookies are only transmitted over HTTPS connections.
- **`security.W018` (DEBUG Mode)**: Set `DEBUG=False` in the production `.env` file to prevent stack traces from exposing system internals.

---

## 🎓 University Viva Voce — Technical Defense & Examination Q&A

### PART 1: Expiry & Stock Alerts (FEFO)
1. **Q: Why is FEFO (First-Expired-First-Out) crucial for fertilizer distribution, and how does your implementation handle stock splitting?**  
   *Answer*: Chemical fertilizers like Urea degrade over time, absorb moisture, and cake if stored past expiration. Issuing the newest batch while older batches expire creates government waste. In `confirm_issue_distribution`, we query unexpired stock ordered by `batch__expiry_date` with `select_for_update()`. If the earliest-expiring batch has fewer bags than requested, the algorithm deducts available bags from the first batch and automatically takes the balance from the next earliest batch. Each batch deduction records its own outbound `StockMovement` pointing to that specific batch for 100% traceability.

2. **Q: Why does the system block expired batches from being issued, and how are expired bags disposed of?**  
   *Answer*: Substandard or expired fertilizer damages soil chemistry and crop yield. The verification service checks `batch__expiry_date >= today`. If a batch has expired, it is strictly skipped during issue allocation. To account for expired stock, an ASC Head can perform an **Expired Stock Write-Off**. Crucially, the system does not delete database rows; it records an append-only `StockMovement(movement_type='WRITE_OFF')` and an `AuditLog` entry, decrementing `bags_on_hand` while preserving the full audit trail.

3. **Q: What locking mechanism guarantees that two officers cannot allocate the same batch stock simultaneously?**  
   *Answer*: We use PostgreSQL's `SELECT ... FOR UPDATE` row-level locks on the candidate `ASCStock` rows inside an `@transaction.atomic` block. When Officer 1 initiates an issue, the database engine places an exclusive lock on those specific stock rows. If Officer 2 attempts an issue from the same stock at the exact same millisecond, Officer 2's transaction blocks until Officer 1 commits. Officer 2 then reads the updated `bags_on_hand`, preventing stock overselling.

### PART 2: Role-Based Dashboards & Usability
1. **Q: How does the role-based dashboard design satisfy the usability requirements for non-technical ASC officers?**  
   *Answer*: ASC officers often have limited computer experience. Rather than overwhelming them with system-wide analytics, the ASC Officer dashboard displays only 4 primary elements: a large touch-target "Scan QR" button (min 48px height), today's issue counter, a stock balance table with color-coded health badges, and an incoming dispatches alert. Dashboards for other roles (Warehouse Officer, Auditor, Admin) render entirely different contexts tailored exclusively to their duties.

2. **Q: How does the ASC Head dashboard enforce the Two-Officer Rule?**  
   *Answer*: The ASC Head dashboard features a dedicated "Pending Approvals" section. When a counter officer creates an assisted request for a farmer without a phone, the request appears on the ASC Head's screen. The head reviews the farmer's identity and clicks Approve. If the requester attempts to approve their own request, the database service rejects it with `ValidationError("You cannot approve your own assisted issue request")`.

3. **Q: How does the Administrator dashboard support season management without data corruption?**  
   *Answer*: The Admin dashboard provides an instant active/closed toggle for cultivation seasons (Maha / Yala). When a season is toggled to `CLOSED`, `verify_farmer_token` and `confirm_issue_distribution` immediately block all fertilizer issuances for that season. Historical distributions and entitlements remain intact and read-only.

### PART 3: Reports, Batch Traceability & Exports
1. **Q: Why is the Batch Traceability page considered the core supply chain feature of FertiTracker?**  
   *Answer*: Traceability requires accounting for a batch from manufacture to farmer soil. On the Batch Traceability page (`/distributions/reports/batch-trace/`), entering a batch number displays its complete chronology across 5 stages: creation warehouse & expiry date, dispatches to ASCs, receiving reconciliation (good, damaged, missing bags), current on-hand balances across all ASCs, farmer distribution receipts (with masked NICs), and write-offs. A reconciliation ledger proves that `Dispatched Bags == Received Good + Damaged + Missing`.

2. **Q: Why did you use UTF-8 BOM (`\ufeff`) in CSV export, and why avoid ReportLab for PDF generation?**  
   *Answer*: Microsoft Excel on Windows defaults to legacy Windows-1252/ANSI decoding unless a UTF-8 Byte Order Mark (`\ufeff` / `utf-8-sig`) is present at the beginning of the file. Without the BOM, Sinhala and Tamil characters render as garbled mojibake (`à¶à·...`). For PDF generation, Python libraries like ReportLab lack HarfBuzz complex text shaping for Sinhala and Tamil conjunct glyphs, causing disjointed characters. By utilizing `@media print` with browser-native `window.print()`, the browser's native text engine shapes complex Unicode conjuncts flawlessly.

3. **Q: How is the audit log viewer designed to guarantee audit integrity?**  
   *Answer*: The audit log viewer (`/distributions/audit/logs/`) is strictly read-only. There are no update or delete routes, views, or forms anywhere in the codebase. Every security event (login, token verification, stock receiving, distribution, assisted approval, write-off) is appended immutably to the `AuditLog` table with user, timestamp, client IP, and action details.

### PART 4: Accounts, Authentication & Farmer Inclusion
1. **Q: How does the system secure temporary officer credentials and protect against privilege misuse?**  
   *Answer*: Only an Administrator can provision officer accounts (Warehouse Officer, ASC Counter Officer, ASC Head, Auditor). The system generates a cryptographically secure 12-character random temporary password (`secrets.token_urlsafe(9)`) displayed exactly once in an ephemeral flash message. The account is created with `must_change_password=True`. Upon first login, `login_view` detects this flag and forces the officer to a mandatory change password screen governed by Django's strict password validators (min 8 chars, common password checks, non-numeric). Officers cannot access operational views until they change their password. Furthermore, administrators can only deactivate or reactivate accounts; hard-deletions are blocked to maintain full audit accountability.

2. **Q: How are farmer accounts registered, and how are activation OTPs secured against brute-force and user enumeration?**  
   *Answer*: Farmers are registered by an ASC Officer, who validates their Sri Lankan National Identity Card (NIC) against both the 9-digit + V/X legacy format and the 12-digit modern format. Registered farmer accounts start strictly `INACTIVE` (`is_account_active=False`) and cannot log in until verified. When activating an account or resetting a password, the system generates a 6-digit OTP stored in the database as a keyed HMAC-SHA256 hash using a server secret from settings/env (preventing rainbow table reversal if the DB is compromised). Security controls include:
   - **Timing-safe comparison**: Verified using Python's `hmac.compare_digest()`.
   - **Short lifespan & single-use**: Expires after 5 minutes; marked `is_used=True` upon redemption.
   - **Brute-force lockout**: Inactivated after 5 consecutive incorrect attempts.
   - **Rate limiting**: Max 3 OTP requests per NIC per hour, with a mandatory 60-second cooldown between requests.
   - **Anti-enumeration**: The activation/reset endpoint returns an identical generic success response whether the NIC exists or not, preventing attackers from probing the database for registered citizens.

3. **Q: Why is phone-number updating restricted, and how is session hijacking prevented?**  
   *Answer*: Fertilizer subsidies attract identity fraud. A rogue officer could change a farmer's phone number to their own device and intercept OTP/SMS tokens. Therefore, updating a phone number requires the officer to explicitly check an "I verified the original NIC in person" declaration, which writes an immutable `AuditLog` record containing both the old and new masked numbers (`077****233` -> `071****677`). For session security, idle sessions expire after 30 minutes (`SESSION_COOKIE_AGE = 1800`), redirecting the user to `/login/` with a friendly translated alert (`?next=...`).

### PART 5: Seasons & Entitlement Management
1. **Q: How does FertiTracker enforce the single active season invariant across the entire system?**  
   *Answer*: Cultivation seasons in Sri Lanka are strictly divided into Maha and Yala. Allowing multiple active seasons creates ambiguity over which quota applies. In `toggle_season_status`, when an admin toggles a season to `ACTIVE`, the view immediately executes `Season.objects.exclude(id=season.id).update(status='CLOSED')` to close all other seasons. Furthermore, the central `confirm_issue_distribution` atomic service directly verifies `season.status == 'ACTIVE'` and raises a `ValidationError` if the season is closed, ensuring that even if an outdated UI form is submitted, the database transaction aborts.

2. **Q: How does the two-phase CSV entitlement import prevent incomplete or corrupted quota imports?**  
   *Answer*: Government quota files often contain thousands of rows and formatting anomalies (e.g., UTF-8 Byte Order Marks added by Windows Excel). The system implements a two-phase preview and atomic commit workflow:
   - **Phase 1 (Preview)**: Uploaded CSV files are parsed using Python's `utf-8-sig` encoding (transparently stripping BOMs if present). Each row is validated (NIC existence, valid product code, positive numeric quantity). The preview screen displays all valid and invalid rows; rows with unknown NICs or invalid quantities are highlighted with red alert badges, and the commit button is disabled until all errors are fixed.
   - **Phase 2 (Atomic Commit)**: The import is wrapped in `@transaction.atomic`. If any exception occurs during processing, the entire transaction rolls back—preventing partial imports. Every adjusted entitlement logs both the previous and new quota values to the immutable audit trail.

### PART 6: Append-Only Audit Logging & Database Integrity
1. **Q: How is the `AuditLog` model made mathematically and programmatically immutable?**  
   *Answer*: Unlike typical Django models where records can be edited or deleted via Python code or Django Admin, `AuditLog` enforces true append-only immutability at three distinct levels:
   - **Model Level**: The `save()` method raises `ValidationError("AuditLog records are append-only and cannot be modified.")` if `self.pk` already exists. The `delete()` method raises `ValidationError("AuditLog records cannot be deleted.")`.
   - **QuerySet Level**: A custom `AuditLogQuerySet` overrides `.update()` and `.delete()`, raising `ValidationError` on bulk operations like `AuditLog.objects.filter(...).delete()`.
   - **Django Admin Level**: `AuditLogAdmin` sets `has_add_permission`, `has_change_permission`, and `has_delete_permission` all to `False`, making it impossible for administrators or staff to tamper with logs through the administrative console.

2. **Q: Why were all instances of `date.today()` and `datetime.now()` replaced with `timezone.localdate()`?**  
   *Answer*: Server system clocks may run on UTC, while ASC centres and farmers operate in Sri Lanka Standard Time (`Asia/Colombo`, UTC+5:30). Using `date.today()` or naive `datetime.now()` creates a 5.5-hour timezone discrepancy where a batch expiring on midnight local time or a season toggle could be miscalculated or prematurely locked. By strictly enforcing `timezone.localdate()` and `timezone.now()`, all expiry checks, audit timestamps, and daily issue summaries reflect the exact calendar day in Sri Lanka.

3. **Q: What safeguards prevent the `seed_demo_data` command from wiping a live production database?**  
   *Answer*: In `core/management/commands/seed_demo_data.py`, an explicit environment guard checks `settings.DEMO_MODE`. If `DEMO_MODE` is not `True` and the administrator has not passed the explicit `--force` flag, the command immediately terminates with a `CommandError("DEMO_MODE is False. Refusing to seed demo data in a non-demo environment.")`. This ensures demo seeds cannot overwrite real agrarian records during deployment.

---

## 📜 Academic Integrity & Project Information
- **Course**: TICT3153 — Software Engineering Project
- **Exhibition**: ICT Expo 5.0, University of Vavuniya
- **License**: Academic / Government Prototype — Department of Agrarian Development, Sri Lanka

