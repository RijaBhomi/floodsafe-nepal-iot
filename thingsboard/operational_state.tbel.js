// FloodSafe Nepal — server-side operational state (TBEL transform node).
//
// IMPORTANT — PROPOSED MAPPING, NOT AN ASSIGNMENT SPECIFICATION.
// Assessment 1 Table 4 defines the four states qualitatively and says rules
// are location-specific and need persistent readings before escalation.
// No numeric transition thresholds, persistence counts or escalation timings
// are given in the assignment documents. The constants below are a candidate
// mapping derived from documented NDWQS values and the exact Task 3 alarm
// severities. Your group MUST approve them before using this in a submission.
//
// This node is stateless: it cannot count readings over time. "Multiple
// abnormal readings" is represented here by two or more abnormal VALUES in
// the same reading, which is an explicit simplification, not the documented
// persistence rule. See operational_states.md for the compatible options.

var WATCH_TURBIDITY_NTU = 5;        // NDWQS screening value (Assessment 1)
var WATCH_TDS_PPM = 1000;           // NDWQS screening value (Assessment 1)
var PH_LOW = 6.5;                   // NDWQS / Task 3 critical boundary
var PH_HIGH = 8.5;                  // NDWQS / Task 3 critical boundary
var HIGH_TURBIDITY_WARNING = 50;    // Task 3: High Turbidity Warning create
var GROSS_CONTAMINATION = 200;      // Task 3: Gross Contamination Critical create
var HIGH_TDS_CRITICAL = 500;        // Task 3: High TDS Critical create

// TBEL is Java-like: `value || 0` is invalid because || requires booleans.
// Explicit null checks keep missing values at zero without a script error.
var turbidity = msg['turbidity_ntu'];
if (turbidity == null) {
    turbidity = 0;
}
var ph = msg['ph'];
if (ph == null) {
    ph = 0;
}
var tds = msg['tds_ppm'];
if (tds == null) {
    tds = 0;
}
var flow = msg['flow_lpm'];
if (flow == null) {
    flow = 0;
}

var unusualCount = 0;
if (turbidity > WATCH_TURBIDITY_NTU) {
    unusualCount = unusualCount + 1;
}
if (ph < PH_LOW || ph > PH_HIGH) {
    unusualCount = unusualCount + 1;
}
if (tds > WATCH_TDS_PPM) {
    unusualCount = unusualCount + 1;
}

var critical = (turbidity > GROSS_CONTAMINATION) ||
               (ph < PH_LOW || ph > PH_HIGH) ||
               (tds > HIGH_TDS_CRITICAL);
var major = (flow == 0);   // Supply Interruption is Major in Task 3
var warning = (turbidity > HIGH_TURBIDITY_WARNING);

var state;
if (critical) {
    state = 'Intervention';   // Critical alarm severity -> decision-support state
} else if (major || unusualCount >= 2) {
    state = 'Investigate';    // Major severity / multiple abnormal values
} else if (warning || unusualCount >= 1) {
    state = 'Watch';          // Warning severity / one unusual value
} else {
    state = 'Normal';
}

// Node Inactive is a Critical alarm but produces no telemetry, so this
// transform cannot change the state while a node is offline. The alarm table
// and map marker still show it. Document this limitation in the report.

msg['operational_state'] = state;

// TbTransformMsgNode requires the full output envelope, not just the payload.
return {msg: msg, metadata: metadata, msgType: msgType};
