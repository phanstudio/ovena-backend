# Referrals App

This app owns referral relationships between profiles.

## What this app owns

- `ProfileReferral`: one referral link from one profile to another.

## Mental model

- Referrals are profile-based, not just user-based.
- The model stores both profile links and user links for safety and easier querying.

## Relationships that matter

- Both sides point to `accounts.ProfileBase`.
- Both sides also point to the corresponding `accounts.User`.
- The app expects profile/user pairs to match correctly.

## Important rules

- No self-referrals.
- One referee profile can only be referred once.
- Conversion and reward issuance are tracked separately.

## Remember this when coming back

- Referral identity starts from `ProfileBase`.
- If referral code behavior is confusing, also check `accounts.ProfileBase`, because that is where referral codes are generated.
