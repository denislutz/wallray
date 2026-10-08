# New-User Registration Notification — Plan

## Goal

When a brand-new user registers for the first time, send a notification email to
`info@example.com`.

## Trigger point

`be/app/api/routes/auth.py::verify_otp` — the `if user is None:` branch is exactly where a
brand-new `UserRow` is first created. That's the only place "first-time registration" is known
with certainty (matches `docs/tech/AUTH_PLAN.md`'s "backend upserts on first verify" design).

## Pattern to follow

The codebase already has a clean port/adapter/template pipeline for transactional email
(`EmailPort` → `ResendAdapter` → Jinja templates), used by `expert_notifier.py` for the
structurally identical "notify someone when an event happens" case. Extend that pipeline rather
than reusing the ad-hoc raw `resend.Emails.send()` call that `send_otp` uses (that one's a
blocking, un-templated one-off and shouldn't be the model for new code).

## Changes

1. **`be/app/core/config.py`** — add one setting:

   ```python
   new_user_notification_email: str = Field(default="", validation_alias="NEW_USER_NOTIFICATION_EMAIL")
   ```

   Env-configurable (matches the existing `ADMIN_EMAILS`/`EXPERT_REVIEW_EMAILS` pattern), set to
   `info@example.com` in `.env.prod` / `.env.test` / `.env.local`. Keeping it a dedicated var
   rather than reusing `ADMIN_EMAILS` — that list is currently `owner@example.com` and drives
   role assignment, a different concern from "who gets pinged on signup."

2. **`be/app/domain/ports/email.py`** — add to `EmailPort` protocol:

   ```python
   async def send_new_user_notification(
       self, to: str, user_email: str, role: str, locale: str = "en"
   ) -> None: ...
   ```

3. **`be/app/adapters/email/resend.py`** — implement `send_new_user_notification` on
   `ResendAdapter`, following `send_expert_review_request`'s shape (skip silently if `to` is
   empty, render template, log).

4. **`be/app/adapters/email/templates/new_user.html`** — new template extending `base.html`,
   showing the new user's email + role. Add matching keys to `locales/en.json`, `de.json`,
   `ru.json`.

5. **`be/app/api/routes/auth.py`** — inject `email: Annotated[ResendAdapter, Depends(get_email)]`
   into `verify_otp`, and inside `if user is None:` (after `session.commit()`/`refresh`), fire:

   ```python
   with contextlib.suppress(Exception):
       await email.send_new_user_notification(
           to=settings.new_user_notification_email,
           user_email=user.email,
           role=user.role,
       )
   ```

   Wrapped in `contextlib.suppress` — same as `expert_notifier` — so a Resend hiccup never breaks
   the user's actual sign-in.

6. **Tests** — extend `be/tests/test_auth.py::test_verify_otp_creates_user_on_first_verify` (or
   add a sibling test) asserting the notification fires once on first verify and not on repeat
   verifies for the same email, using the existing fake email adapter in `be/tests/fakes.py`.

## Migration

No schema changes, no `orm_models.py` touch, so no Alembic migration needed.
