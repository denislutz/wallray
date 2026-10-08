import type { LegalCopy } from "./types";

export const EN_LEGAL: LegalCopy = {
  privacy: {
    heading: "Privacy Policy",
    markdown: `## Controller

Example Co LLC (a US company). All customers are EU-based; this policy applies GDPR regardless of
where the controller is incorporated (Art. 3(2)).

Contact: <privacy@example.com>

## What We Collect

- Your email address (used for sign-in via a one-time code, and to deliver your report)
- Photos you upload for assessment
- The free-text description you provide alongside your photos
- Standard server logs, including your IP address

We do not collect your name or a password — sign-in is email plus a one-time code only. WallRay
does not currently process payments, so no billing data is collected either.

## Legal Basis

We process your data on the basis of performing the contract with you: providing the WallRay
assessment service you requested (Art. 6(1)(b) GDPR).

## Processors

We share data with the following processors, each under a signed data processing agreement:

- **Hetzner Online GmbH** (Germany) — hosting and object storage. EU-based; no cross-border
  transfer.
- **Anthropic** (United States) — generates your AI assessment report from your photos and
  description.
- **Resend** (United States) — sends transactional email (sign-in codes, report delivery).

### International Transfers

Anthropic and Resend are based in the United States. Where your personal data is transferred
there, it is protected under Standard Contractual Clauses (SCCs) included in each processor's
data processing agreement.

## Retention

- Uploaded photos: 90 days
- Generated reports: 1 year
- Account data: 30 days after you delete your account
- Server logs: 30 days

## Your Rights

Under GDPR you have the right to access, correct, restrict, or object to our processing of your
data, to have it erased, and to receive a copy of it in a portable format. To exercise any of
these rights, contact us at <privacy@example.com>. At our current size, requests are handled manually
and fulfilled within the statutory timeframe (generally within one month).

## Cookies

WallRay does not use cookies or analytics of any kind.`,
  },
  disclaimer: {
    heading: "Disclaimer & Acceptable Use",
    markdown: `## Report Disclaimer

WallRay's assessment reports are produced by automated AI systems for informational purposes
only. They do not constitute a professional structural, architectural, or building survey.
WallRay makes no warranty as to accuracy or completeness. Obtain a qualified professional
inspection before making repair, legal, or financial decisions.

By using WallRay, you agree not to rely on a report as a substitute for a licensed professional's
inspection, and that WallRay and Example Co LLC are not liable for decisions made or losses incurred
in reliance on a report.

## Acceptable Use

You may not:

- Upload images that don't belong to you or that you don't have permission to use
- Use the service to generate fraudulent reports for insurance or legal claims
- Attempt to reverse-engineer, scrape, or abuse the AI assessment system
- Upload images containing identifiable people without their consent`,
  },
};
