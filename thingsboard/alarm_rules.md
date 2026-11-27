# ThingsBoard alarm rules — FloodSafe Nepal

All six rules come **exactly** from `ITS67404_Assessment_Task_3_202609_MLO3_Updated.pdf`,
section C.3. Do not change a number, operator or severity.

## Alarm table

| Alarm name | Severity | Create condition | Clear condition | Hysteresis purpose |
| --- | --- | --- | --- | --- |
| High Turbidity | Warning | `turbidity_ntu > 50` | `turbidity_ntu < 40` | A node hovering at 50 NTU does not create hundreds of alarms. |
| Gross Contamination | Critical | `turbidity_ntu > 200` | `turbidity_ntu < 150` | Clears well below the trigger. |
| pH Out of Range | Critical | `ph < 6.5 OR ph > 8.5` | `6.7 ≤ ph ≤ 8.3` | Clear band is narrower than create band. |
| High TDS | Critical | `tds_ppm > 500` | `tds_ppm < 450` | Clears well below the trigger. |
| Supply Interruption | Major | `flow_lpm == 0` sustained | `flow_lpm > 0` | Prevents a brief zero sample from alarming. |
| Node Inactive | Critical | Device inactivity timeout exceeded | Telemetry resumes | Detects a lost node, not a bad reading. |

**Not specified in the assignment (needs group decision before you configure):**

- How long "sustained" is for `flow_lpm == 0`. The document gives no seconds or minutes.
- The device inactivity timeout value. Task 3 says to configure it but gives no value.
- Named responder, acknowledgement deadline and escalation chain. The Assignment 2
  report says these exist but gives no names or times.

Do not guess these. Write your agreed values into your report and screenshot the
configured values.

## Configure in the web interface (preferred method)

Task 3 says Device Profile → Alarm Rules is the preferred location.

1. Log in to **the same ThingsBoard region** as `THINGSBOARD_HOST`
   (`thingsboard.cloud` → North America, `eu.thingsboard.cloud` → Europe).
2. Go to **Device profiles** → **+ Add device profile**.
3. Name it exactly `FloodSafe Node`. This name matters: the dashboard JSON uses
   it in its entity alias.
4. Open the new profile → **Alarm rules** tab → **Add alarm rule**.
5. For each row in the table above:
   - **Alarm type**: type the alarm name exactly as shown.
   - **Severity**: choose the shown severity.
   - **Create condition**: add a condition on the telemetry key, e.g.
     key `turbidity_ntu`, operation `>`, value `50`.
   - For `ph < 6.5 OR ph > 8.5`, add **two** conditions and join them with **OR**:
     `ph < 6.5` and `ph > 8.5`.
   - **Clear condition**: add the clear expression from the table.
     For `6.7 ≤ ph ≤ 8.3`, use two conditions joined with **AND**:
     `ph >= 6.7` and `ph <= 8.3`.
   - **Duration / "for"**: for Supply Interruption, enter the group-agreed
     sustained duration. Leave the others at their default unless your group
     agrees otherwise.
   - Click **Add**, then **Save**.
6. Go to **Devices** → open each of `FSN-01`, `FSN-02`, `FSN-03` → set its
   device profile to `FloodSafe Node` → **Save**.
7. In the `FloodSafe Node` profile, configure the **inactivity timeout** to the
   group-agreed value. This is what creates/clears **Node Inactive**.
8. Take screenshots of the alarm-rule list (all six rows) and the inactivity
   timeout field.

## Why the clear thresholds differ from the create thresholds

This is hysteresis. If High Turbidity created an alarm at `> 50` and cleared at
`< 50`, a sensor reading 49.9 / 50.1 / 49.9 would flip the alarm repeatedly.
Clearing only below 40 means the water must visibly recover before the alarm
disappears. The same idea applies to 200/150, 500/450 and 6.5/8.5 vs 6.7/8.3.

## Alternative: custom rule chain

Task 3 allows a custom rule chain instead. If you choose that route, keep the
same six alarm types, severities and create/clear expressions. Use
`org.thingsboard.rule.engine.action.TbCreateAlarmNode` and
`org.thingsboard.rule.engine.action.TbClearAlarmNode` nodes, then export the
rule chain and save the export in this folder. Do not use the four operational
state names as severities — they are decision-support labels, not alarms.
