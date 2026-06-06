// Language detection via QVAC's @qvac/langdetect-text.
// Used by bot.py to route the reply language for an incoming mesh query.
//
//   node tools/langdetect.mjs "被毒蛇咬到了怎麼辦"
//   -> {"code":"zh","language":"Chinese","probability":1}
//
// Prints ONLY a JSON object to stdout (any library noise goes to stderr), so the
// Python side can parse it safely. Exits non-zero on empty input.
import { detectMultiple } from "@qvac/langdetect-text";

const text = process.argv.slice(2).join(" ").trim();
if (!text) {
  process.stderr.write("usage: node tools/langdetect.mjs <text>\n");
  process.exit(2);
}

const [top] = detectMultiple(text, 1);
process.stdout.write(JSON.stringify({
  code: top?.code ?? "und",
  language: top?.language ?? "Unknown",
  probability: top?.probability ?? 0,
}));
