# Email notification for Critical Intervention alarms

This is an optional configuration in ThingsBoard, not a local code change.
It was verified in the demo tenant: newly created Critical water-quality alarms
sent mail through the rule-engine path below. No secret belongs in this
repository. Enter the Gmail app password only in the ThingsBoard `Send Email`
rule node. Do not paste it into a terminal recording, screenshot, `.env`,
exported rule-chain JSON or Git commit.

## 1. Verified flow

The working path in the demo tenant is:

`Alarm Created` → `FloodSafe Critical Water Quality` → `To Email` → `Send Email`

- `Alarm Created` emits only new alarm events. Do not listen to update,
  acknowledgement or clear events, or the mailbox will fill with duplicates.
- `FloodSafe Critical Water Quality` admits exactly three alarm types:
  `Gross Contamination`, `pH Out of Range` and `High TDS`.
- `To Email` prepares the message for the operator recipient group.
- `Send Email` delivers it through custom Gmail SMTP.

`Node Inactive` is also Critical in Task 3, but it means the device is offline
rather than the water being contaminated. It is deliberately excluded.

No district, latitude or longitude claim is made here. If you add those fields
to a template, confirm from a delivered message that your ThingsBoard version
renders them; do not assume the dashboard mapping is present in mail.

## 2. Prepare the Gmail app password

1. Use a Gmail account that has **2-step verification** enabled.
2. Go to Google Account → **Security** → **2-Step Verification** →
   **App passwords**.
3. Create an app password for **Mail** on the device/app used for the demo.
4. Keep it ready for the `Send Email` rule node. It is not the normal Gmail
   login password.

If your college Gmail account does not allow app passwords, use an institutional
SMTP account instead and replace the host/port values below with the ones given
by your mail administrator.

## 3. Configure the `Send Email` rule node

In the rule chain that handles alarms, add or open a `Send Email` node and use:

| Field | Value |
| --- | --- |
| SMTP host | `smtp.gmail.com` |
| SMTP port | `587` |
| Security | **STARTTLS** |
| Username | the full Gmail address |
| Password | the Gmail **app password** (enter only in this rule node) |

If your ThingsBoard version offers SSL/TLS instead of STARTTLS, use port `465`
with SSL/TLS. Do not enable both. Use **Send test email** if that button is
available.

The SMTP password is stored in the tenant's rule-node configuration. Never
export that configured chain into this repository, photograph the form, or
include the password in a terminal recording.

## 4. Build the rule path

1. Start from the alarm **Created** event (`Alarm Created` in the verified
   chain).
2. Add a filter named `FloodSafe Critical Water Quality` that passes only
   `Gross Contamination`, `pH Out of Range` and `High TDS`.
3. Add `To Email` to build the message from the alarm.
4. Connect its **Success** relation to the configured `Send Email` node.
5. Save and enable the chain. Keep the alarm-type spelling exact; a mismatch
   silently drops the mail.

## 5. Message body example

The verified message was an ordinary alarm email. A suitable example body is:

```text
A Critical water-quality alarm requires Intervention.

Device: ${deviceName}
Alarm: ${alarmType}
Severity: ${severity}
Created: ${createdTime}

Response required:
1. Stop supply at this water point.
2. Acknowledge the alarm in ThingsBoard.
3. Resample and verify after flushing/mixing.
4. Resume supply only after safe readings persist.
```

Use only dynamic fields that render in your ThingsBoard version. Remove a field
rather than inventing a replacement if it appears as literal text.

## 6. Test with deterministic readings

After setting the three `FSN_XX_TOKEN` values in `.env`:

```powershell
.\.venv\Scripts\python.exe thingsboard\publish_test_reading.py --node FSN-01 --turbidity 260 --ph 6.2 --tds 600 --flow 12
```

Expected:

- Alarm table shows Gross Contamination, pH Out of Range and High TDS as ACTIVE.
- Node badge shows Intervention with the response strip.
- One email arrives for each newly created Critical alarm type.

Clear the alarms before retesting. An alarm that is already ACTIVE does not
emit another **Created** event, so no new email should be expected. Clear with a
normal reading:

```powershell
.\.venv\Scripts\python.exe thingsboard\publish_test_reading.py --node FSN-01 --turbidity 4 --ph 7.1 --tds 180 --flow 12
```

No new email should be sent on clearing because the rule listens to **Created**
events only.

## 7. Troubleshooting

| Symptom | Check |
| --- | --- |
| Test email fails | Gmail app password, 2FA enabled, STARTTLS/port 587 |
| No email after alarm | Rule enabled, event `Created`, alarm type spelling exact |
| Too many emails | Remove update/acknowledgement/clear events and keep `Created` only |
| Email in spam | Mark as not spam; check Gmail forwarding/filters |
| Node Inactive email appears | Alarm-type filter was not applied; restrict to the three water-quality types |

## 8. Honest limitation

This path was verified in the demo tenant, including delivery of mail from the
rule chain. In a different tenant it is not configured until you complete these
steps and receive a test email. The repository documents the steps only and
contains no SMTP credentials.
