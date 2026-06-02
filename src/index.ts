import { chunkForMesh } from "./mesh/chunker.js";
import { SYSTEM_PROMPT } from "./llm/prompts.js";

async function main(): Promise<void> {
  const sampleReply =
    "1. Stop bleeding: direct pressure 10 min. 2. Elevate. 3. Tourniquet only if limb spurting and pressure failed. 4. Mark time on tourniquet. 5. Signal SOS / SAR. 6. Keep victim warm, monitor pulse.";

  console.log("--- system prompt ---");
  console.log(SYSTEM_PROMPT);
  console.log("--- mesh-ready chunks ---");
  for (const chunk of chunkForMesh(sampleReply)) {
    console.log(chunk);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
