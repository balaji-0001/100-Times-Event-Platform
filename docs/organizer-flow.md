# Organizer Onboarding & Event Lifecycle Flow

## 1. Organizer Journey
```text
DISCOVERY → INVITED → SIGNED_UP → CREATED_EVENT → SUBMITTED → TRUST_CHECK → APPROVED → PUBLISHED → REGISTRATIONS → EVENT_COMPLETED → FOLLOW_UP → REPEAT_ORGANIZER
```

## 2. Onboarding Steps
1. **Sign Up / Login:** Organizers sign up via `/register` or upgrade via `/organizer` (`POST /api/auth/register` or `POST /api/organizer/onboarding`).
2. **Organization & Profile Verification:** Organizers provide organization/company name, contact email/phone, website, and social links (`OrganizerProfile` & `Organization` tables).
3. **Multi-Step Event Creation (`/organizer/events/create`):**
   - **Step 1:** Title, description, category, event type, tags, target audience
   - **Step 2:** Start/end date, start/end time, IANA timezone, format (`in-person`, `online`, `hybrid`), venue, full address, city, state, country, online meeting URL
   - **Step 3:** Free/paid toggle, ticket price, capacity limit, registration URL, ticket tier metadata
   - **Step 4:** Speaker lineup, banner image URL, contact details, website/social links, terms & cancellation policy
   - **Step 5:** Save as Draft (`lifecycle_state = DRAFT`) OR Submit to Trust Agent (`SUBMITTED` → `TRUST_CHECK`)
   - **Step 6 & 7:** View Trust Agent checklist (`✓ Event information complete`, `✓ Organizer verified`, `✓ No duplicate detected`, `✓ No major risk detected`) and either go live immediately (`"Event published successfully."`) or enter moderation (`"Your event is under review."`) without losing any data.
