# Feature Poll — Admin Guide

## Overview

Feature polls let you ask users a question with multiple-choice options. The poll appears in the **Portfolio tab** of the iOS app. Only one poll can be active at a time. If no poll is active, nothing is shown.

---

## Admin Panel (Recommended)

Go to the **Polls** tab in the admin panel at `https://apestogether.ai/admin`.

### Creating a Poll
1. Click **New Poll**
2. Enter the question and at least 2 options (add/remove as needed)
3. Click **Create Poll** → confirm with 2FA
4. The new poll is immediately active; any previous active poll is auto-deactivated.

### Toggling On/Off
Each poll has a **toggle switch**. Flip it to activate or deactivate (requires 2FA). Activating a poll auto-deactivates any other active poll.

### Viewing Results
Click any poll card to expand it and see vote counts + percentages per option.

---

## How Voting Works

- Users see the active poll in the iOS app Portfolio tab.
- Each user gets **one vote per poll** (enforced by unique constraint).
- If a user votes again, their vote is **updated** (not duplicated).
- Results are visible to all users immediately after voting.

---

## API Endpoints (for reference)

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/mobile/admin/poll/list` | GET | Admin | List all polls with results |
| `/api/mobile/admin/poll/create` | POST | Admin 2FA | Create new poll |
| `/api/mobile/admin/poll/toggle` | POST | Admin 2FA | Activate/deactivate a poll |
| `/api/mobile/poll/active` | GET | User auth | Get active poll for app |
| `/api/mobile/poll/vote` | POST | User auth | Submit a vote |

---

## Database Tables

### `feature_poll`
| Column | Type | Description |
|---|---|---|
| `id` | Integer (PK) | Auto-increment |
| `question` | String(300) | The poll question |
| `options` | Text (JSON) | JSON array of option strings |
| `active` | Boolean | Only one should be `true` at a time |
| `created_at` | DateTime | Auto-set on creation |

### `feature_poll_vote`
| Column | Type | Description |
|---|---|---|
| `id` | Integer (PK) | Auto-increment |
| `poll_id` | Integer (FK) | References `feature_poll.id` |
| `user_id` | Integer (FK) | References `user.id` |
| `selected_option` | String(300) | The option the user chose |
| `voted_at` | DateTime | Auto-set, updated on re-vote |

**Unique constraint:** `(poll_id, user_id)` — one vote per user per poll.

---

## Where It Appears

- **iOS:** `FeaturePollView` is embedded in `MyPortfolioView`, below the Share Performance button.
- Users see the question, tap an option to vote, then see live results with vote counts and percentages.
