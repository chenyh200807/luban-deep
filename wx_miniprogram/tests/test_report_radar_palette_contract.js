// test_report_radar_palette_contract.js — radar canvas must be visible in light and dark mode
// Run: node wx_miniprogram/tests/test_report_radar_palette_contract.js

var fs = require("fs");
var path = require("path");

var source = fs.readFileSync(path.join(__dirname, "../pages/report/report.js"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

assert(/const palette = this\.data\.isDark/.test(source), "report radar should branch palette by theme");
assert(/rgba\(15,23,42,0\.76\)/.test(source), "light mode should use dark label color");
assert(/palette\.grid/.test(source), "radar grid should use theme palette");
assert(/palette\.label/.test(source), "radar labels should use theme palette");

console.log("PASS test_report_radar_palette_contract.js");
